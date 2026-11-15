"""Per-chat sessions, kept in memory (lost on restart)."""
import threading
from . import config

chats = {}  # chat_id -> {"sessions": {name: session}, "current": name}

_chat_locks_guard = threading.Lock()
_chat_locks = {}


def chat_lock(chat_id):
    """One Claude call at a time per chat; different chats run in parallel."""
    with _chat_locks_guard:
        return _chat_locks.setdefault(chat_id, threading.Lock())


def new_name(sessions, base):
    name, suffix = base, 2
    while name in sessions:
        name, suffix = f"{base}-{suffix}", suffix + 1
    return name


def new_session():
    provider = next(iter(config.PROVIDERS))
    return {
        "provider": provider,
        "model": config.PROVIDERS[provider]["models"][0],
        "session": None,  # claude session id, set after the first answer
        "msgs": 0,
        "mode": config.CFG.get("permission_mode", "default"),
        "allow": list(config.CFG.get("allowed_tools", [])),
    }


def get_chat(chat_id):
    return chats.setdefault(chat_id, {"sessions": {}, "current": None})


def current_session(chat_id):
    chat = get_chat(chat_id)
    if not chat["sessions"]:
        chat["sessions"]["1"] = new_session()
        chat["current"] = "1"
    return chat["sessions"][chat["current"]]
