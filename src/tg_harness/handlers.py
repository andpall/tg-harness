"""Bot commands, messages and inline-button callbacks."""
import json, os, sys, threading, time
from . import claude, config, state, telegram, voice

RETRY_AFTER_GRANT = "Разрешение на {tool} выдано. Повтори то, что не получилось из-за прав, и продолжай."


def describe(session):
    return f"{session['provider']} / {session['model']}, права: {session['mode']}, папка: {session['workdir']}"


def allowed_tools_text(session):
    return ", ".join(session["allow"]) or "—"


# --- commands: each takes (chat_id, arg) ---

def cmd_new(chat_id, arg):
    chat = state.get_chat(chat_id)
    name = state.new_name(chat["sessions"], state.clean_name(arg) or str(len(chat["sessions"]) + 1))
    chat["sessions"][name] = state.new_session()
    chat["current"] = name
    telegram.say(chat_id, f"Сессия «{name}». {describe(chat['sessions'][name])}")


def show_sessions(chat_id):
    state.current_session(chat_id)  # recreates the default session if the last one was deleted
    chat = state.get_chat(chat_id)
    message_counts = {name: session.get("msgs", 0) for name, session in chat["sessions"].items()}
    telegram.picker(chat_id, "/sessions", list(chat["sessions"]), chat["current"], "Переключиться на сессию:",
                    delete_cmd="/delsession", counts=message_counts, rename_cmd="/renamesession",
                    footer=[{"text": "➕ Новая сессия", "callback_data": "/new"}])


def cmd_sessions(chat_id, arg):
    chat = state.get_chat(chat_id)
    if arg not in chat["sessions"]:
        return show_sessions(chat_id)
    chat["current"] = arg
    telegram.say(chat_id, f"Сессия «{arg}». {describe(chat['sessions'][arg])}")


def cmd_delete_session(chat_id, arg):
    chat = state.get_chat(chat_id)
    if arg not in chat["sessions"]:
        return
    del chat["sessions"][arg]
    if chat["current"] == arg:
        chat["current"] = next(iter(chat["sessions"]), None)
    show_sessions(chat_id)


def cmd_rename_session(chat_id, arg):
    chat = state.get_chat(chat_id)
    if arg not in chat["sessions"]:
        return
    chat["renaming"] = arg  # the next plain text message becomes the new name
    telegram.say(chat_id, f"Пришли новое имя для сессии «{arg}».")


def finish_rename(chat_id, old_name, text):
    chat = state.get_chat(chat_id)
    if old_name not in chat["sessions"]:
        return telegram.say(chat_id, f"Сессии «{old_name}» уже нет.")
    new = state.rename_session(chat, old_name, text)
    telegram.say(chat_id, f"Сессия «{old_name}» теперь «{new}».")


def cmd_provider(chat_id, arg):
    session = state.current_session(chat_id)
    if arg not in config.PROVIDERS:
        return telegram.picker(chat_id, "/provider", list(config.PROVIDERS), session["provider"], "Выбери провайдера:")
    session.update(provider=arg, model=config.PROVIDERS[arg]["models"][0])
    telegram.say(chat_id, f"Провайдер: {arg}, модель: {session['model']}")


def cmd_model(chat_id, arg):
    session = state.current_session(chat_id)
    models = config.PROVIDERS[session["provider"]]["models"]
    if arg not in models:
        return telegram.picker(chat_id, "/model", models, session["model"], f"Модель ({session['provider']}):")
    session["model"] = arg
    telegram.say(chat_id, f"Модель: {arg}")


def cmd_mode(chat_id, arg):
    session = state.current_session(chat_id)
    if arg not in config.MODES:
        title = (f"Режим прав (сейчас {session['mode']}).\n"
                 f"Разрешено всегда: {allowed_tools_text(session)}\n"
                 "/allow <Tool> — добавить, /allow reset — очистить")
        return telegram.picker(chat_id, "/mode", config.MODES, session["mode"], title)
    session["mode"] = arg
    telegram.say(chat_id, f"Права: {arg}. Действует со следующего сообщения, контекст сохраняется.")


