"""Settings: secrets and access list from .env, shared settings from config.json (both in the repo root)."""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # src/tg_harness/config.py -> repo root


def _load_dotenv(path):
    """KEY=value lines; variables already set in the real environment win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(ROOT / ".env")

TOKEN = os.environ["TG_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}/"
CFG = json.loads((ROOT / "config.json").read_text())
# comma-separated Telegram user ids; empty = nobody (the bot replies with the sender's id)
ALLOWED = {int(user_id) for user_id in os.environ.get("TG_ALLOWED", "").split(",") if user_id.strip()}


def parse_workdirs(default, extra):
    """Default workdir + comma-separated extras -> {folder name: absolute path}, default first."""
    paths = [default, *(path.strip() for path in extra.split(",") if path.strip())]
    workdirs = {}
    for path in paths:
        absolute = (ROOT / os.path.expanduser(path)).resolve()
        assert absolute.is_dir(), f"workdir not found: {absolute}"
        assert absolute.name not in workdirs, f"two workdirs named {absolute.name}"
        # names go into Telegram callback_data, which is capped at 64 bytes
        assert len(f"/workdir {absolute.name}".encode()) <= 64, f"workdir name too long: {absolute.name}"
        workdirs[absolute.name] = str(absolute)
    return workdirs


WORKDIRS = parse_workdirs(os.environ.get("TG_WORKDIR") or ".", os.environ.get("TG_EXTRA_WORKDIRS", ""))
PROVIDERS = CFG["providers"]  # name -> {"env": {...}, "models": [...]}

for _name, _provider in PROVIDERS.items():
    assert _provider["models"], f"provider {_name}: models list is empty"
    # names go into Telegram callback_data, which is capped at 64 bytes
    for _option in [_name, *_provider["models"]]:
        assert len(f"/provider {_option}".encode()) <= 64, f"provider {_name}: name too long: {_option}"

MODES = ["default", "acceptEdits", "plan", "bypassPermissions"]  # claude --permission-mode values
BUTTONS = {"📂 Сессии": "/sessions", "📁 Папка": "/workdir", "⚙️ Настройки": "/settings"}
# rarely-pressed commands, tucked under "⚙️ Настройки" instead of their own keyboard button
SETTINGS_MENU = {"🔐 Права": "/mode", "🤖 Модель": "/model", "🔌 Провайдер": "/provider", "♻️ Рестарт бота": "/restart"}
_buttons = [{"text": label} for label in BUTTONS]
KEYBOARD = json.dumps({"keyboard": [_buttons], "resize_keyboard": True, "is_persistent": True})
