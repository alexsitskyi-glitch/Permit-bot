import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])

WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER = range(7)

def legal_keyboard():
    return ReplyKeyboardMarkup([["Legal"]], resize_keyboard=True, one_time_keyboard=True)

def weight_keyboard():
    return ReplyKeyboardMarkup([["Legal", "Overweight"]], resize_keyboard=True, one_time_keyboard=True)

def length_keyboard():
    return ReplyKeyboardMarkup([["Not extended"]], resize_keyboard=True, one_time_keyboard=True)

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📋 *New Permit Request*\n\n"
        "Step 1/4 — *Width*\n"
        "Tap *Legal* or type the value (e.g. 11'6\")",
        parse_mode="Markdown",
        reply_markup=legal_keyboard()
    )
    return WIDTH

async def get_width(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["width"] = update.message.text
    await update.message.reply_text(
        "Step 2/4 — *Height*\n"
        "Tap *Legal* or type the value (e.g. 13'9\")",
        parse_mode="Markdown",
        reply_markup=legal_keyboard()
    )
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["height"] = update.message.text
    await update.message.reply_text(
        "Step 3/4 — *Length in the well*\n"
        "Tap *Not extended* or type the value (e.g. 36')",
        parse_mode="Markdown",
        reply_markup=length_keyboard()
    )
    return LENGTH

async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["length"] = update.message.text
    await update.message.reply_text(
        "Step 4/4 — *Weight*\n"
        "Tap *Legal* or *Overweight*",
        parse_mode="Markdown",
        reply_markup=weight_keyboard()
    )
    return WEIGHT

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    context.user_data["weight"] = update.message.text

    if answer == "overweight":
        await update.message.reply_text(
            "Enter *Steer* axle weight (lbs):\nExample: 13200",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return STEER
    else:
        await send_permit(update, context)
        return ConversationHandler.END

async def get_steer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["steer"] = update.message.text
    await update.message.reply_text(
        "Enter *Drives* axle weight (lbs):\nExample: 35000",
        parse_mode="Markdown"
    )
    return DRIVES

async def get_drives(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drives"] = update.message.text
    await update.message.reply_text(
        "Enter *Trailer* axle weight (lbs):\nExample: 35000",
        parse_mode="Markdown"
    )
    return TRAILER

async def get_trailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trailer"] = update.message.text
    await send_permit(update, context)
    return ConversationHandler.END

async def send_permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    chat = update.message.chat
    user = update.message.from_user

    weight_line = f"⚖️ Weight: {data['weight']}"
    if data['weight'].lower() == "overweight":
        weight_line += (
            f"\n   • Steer: {data.get('steer', '—')}"
            f"\n   • Drives: {data.get('drives', '—')}"
            f"\n   • Trailer: {data.get('trailer', '—')}"
        )

    msg = (
        f"🚛 PERMIT REQUEST\n\n"
        f"👤 Driver: {user.full_name}\n"
        f"📍 Group: {chat.title
or 'Direct message'}\n\n"
        f"📐 Width: {data['width']}\n"
        f"📐 Height: {data['height']}\n"
        f"📏 Length in the well: {data['length']}\n"
        f"{weight_line}"
    )

    await context.bot.send_message(
        chat_id=PERMITS_GROUP_ID,
        text=msg,
        reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(
        "✅ Permit request submitted! We will process it shortly.",
        reply_markup=ReplyKeyboardRemove()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Request cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("permit", permit)],
        states={
            WIDTH:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_width)],
            HEIGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            LENGTH:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_length)],
            WEIGHT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            STEER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_steer)],
            DRIVES:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_drives)],
            TRAILER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_trailer)],
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