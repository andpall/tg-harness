"""Thin wrappers over the Telegram Bot API."""
import json, os, sys, threading, urllib.parse, urllib.request
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


def picker(chat_id, cmd, options, current, title, delete_cmd=None, counts=None):
    """Inline keyboard: one row per option, ✅ on the current one, optional 🗑 button."""
    def row(option):
        label = ("✅ " if option == current else "") + option + (f" ({counts[option]})" if counts else "")
        buttons = [{"text": label, "callback_data": f"{cmd} {option}"}]
        if delete_cmd:
            buttons.append({"text": "🗑", "callback_data": f"{delete_cmd} {option}"})
        return buttons
    say(chat_id, title, json.dumps({"inline_keyboard": [row(option) for option in options]}))


@contextmanager
def typing(chat_id):
    """Show "typing..." until the block ends (Telegram drops the status after ~5s, so refresh it)."""
    stop = threading.Event()
    def refresh():
        while not stop.wait(4):
            tg("sendChatAction", chat_id=chat_id, action="typing")
    tg("sendChatAction", chat_id=chat_id, action="typing")
    threading.Thread(target=refresh, daemon=True).start()
    try:
        yield
    finally:
        stop.set()


def restart(chat_id):
    tg("getUpdates", offset=offset, timeout=0)  # ack the /restart update, else Telegram resends it forever
    # same cmdline as run.sh starts (so `run.sh stop` matches); chat_id gets the "restarted" message
    os.execv(sys.executable, [sys.executable, "-m", "tg_harness", str(chat_id)])