def cmd_workdir(chat_id, arg):
    session = state.current_session(chat_id)
    if arg not in config.WORKDIRS:
        return telegram.picker(chat_id, "/workdir", list(config.WORKDIRS), session["workdir"], "Рабочая папка:")
    if arg == session["workdir"]:
        return telegram.say(chat_id, f"Папка уже {arg}.")
    # claude keeps session history per directory, so --resume would not find it in the new one
    session.update(workdir=arg, session=None, msgs=0)
    telegram.say(chat_id, f"Папка: {arg} ({config.WORKDIRS[arg]}). Контекст сессии начат заново.")


def cmd_settings(chat_id, arg):
    buttons = [[{"text": label, "callback_data": cmd}] for label, cmd in config.SETTINGS_MENU.items()]
    telegram.say(chat_id, "Настройки:", json.dumps({"inline_keyboard": buttons}))


def cmd_clear(chat_id, arg):
    session = state.current_session(chat_id)
    session.update(session=None, msgs=0)
    telegram.say(chat_id, "Контекст сессии очищен.")


def cmd_allow(chat_id, arg):
    session = state.current_session(chat_id)
    if arg == "reset":
        session["allow"] = []
    elif arg and arg not in session["allow"]:
        session["allow"].append(arg)
    telegram.say(chat_id, f"Разрешено всегда: {allowed_tools_text(session)}")


def cmd_restart(chat_id, arg):
    telegram.say(chat_id, "Перезапускаюсь...")
    telegram.restart(chat_id)


COMMANDS = {
    "/start": cmd_new,
    "/new": cmd_new,
    "/sessions": cmd_sessions,
    "/delsession": cmd_delete_session,
    "/renamesession": cmd_rename_session,
    "/provider": cmd_provider,
    "/model": cmd_model,
    "/mode": cmd_mode,
    "/workdir": cmd_workdir,
    "/clear": cmd_clear,
    "/allow": cmd_allow,
    "/restart": cmd_restart,
    "/settings": cmd_settings,
}
# inline buttons that just apply a choice; "/allow" buttons are handled separately (grant + retry)
PICKER_COMMANDS = {"/sessions", "/delsession", "/renamesession", "/provider", "/model", "/mode", "/workdir"}
# buttons that run with no argument: "/new" starts a session, "/restart" just runs,
# the pickers among them (/mode, /model, /provider) open their own menu instead of applying a choice
MENU_COMMANDS = {"/new", "/mode", "/model", "/provider", "/restart"}


def command(chat_id, cmd, arg):
    """Run a bot command. Returns False if it is not ours, so the text goes to Claude."""
    handler = COMMANDS.get(cmd)
    if handler is None:
        return False
    handler(chat_id, arg)
    return True


def set_commands():
    telegram.tg("setMyCommands", commands=json.dumps([
        {"command": "new", "description": "Новая сессия"},
        {"command": "sessions", "description": "Переключить сессию"},
        {"command": "model", "description": "Выбрать модель"},
        {"command": "provider", "description": "Выбрать провайдера"},
        {"command": "mode", "description": "Режим прав"},
        {"command": "workdir", "description": "Рабочая папка сессии"},
        {"command": "clear", "description": "Очистить контекст сессии"},
        {"command": "allow", "description": "Разрешить инструмент: /allow WebFetch"},
        {"command": "restart", "description": "Перезапустить бота"},
        {"command": "settings", "description": "Права, модель, провайдер, рестарт"},
    ]))


# --- talking to Claude ---

def permission_keyboard(tools):
    # Telegram caps callback_data at 64 bytes; longer tool names get only the typed /allow hint
    buttons = [[{"text": f"✅ Разрешить {tool}", "callback_data": f"/allow {tool}"}]
               for tool in tools if len(f"/allow {tool}".encode()) <= 64]
    return json.dumps({"inline_keyboard": buttons})


