from tg_harness import claude, state


def test_passes_permission_flags_and_reports_unique_denials(fake_claude):
    session = state.new_session()
    session.update(mode="plan", allow=["WebFetch"])
    assert claude.ask_claude(session, "hi") == ("нужен fetch", ["WebFetch", "Bash"])
    assert session["session"] == "S1"
    cmd = fake_claude[-1]
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"
    assert cmd[cmd.index("--allowedTools") + 1] == "WebFetch"


def test_telegram_hint_only_on_first_turn(fake_claude):
    session = state.new_session()
    claude.ask_claude(session, "hi")
    assert "Telegram" in fake_claude[-1][2] and fake_claude[-1][2].endswith("hi")
    claude.ask_claude(session, "hi again")
    assert fake_claude[-1][2] == "hi again" and "--resume" in fake_claude[-1]
