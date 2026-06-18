import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

load_dotenv()

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])

WIDTH, HEIGHT, LENGTH, WEIGHT = range(4)

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Новая заявка на пермит\n\nВведи ширину груза (Width):\nПример: 14'6\""
    )
    return WIDTH

async def get_width(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["width"] = update.message.text
    await update.message.reply_text("Введи высоту (Height):\nПример: 13'6\"")
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["height"] = update.message.text
    await update.message.reply_text("Введи длину (Length):\nПример: 75'")
    return LENGTH

async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["length"] = update.message.text
    await update.message.reply_text("Введи вес (Weight) в lbs:\nПример: 80000")
    return WEIGHT

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["weight"] = update.message.text
    chat = update.message.chat
    user = update.message.from_user

    msg = (
        f"🚛 ЗАЯВКА НА ПЕРМИТ\n\n"
        f"👤 Водитель: {user.full_name}\n"
        f"📍 Группа: {chat.title or 'Личный чат'}\n\n"
        f"📐 Width: {context.user_data['width']}\n"
        f"📐 Height: {context.user_data['height']}\n"
        f"📏 Length: {context.user_data['length']}\n"
        f"⚖️ Weight: {context.user_data['weight']}"
    )

    await context.bot.send_message(chat_id=PERMITS_GROUP_ID, text=msg)
    await update.message.reply_text("✅ Заявка отправлена!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Заявка отменена.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("permit", permit)],
        states={
            WIDTH:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_width)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_length)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()