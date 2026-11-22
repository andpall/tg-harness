import json
import pytest
from tg_harness import handlers, state, telegram
from conftest import OWNER

STRANGER = 999


def message(text, user_id=OWNER):
    return {"chat": {"id": 1}, "from": {"id": user_id}, "text": text}


def callback(data, user_id=OWNER, message_id=1):
    return {"id": "q", "from": {"id": user_id}, "data": data, "message": {"chat": {"id": 1}, "message_id": message_id}}


def test_model_and_provider_switching():
    session = state.current_session(1)
    assert (session["provider"], session["model"]) == ("a", "m1")
    handlers.command(1, "/model", "m2"); assert session["model"] == "m2"
    handlers.command(1, "/model", "nope"); assert session["model"] == "m2"  # unknown -> picker, no change
    handlers.command(1, "/provider", "b"); assert (session["provider"], session["model"]) == ("b", "x")


def test_unknown_command_goes_to_claude():
    assert handlers.command(1, "/compact", "") is False


def test_new_session_keeps_the_old_one_and_sessions_switches_back():
    old = state.current_session(1)
    old["session"] = "s"
    handlers.command(1, "/new", "")
    chat = state.chats[1]
    assert chat["current"] == "2" and state.current_session(1)["session"] is None
    handlers.command(1, "/sessions", "1")
    assert state.current_session(1) is old


def test_reply_keyboard_button_maps_to_command(sent):
    handlers.handle(message("📂 Сессии"))
    assert sent[-1][1]["text"] == "Переключиться на сессию:"


def test_new_session_button_under_session_list(sent):
    handlers.command(1, "/sessions", "")
    footer = json.loads(sent[-1][1]["reply_markup"])["inline_keyboard"][-1]
    handlers.handle_callback(callback(footer[0]["callback_data"]))
    assert list(state.chats[1]["sessions"]) == ["1", "2"] and state.chats[1]["current"] == "2"


def test_delete_session_moves_current_and_recreates_last():
    handlers.command(1, "/new", "")  # sessions 1 and 2, current 2
    handlers.command(1, "/delsession", "2")
    assert list(state.chats[1]["sessions"]) == ["1"] and state.chats[1]["current"] == "1"
    handlers.command(1, "/delsession", "1")
    assert list(state.chats[1]["sessions"]) == ["1"] and state.current_session(1)["session"] is None


def test_callbacks_ignore_strangers_and_forged_data():
    session = state.current_session(1)
    handlers.handle_callback(callback("/provider b", STRANGER)); assert session["provider"] == "a"
    handlers.handle_callback(callback("/provider zzz")); assert session["provider"] == "a"
    handlers.handle_callback(callback("/provider b")); assert session["provider"] == "b"
    handlers.handle_callback(callback("/allow Read", STRANGER)); assert session["allow"] == []


def test_settings_menu_button_opens_its_picker(sent):
    handlers.command(1, "/settings", "")
    buttons = json.loads(sent[-1][1]["reply_markup"])["inline_keyboard"]
    assert [row[0]["callback_data"] for row in buttons] == ["/mode", "/model", "/provider", "/restart"]

    handlers.handle_callback(callback("/model", message_id=5))
    assert ("deleteMessage", {"chat_id": 1, "message_id": 5}) in sent
    assert sent[-1][1]["text"] == "Модель (a):"  # opened the picker instead of applying an empty choice


def test_picker_choice_deletes_the_menu_message(sent):
    handlers.handle_callback(callback("/provider b", message_id=7))
    assert ("deleteMessage", {"chat_id": 1, "message_id": 7}) in sent


def test_allow_grant_strips_keyboard_but_keeps_message(sent, fake_claude):
    handlers.run(1, "hi")
    handlers.handle_callback(callback("/allow Bash", message_id=9))
    assert ("editMessageReplyMarkup",
            {"chat_id": 1, "message_id": 9, "reply_markup": json.dumps({"inline_keyboard": []})}) in sent
    assert not any(method == "deleteMessage" for method, _ in sent)


def test_mode_and_allow():
    session = state.current_session(1)
    handlers.command(1, "/mode", "plan"); assert session["mode"] == "plan"
    handlers.command(1, "/mode", "evil"); assert session["mode"] == "plan"
    handlers.command(1, "/allow", "WebFetch"); handlers.command(1, "/allow", "WebFetch")
    assert session["allow"] == ["WebFetch"]
    handlers.command(1, "/allow", "reset"); assert session["allow"] == []


def test_permission_denial_shows_buttons_and_grant_retries(sent, fake_claude):
    session = state.current_session(1)
    handlers.run(1, "hi")
    keyboard = json.loads(sent[-1][1]["reply_markup"])["inline_keyboard"]
    assert [row[0]["callback_data"] for row in keyboard] == ["/allow WebFetch", "/allow Bash"]

    handlers.handle_callback(callback("/allow Bash"))
    assert session["allow"] == ["Bash"]
    assert "--resume" in fake_claude[-1] and "Bash" in fake_claude[-1][2]  # retried in the same session