def run(chat_id, prompt):
    session = state.current_session(chat_id)  # taken now: switching sessions later must not redirect this message
    lock = state.session_lock(session)
    if lock.locked():
        telegram.say(chat_id, f"⏳ Сессия «{state.session_name(chat_id, session)}» занята, сообщение в очереди.")
    with lock, telegram.typing(chat_id):
        answer, denied_tools = claude.ask_claude(session, prompt)
    if len(state.get_chat(chat_id)["sessions"]) > 1:  # answers from parallel sessions interleave in one chat
        answer = f"[{state.session_name(chat_id, session)}]\n{answer}"
    parts = telegram.chunks(answer)
    for part in parts[:-1]:
        telegram.say(chat_id, part)
    if not denied_tools:
        return telegram.say(chat_id, parts[-1])
    hint = (f"\n\n🔒 Нужны права: {', '.join(denied_tools)}\n"
            "Нажми кнопку — разрешу и повторю. Или /allow <Tool>, /mode.")
    telegram.say(chat_id, parts[-1][:3500] + hint, permission_keyboard(denied_tools))


# --- Telegram updates ---

def log_incoming(message):
    kind = "voice" if "voice" in message else "photo" if "photo" in message else "text"
    print(f"[{time.strftime('%H:%M:%S')}] thread={threading.current_thread().name} "
          f"recv chat={message['chat']['id']} kind={kind} content={message.get('text', message.get('caption', f'<{kind}>'))!r}",
          file=sys.stderr, flush=True)


def handle_voice(chat_id, file_id):
    try:
        with telegram.typing(chat_id):
            text = voice.transcribe(file_id)
    except Exception as error:
        return telegram.say(chat_id, f"Не разобрал голосовое: {error}")
    run(chat_id, f"Voice message: *{text}*")


def handle_photo(chat_id, message):
    file_id = message["photo"][-1]["file_id"]  # last entry is the largest size
    try:
        path = telegram.save_file(file_id, ".jpg")
    except Exception as error:
        return telegram.say(chat_id, f"Не скачал картинку: {error}")
    caption = message.get("caption", "")
    prompt = f"Прислали картинку, посмотри её: {path}\n{caption}".strip()
    try:
        run(chat_id, prompt)
    finally:
        os.remove(path)


def handle(message):
    chat_id, user_id = message["chat"]["id"], message["from"]["id"]
    log_incoming(message)
    if user_id not in config.ALLOWED:
        return telegram.say(chat_id, f"Not allowed. Your id: {user_id}", "")
    if "voice" in message:
        return handle_voice(chat_id, message["voice"]["file_id"])
    if "photo" in message:
        return handle_photo(chat_id, message)

    raw_text = message.get("text", "")
    text = config.BUTTONS.get(raw_text, raw_text)  # reply-keyboard buttons map to commands
    if not text:
        return
    renaming = state.get_chat(chat_id).pop("renaming", None)  # any command cancels a pending rename
    if renaming and not text.startswith("/"):
        return finish_rename(chat_id, renaming, text)
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        if command(chat_id, cmd.split("@")[0], arg.strip()):
            return
    run(chat_id, text)


def handle_callback(callback):
    telegram.tg("answerCallbackQuery", callback_query_id=callback["id"])
    if callback["from"]["id"] not in config.ALLOWED or "message" not in callback:
        return
    cmd, _, arg = callback.get("data", "").partition(" ")
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    if not arg and cmd in MENU_COMMANDS:  # a bare command tapped from "⚙️ Настройки" or "➕ Новая сессия"
        telegram.tg("deleteMessage", chat_id=chat_id, message_id=message_id)
        return command(chat_id, cmd, "")
    if not arg:
        return
    if cmd in PICKER_COMMANDS:  # a picker message is just a menu, gone once a choice is made
        telegram.tg("deleteMessage", chat_id=chat_id, message_id=message_id)
        command(chat_id, cmd, arg)
    elif cmd == "/allow":  # button under a permission denial: grant, then retry; keep the answer, drop the keyboard
        telegram.tg("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                    reply_markup=json.dumps({"inline_keyboard": []}))
        command(chat_id, cmd, arg)
        run(chat_id, RETRY_AFTER_GRANT.format(tool=arg))
