"""Entry point: `python -m tg_harness [chat_id]` — long-polls Telegram.

chat_id is passed by telegram.restart() so the bot can say "restarted" in that chat.
"""
import sys, threading, time
from . import config, handlers, state, telegram


def in_background(handler, payload):
    def run():
        handler(payload)
        state.save()
    threading.Thread(target=run, daemon=True).start()


def main():
    state.load()
    try:  # cosmetic menu; a failure here (e.g. 429) must not crash-loop the bot
        handlers.set_commands()
    except Exception as error:
        print("setMyCommands failed:", error, file=sys.stderr)
    print(f"bot running, workdirs={config.WORKDIRS}", file=sys.stderr)

    restarted_from_chat = sys.argv[1] if len(sys.argv) > 1 else None
    if restarted_from_chat:
        try:
            telegram.say(int(restarted_from_chat), "Перезапущен ✅")
        except Exception as error:
            print("restart confirmation failed:", error, file=sys.stderr)

    while True:
        try:
            for update in telegram.tg("getUpdates", offset=telegram.offset, timeout=60):
                telegram.offset = update["update_id"] + 1
                if "message" in update:
                    in_background(handlers.handle, update["message"])
                elif "callback_query" in update:
                    in_background(handlers.handle_callback, update["callback_query"])
        except Exception as error:
            print("error:", error, file=sys.stderr)
            time.sleep(5)  # don't hammer Telegram on 429 / network outage


if __name__ == "__main__":
    main()
