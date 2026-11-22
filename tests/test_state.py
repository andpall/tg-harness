from tg_harness import state


def test_save_and_load_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "SESSIONS_FILE", tmp_path / "sessions.json")
    session = state.current_session(1)
    session["session"] = "claude-session-id"
    state.save()

    state.chats = {}
    state.load()
    assert state.chats[1]["sessions"]["1"]["session"] == "claude-session-id"


def test_load_without_file_keeps_empty_chats(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "SESSIONS_FILE", tmp_path / "missing.json")
    state.load()
    assert state.chats == {}


def test_load_broken_file_starts_fresh(monkeypatch, tmp_path):
    broken = tmp_path / "sessions.json"
    broken.write_text('{"1": {"sessions"')  # cut off mid-write
    monkeypatch.setattr(state, "SESSIONS_FILE", broken)
    state.load()
    assert state.chats == {}


def test_save_replaces_file_without_leftovers(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "SESSIONS_FILE", tmp_path / "sessions.json")
    state.current_session(1)
    state.save()
    state.save()
    assert [path.name for path in tmp_path.iterdir()] == ["sessions.json"]
