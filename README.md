<div align="center">

# 📱 tg-harness

**Claude Code in Telegram — from your phone, on your own machine, with your own subscription.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-CLI-d97757)](https://docs.claude.com/en/docs/claude-code)
[![No dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-lightgrey)](pyproject.toml)
[![Boosty](https://img.shields.io/badge/Boosty-support-f15f2c)](https://boosty.to/andpall)

</div>

Send a task to the chat as text or a voice message. The bot runs `claude -p` in a working directory on your machine
and sends back the answer. Everyone hosts their own copy: your own Telegram bot, your own `claude`, your own subscription.

```
you ──► Telegram ──► tg-harness (your computer) ──► claude -p ──► reply in chat
```

## ⚡ Quick start

You need Python 3.11+ and `claude` installed and logged in.

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. Clone and start it — leave `TG_ALLOWED` empty for now:
   ```bash
   git clone https://github.com/andpall/tg-harness.git && cd tg-harness
   cp .env.example .env     # fill in TG_TOKEN
   ./run.sh start
   ```
3. Send your bot any message — it replies `Not allowed. Your id: 123456789`.
4. Put that id into `.env` (`TG_ALLOWED=123456789`) and restart: `./run.sh restart`. Done.

Details below.

## ✨ Features

- **Sessions.** Each chat has several sessions with preserved context: create, switch, delete.
- **Model and provider** are picked with buttons, per session. A provider is a set of environment variables
  for `claude` (Anthropic, Bedrock, Vertex, your own proxy).
- **Permissions.** When Claude hits a denied tool (WebFetch, Bash, …), a «✅ Разрешить X» ("Allow X") button appears
  under the reply. Tapping it allows the tool for the session and retries the request with context intact.
  The permission mode (`default` / `acceptEdits` / `plan` / `bypassPermissions`) is switched with a button.
- **Voice messages** are transcribed locally with faster-whisper.
- **Access** is limited to the Telegram users listed in `TG_ALLOWED` in `.env`.

> The bot's own interface (buttons and messages) is in Russian.

## 📋 Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.claude.com/en/docs/claude-code), installed and authenticated (`claude` on `PATH`)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## 📦 Installation

```bash
git clone https://github.com/andpall/tg-harness.git && cd tg-harness
python3 -m pip install faster-whisper "av<14"   # only needed for voice messages
cp .env.example .env                            # fill in TG_TOKEN and TG_ALLOWED
```

To find your Telegram user id, ask [@userinfobot](https://t.me/userinfobot)
or just message the bot: it replies to unknown users with `Not allowed. Your id: …`.

## ⚙️ Configuration

**`.env`** — secrets and the access list, never committed:

```
TG_TOKEN=123456:ABC...
# Telegram user ids allowed to use the bot, comma-separated
TG_ALLOWED=111111111,222222222
# any secrets referenced from config.json
PROXY_TOKEN=...
```

Comments in `.env` must be on their own line.

**`config.json`** — shared settings, kept in git:

| Field | Meaning |
|---|---|
| `workdir` | Directory Claude works in (relative to the repo root, or absolute) |
| `permission_mode` | Permission mode for new sessions |
| `allowed_tools` | Tools allowed by default in new sessions, e.g. `["WebFetch"]` |
| `claude_args` | Extra arguments for `claude` |
| `whisper_model` | Speech recognition model (default `medium`) |
| `providers` | Providers: environment variables + list of models. The first one is the default |

Example with several providers:

```json
"providers": {
  "anthropic": {"env": {}, "models": ["sonnet", "opus", "haiku"]},
  "bedrock":   {"env": {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"}, "models": ["sonnet"]},
  "proxy":     {"env": {"ANTHROPIC_BASE_URL": "https://my-proxy", "ANTHROPIC_AUTH_TOKEN": "$PROXY_TOKEN"},
                "models": ["my-model"]}
}
```

`$VAR` is substituted from `.env` or the environment.

## 🚀 Running

```bash
./run.sh start     # in the background; restarts 2 s after a crash
./run.sh log       # follow the log (bot.log)
./run.sh restart
./run.sh stop
```

The bot runs as long as your machine does. After a reboot, run `./run.sh start` again.

## 💬 Bot commands

| Button | Command | What it does |
|---|---|---|
| 🆕 Новая сессия | `/new [name]` | New session with default settings |
| 📂 Сессии | `/sessions` | List sessions: switch or delete |
| 🔐 Права | `/mode` | Session permission mode |
| 🤖 Модель | `/model` | Model of the current provider |
| 🔌 Провайдер | `/provider` | Provider (the model resets to the first one in its list) |
| ♻️ Рестарт бота | `/restart` | Restart the bot process (picks up new code) |
| — | `/allow <Tool>` | Allow a tool in the session; `/allow reset` clears the list |

Any other text, including commands the bot doesn't know such as `/compact`, goes to Claude.

## 🔒 Security

- Everyone in `TG_ALLOWED` can make Claude act on your machine. Add only people you trust.
- "Allow Bash" allows **any** terminal command in that session; `bypassPermissions` removes all restrictions.
- With `"workdir": "."` Claude can edit the bot's own code. To work on another project, point `workdir` at it.
- Sessions, models and permissions live in memory and are reset when the bot restarts.

## 🛠 Development

```bash
python3 -m pip install pytest
python3 -m pytest
```

Code structure and conventions are in [CLAUDE.md](CLAUDE.md) (in Russian).

## ☕ Support

tg-harness is free. If it saves you time, you can support its development ❤

- [Boosty](https://boosty.to/andpall)

## 📄 License

[MIT](LICENSE)
