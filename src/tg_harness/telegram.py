"""Thin wrappers over the Telegram Bot API."""
import json, os, sys, tempfile, threading, urllib.parse, urllib.request
from contextlib import contextmanager
from . import config

offset = 0  # next update to fetch; restart() acks it before exec


def tg(method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(config.API + method, data, timeout=70) as response:
        return json.load(response)["result"]


def say(chat_id, text, markup=config.KEYBOARD):
    tg("sendMessage", chat_id=chat_id, text=text, reply_markup=markup)


def chunks(text, size=4000):  # Telegram limit is 4096 chars per message
    return [text[start:start + size] for start in range(0, len(text), size)] or ["(empty)"]


def save_file(file_id, suffix):
    """Downloads a Telegram-hosted file (voice, photo, …) to a temp path; caller deletes it."""
    file_path = tg("getFile", file_id=file_id)["file_path"]
    url = f"https://api.telegram.org/file/bot{config.TOKEN}/{file_path}"
    with urllib.request.urlopen(url, timeout=70) as response:
        data = response.read()
    descriptor, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(descriptor, "wb") as file:
        file.write(data)
    return path


def picker(chat_id, cmd, options, current, title, delete_cmd=None, counts=None, rename_cmd=None, footer=None):
    """Inline keyboard: one row per option, ✅ on the current one, optional ✏️ and 🗑 buttons, footer row last."""
    def row(option):
        label = ("✅ " if option == current else "") + option + (f" ({counts[option]})" if counts else "")
        buttons = [{"text": label, "callback_data": f"{cmd} {option}"}]
        if rename_cmd:
            buttons.append({"text": "✏️", "callback_data": f"{rename_cmd} {option}"})
        if delete_cmd:
            buttons.append({"text": "🗑", "callback_data": f"{delete_cmd} {option}"})
        return buttons
    rows = [row(option) for option in options] + ([footer] if footer else [])
    say(chat_id, title, json.dumps({"inline_keyboard": rows}))


@contextmanager
def typing(chat_id):
    """Show "typing..." until the block ends (Telegram drops the status after ~5s, so refresh it)."""
    stop = threading.Event()
    def refresh():
        while not stop.wait(4):
            try:
                tg("sendChatAction", chat_id=chat_id, action="typing")
            except Exception as error:  # one network blip must not stop the indicator for the rest of a long run
                print("typing refresh failed:", error, file=sys.stderr)
    tg("sendChatAction", chat_id=chat_id, action="typing")
    threading.Thread(target=refresh, daemon=True).start()
    try:
        yield
    finally:
        stop.set()


def restart(chat_id):
    tg("getUpdates", offset=offset, timeout=0)  # ack the /restart update, else Telegram resends it forever
    # os.execv keeps this process's environment, so .env-sourced vars (setdefault'd once) would
    # never pick up edits made since startup unless we clear them before reloading .env
    for key in ("TG_TOKEN", "TG_ALLOWED", "TG_WORKDIR", "TG_EXTRA_WORKDIRS"):
        os.environ.pop(key, None)
    # same cmdline as run.sh starts (so `run.sh stop` matches); chat_id gets the "restarted" message
    os.execv(sys.executable, [sys.executable, "-m", "tg_harness", str(chat_id)])
