"""One `claude -p` turn per call."""
import json, os, subprocess
from . import config

TELEGRAM_HINT = "Сообщения приходят через Telegram-бота, учитывай это в ответах.\n\n"


def ask_claude(session, prompt):
    """Returns (answer text, names of tools that were denied)."""
    provider_env = config.PROVIDERS[session["provider"]].get("env", {})
    env = {**os.environ, **{name: os.path.expandvars(value) for name, value in provider_env.items()}}
    env.pop("TG_TOKEN", None)  # the agent has no business with the bot token

    if not session["session"]:
        prompt = TELEGRAM_HINT + prompt
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", session["model"],
           "--permission-mode", session["mode"], *config.CFG.get("claude_args", [])]
    if session["allow"]:
        cmd += ["--allowedTools", *session["allow"]]
    if session["session"]:
        cmd += ["--resume", session["session"]]

    proc = subprocess.run(cmd, cwd=config.WORKDIR, env=env, capture_output=True, text=True)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return f"claude failed (exit {proc.returncode}):\n{proc.stderr or proc.stdout}", []

    session["session"] = result.get("session_id") or session["session"]
    session["msgs"] = session.get("msgs", 0) + 1
    denied_names = (denial.get("tool_name") for denial in result.get("permission_denials") or [])
    denied_tools = list(dict.fromkeys(name for name in denied_names if name))  # unique, keep order
    answer = result.get("result") or json.dumps(result, ensure_ascii=False)[:3000]
    return answer, denied_tools
