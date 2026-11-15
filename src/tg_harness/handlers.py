"""Bot commands, messages and inline-button callbacks."""
import json, sys, threading, time
from . import claude, config, state, telegram, voice

RETRY_AFTER_GRANT = "Разрешение на {tool} выдано. Повтори то, что не получилось из-за прав, и продолжай."


def describe(session):
    return f"{session['provider']} / {session['model']}, права: {session['mode']}"


def allowed_tools_text(session):
    return ", ".join(session["allow"]) or "—"


# --- commands: each takes (chat_id, arg) ---

def cmd_new(chat_id, arg):
    chat = state.get_chat(chat_id)
    name = state.new_name(chat["sessions"], (arg or str(len(chat["sessions"]) + 1))[:20])
    chat["sessions"][name] = state.new_session()
    chat["current"] = name
    telegram.say(chat_id, f"Сессия «{name}». {describe(chat['sessions'][name])}")


def show_sessions(chat_id):
    state.current_session(chat_id)  # recreates the default session if the last one was deleted
    chat = state.get_chat(chat_id)
    message_counts = {name: session.get("msgs", 0) for name, session in chat["sessions"].items()}
    telegram.picker(chat_id, "/sessions", list(chat["sessions"]), chat["current"], "Переключиться на сессию:",
                    delete_cmd="/delsession", counts=message_counts)


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
    "/provider": cmd_provider,
    "/model": cmd_model,
    "/mode": cmd_mode,
    "/allow": cmd_allow,
    "/restart": cmd_restart,
}
# inline buttons that just apply a choice; "/allow" buttons are handled separately (grant + retry)
PICKER_COMMANDS = {"/sessions", "/delsession", "/provider", "/model", "/mode"}


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
        {"command": "allow", "description": "Разрешить инструмент: /allow WebFetch"},
        {"command": "restart", "description": "Перезапустить бота"},
    ]))


# --- talking to Claude ---

def permission_keyboard(tools):
    # Telegram caps callback_data at 64 bytes; longer tool names get only the typed /allow hint
    buttons = [[{"text": f"✅ Разрешить {tool}", "callback_data": f"/allow {tool}"}]
               for tool in tools if len(f"/allow {tool}".encode()) <= 64]
    return json.dumps({"inline_keyboard": buttons})


def run(chat_id, prompt):
    with telegram.typing(chat_id):
        answer, denied_tools = claude.ask_claude(state.current_session(chat_id), prompt)
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
    kind = "voice" if "voice" in message else "text"
    print(f"[{time.strftime('%H:%M:%S')}] thread={threading.current_thread().name} "
          f"recv chat={message['chat']['id']} kind={kind} content={message.get('text', '<voice>')!r}",
          file=sys.stderr, flush=True)


def handle_voice(chat_id, file_id):
    try:
        with telegram.typing(chat_id):
            text = voice.transcribe(file_id)
    except Exception as error:
        return telegram.say(chat_id, f"Не разобрал голосовое: {error}")
    with state.chat_lock(chat_id):
        run(chat_id, f"Voice message: *{text}*")


def handle(message):
    chat_id, user_id = message["chat"]["id"], message["from"]["id"]
    log_incoming(message)
    if user_id not in config.ALLOWED:
        return telegram.say(chat_id, f"Not allowed. Your id: {user_id}", "")
    if "voice" in message:
        return handle_voice(chat_id, message["voice"]["file_id"])

    raw_text = message.get("text", "")
    text = config.BUTTONS.get(raw_text, raw_text)  # reply-keyboard buttons map to commands
    if not text:
        return
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        if command(chat_id, cmd.split("@")[0], arg.strip()):
            return
    with state.chat_lock(chat_id):
        run(chat_id, text)


def handle_callback(callback):
    telegram.tg("answerCallbackQuery", callback_query_id=callback["id"])
    if callback["from"]["id"] not in config.ALLOWED or "message" not in callback:
        return
    cmd, _, arg = callback.get("data", "").partition(" ")
    if not arg:
        return
    chat_id = callback["message"]["chat"]["id"]
    if cmd in PICKER_COMMANDS:  # handlers validate arg against config
        command(chat_id, cmd, arg)
    elif cmd == "/allow":  # button under a permission denial: grant, then retry
        command(chat_id, cmd, arg)
        with state.chat_lock(chat_id):
            run(chat_id, RETRY_AFTER_GRANT.format(tool=arg))
