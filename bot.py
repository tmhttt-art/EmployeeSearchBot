import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from search import search_employee

# قراءة التوكن من متغير البيئة
TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 هلا بيك\n\n"
        "ارسل اسم الموظف حتى أبحث عنه."
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    result = search_employee(name)

    await update.message.reply_text(result)


def main():
    print("Starting bot...")

    app = Application.builder().token(TOKEN).build()

    # أمر /start
    app.add_handler(CommandHandler("start", start))

    # أي رسالة تعتبر بحث
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()