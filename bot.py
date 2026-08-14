import logging
import os

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from database import ensure_admin, init_db
from handlers import callback, documents, messages, on_startup, start


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN or BOT_TOKEN before starting the bot."
        )

    init_db()
    ensure_admin()

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .post_init(on_startup)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, documents))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(CallbackQueryHandler(callback))

    logging.info("Bot is running...")
    # Keep retrying when Telegram is temporarily unreachable instead of exiting.
    app.run_polling(bootstrap_retries=-1)


if __name__ == "__main__":
    main()
