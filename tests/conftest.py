import os

os.environ.setdefault("TG_TOKEN", "test-token")  # must be set before tg_harness.config is imported

import pytest
from tg_harness import config, state, telegram

OWNER = 1  # the only allowed user in tests


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    """Stub Telegram and reset config/state for every test. Returns the list of (method, params) calls."""
    calls = []
    monkeypatch.setattr(telegram, "tg", lambda method, **params: calls.append((method, params)))
    monkeypatch.setattr(config, "CFG", {})
    monkeypatch.setattr(config, "ALLOWED", {OWNER})
    monkeypatch.setattr(config, "PROVIDERS", {"a": {"models": ["m1", "m2"]}, "b": {"models": ["x"]}})
    monkeypatch.setattr(config, "WORKDIRS", {"bot": "/srv/bot", "other": "/srv/other"})
    monkeypatch.setattr(state, "chats", {})
    return calls


@pytest.fixture
def fake_claude(monkeypatch):
    """Stub `claude -p`: records argv, answers with a WebFetch+Bash permission denial."""
    from tg_harness import claude
    calls = []
    class FakeProc:
        returncode, stderr = 0, ""
        stdout = '{"result": "нужен fetch", "session_id": "S1", "permission_denials": ' \
                 '[{"tool_name": "WebFetch"}, {"tool_name": "WebFetch"}, {"tool_name": "Bash"}]}'
    monkeypatch.setattr(claude.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd) or FakeProc)
    return calls
