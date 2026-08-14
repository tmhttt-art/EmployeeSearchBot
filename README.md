# EmployeeSearchBot

Telegram bot for employee lookup, user approvals, administration, statistics,
maintenance notifications, and Excel database updates.

## Environment variables

- `BOT_TOKEN` or `TELEGRAM_BOT_TOKEN`: Telegram bot token.
- `DATA_DIR`: Persistent data directory. On Render, point this to the mounted
  persistent disk (for example `/var/data`).

## Render

- Service type: Background Worker
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `python bot.py`
- Persistent disk mount path: `/var/data`
- Environment variable: `DATA_DIR=/var/data`
