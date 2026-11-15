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
WORKDIR = str(ROOT / os.path.expanduser(CFG.get("workdir", ".")))
PROVIDERS = CFG["providers"]  # name -> {"env": {...}, "models": [...]}

for _name, _provider in PROVIDERS.items():
    assert _provider["models"], f"provider {_name}: models list is empty"
    # names go into Telegram callback_data, which is capped at 64 bytes
    for _option in [_name, *_provider["models"]]:
        assert len(f"/provider {_option}".encode()) <= 64, f"provider {_name}: name too long: {_option}"

MODES = ["default", "acceptEdits", "plan", "bypassPermissions"]  # claude --permission-mode values
BUTTONS = {"🆕 Новая сессия": "/new", "📂 Сессии": "/sessions", "🔐 Права": "/mode",
           "🤖 Модель": "/model", "🔌 Провайдер": "/provider", "♻️ Рестарт бота": "/restart"}
_buttons = [{"text": label} for label in BUTTONS]
KEYBOARD = json.dumps({"keyboard": [_buttons[:3], _buttons[3:]], "resize_keyboard": True, "is_persistent": True})