def test_voice_is_transcribed_and_sent_to_claude(monkeypatch):
    runs = []
    monkeypatch.setattr(handlers.voice, "transcribe", lambda file_id: f"transcribed:{file_id}")
    monkeypatch.setattr(handlers, "run", lambda chat_id, prompt: runs.append((chat_id, prompt)))
    handlers.handle({"chat": {"id": 1}, "from": {"id": OWNER}, "voice": {"file_id": "F1"}})
    assert runs == [(1, "Voice message: *transcribed:F1*")]


def test_photo_is_downloaded_and_sent_to_claude(monkeypatch, tmp_path):
    runs, downloads = [], []
    saved_path = tmp_path / "photo.jpg"
    saved_path.write_bytes(b"")
    def fake_save_file(file_id, suffix):
        downloads.append(file_id)
        return str(saved_path)
    monkeypatch.setattr(handlers.telegram, "save_file", fake_save_file)
    monkeypatch.setattr(handlers, "run", lambda chat_id, prompt: runs.append((chat_id, prompt)))
    handlers.handle({"chat": {"id": 1}, "from": {"id": OWNER},
                      "photo": [{"file_id": "small"}, {"file_id": "F1"}], "caption": "смотри"})
    assert downloads == ["F1"]  # last entry is the largest size
    assert runs == [(1, f"Прислали картинку, посмотри её: {saved_path}\nсмотри")]
    assert not saved_path.exists()  # cleaned up after the claude call


def test_restart_acks_update_before_exec(sent, monkeypatch):
    """Otherwise Telegram redelivers /restart after exec -> endless restart loop."""
    class Exec(BaseException):  # BaseException: the main loop swallows Exception
        pass
    def fake_execv(*args):
        raise Exec
    monkeypatch.setattr(telegram.os, "execv", fake_execv)
    monkeypatch.setattr(telegram, "offset", 42)
    with pytest.raises(Exec):
        handlers.command(1, "/restart", "")
    assert sent[-1] == ("getUpdates", {"offset": 42, "timeout": 0})
    assert ("sendMessage", "Перезапускаюсь...") in [(method, params.get("text")) for method, params in sent]


def test_clear_resets_context_but_keeps_session():
    session = state.current_session(1)
    session.update(session="s", msgs=3, workdir="other")
    handlers.command(1, "/clear", "")
    assert (session["session"], session["msgs"], session["workdir"]) == (None, 0, "other")
    assert list(state.chats[1]["sessions"]) == ["1"]  # not deleted, just cleared


def test_workdir_switch_resets_claude_context():
    session = state.current_session(1)
    session.update(session="s", msgs=3)
    assert session["workdir"] == "bot"
    handlers.command(1, "/workdir", "other")
    assert (session["workdir"], session["session"], session["msgs"]) == ("other", None, 0)


def test_workdir_ignores_names_not_in_config():
    session = state.current_session(1)
    handlers.handle_callback(callback("/workdir /etc"))
    assert session["workdir"] == "bot"


def test_rename_button_then_text_renames_and_keeps_order(sent):
    state.current_session(1)
    handlers.command(1, "/new", "work")  # sessions 1 and work, current work
    handlers.handle_callback(callback("/renamesession work"))
    handlers.handle(message("  проект  "))
    chat = state.chats[1]
    assert list(chat["sessions"]) == ["1", "проект"] and chat["current"] == "проект"
    assert sent[-1][1]["text"] == "Сессия «work» теперь «проект»."


def test_rename_to_taken_name_gets_suffix():
    state.current_session(1)
    handlers.command(1, "/new", "a")
    handlers.command(1, "/renamesession", "a")
    handlers.handle(message("1"))
    assert list(state.chats[1]["sessions"]) == ["1", "1-2"]


def test_command_cancels_pending_rename():
    state.current_session(1)
    handlers.command(1, "/renamesession", "1")
    handlers.handle(message("📂 Сессии"))
    assert list(state.chats[1]["sessions"]) == ["1"] and "renaming" not in state.chats[1]


def test_session_names_fit_callback_data():
    name = state.clean_name("🚀" * 20)
    assert len(f"/renamesession {name}".encode()) <= 64


def test_busy_session_does_not_block_another(sent, fake_claude):
    busy = state.current_session(1)
    handlers.command(1, "/new", "free")
    with state.session_lock(busy):  # session 1 is in the middle of a long Claude run
        handlers.run(1, "hi")
    assert len(fake_claude) == 1 and sent[-1][1]["text"].startswith("[free]\n")


def test_single_session_answer_has_no_label(sent, fake_claude):
    handlers.run(1, "hi")
    assert sent[-1][1]["text"].startswith("нужен fetch")
