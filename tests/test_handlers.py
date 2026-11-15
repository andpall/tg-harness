import json
import pytest
from tg_harness import handlers, state, telegram
from conftest import OWNER

STRANGER = 999


def message(text, user_id=OWNER):
    return {"chat": {"id": 1}, "from": {"id": user_id}, "text": text}


def callback(data, user_id=OWNER):
    return {"id": "q", "from": {"id": user_id}, "data": data, "message": {"chat": {"id": 1}}}


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
    state.current_session(1)
    handlers.handle(message("🆕 Новая сессия"))
    assert state.chats[1]["current"] == "2" and sent[-1][1]["text"].startswith("Сессия «2»")


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
