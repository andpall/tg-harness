"""Per-chat sessions, kept in memory and mirrored to disk so a restart does not lose them."""
import json, os, sys, threading
from . import config

SESSIONS_FILE = config.ROOT / "sessions.json"

chats = {}  # chat_id -> {"sessions": {name: session}, "current": name}

_session_locks_guard = threading.Lock()
_session_locks = {}  # id(session dict) -> Lock; the dict stays alive while a run holds it


_save_lock = threading.Lock()


def save():
    """Called from every handler thread: one writer at a time, atomic replace so a kill mid-write keeps the old file."""
    with _save_lock:
        try:
            data = json.dumps(chats, ensure_ascii=False)
        except RuntimeError:  # shortcut: another thread changed chats mid-dump; the next handler's save catches up
            return
        temp_file = SESSIONS_FILE.with_suffix(".tmp")
        temp_file.write_text(data)
        os.replace(temp_file, SESSIONS_FILE)


def load():
    global chats
    if not SESSIONS_FILE.exists():
        return
    try:
        chats = {int(chat_id): chat for chat_id, chat in json.loads(SESSIONS_FILE.read_text()).items()}
    except ValueError as error:  # a broken file must not crash-loop the bot; start with no sessions instead
        print(f"{SESSIONS_FILE.name} unreadable, starting fresh:", error, file=sys.stderr)


def session_lock(session):
    """One Claude call at a time per session; other sessions and chats run in parallel."""
    with _session_locks_guard:
        return _session_locks.setdefault(id(session), threading.Lock())


def session_name(chat_id, session):
    """Looked up at answer time, so a rename during a long run shows the new name."""
    return next((name for name, candidate in get_chat(chat_id)["sessions"].items() if candidate is session), "?")


def new_name(sessions, base):
    name, suffix = base, 2
    while name in sessions:
        name, suffix = f"{base}-{suffix}", suffix + 1
    return name


def clean_name(text):
    """Session names go into callback_data (64 bytes including the command), so cap them at 40 bytes."""
    name = text.strip()[:20]
    while len(name.encode()) > 40:
        name = name[:-1]
    return name


def rename_session(chat, old_name, wanted):
    """Rename keeping the session's place in the list; returns the name actually used."""
    others = {name: session for name, session in chat["sessions"].items() if name != old_name}
    new = new_name(others, clean_name(wanted) or old_name)
    chat["sessions"] = {(new if name == old_name else name): session for name, session in chat["sessions"].items()}
    if chat["current"] == old_name:
        chat["current"] = new
    return new


def new_session():
    provider = next(iter(config.PROVIDERS))
    return {
        "provider": provider,
        "workdir": next(iter(config.WORKDIRS)),
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
