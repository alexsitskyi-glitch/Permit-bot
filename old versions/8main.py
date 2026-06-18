import os, re, json, logging, requests, asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN            = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])
WEBAPP_URL       = os.environ["WEBAPP_URL"]          # e.g. https://yourname.github.io/permit-app

DIFY_API_KEY = os.environ.get("DIFY_API_KEY", "app-z9qO9ZtpSV8CDnGhUOhdfQB1")
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Hi! I'm your OS/OW assistant.*\n\n"
        "📝 To submit a permit request: /permit\n"
        "❓ To ask about state restrictions or curfews — just send me a message in *private chat*.\n\n"
        "_Example: What are the GA restrictions this weekend?_",
        parse_mode="Markdown"
    )

# ── /permit — opens Mini App ──────────────────────────────────────────────────

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📋  Open Permit Form",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]])
    await update.message.reply_text(
        "🚛 *New Permit Request*\n\n"
        "Tap the button below to open the form.\n"
        "Fill in all the details and press *Submit*.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ── Receive data from Mini App ────────────────────────────────────────────────

def D(char="─", n=30) -> str:
    return char * n

def build_permit_text(data: dict, driver_name: str, origin: str) -> str:
    is_ow = data.get("weight", "").lower() == "overweight"

    weight_block = f"⚖️  Weight:    {data.get('weight', '—')}"
    if is_ow:
        weight_block += (
            f"\n     Steer:    {data.get('steer',   '—')} lbs"
            f"\n     Drives:   {data.get('drives',  '—')} lbs"
            f"\n     Trailer:  {data.get('trailer', '—')} lbs"
        )
        if data.get("gross"):
            weight_block += f"\n{D()}\n⚖️  Gross Weight:  *{data['gross']}*"

    return (
        f"🚛  *NEW PERMIT REQUEST*\n"
        f"{D('═')}\n"
        f"👤  Driver:     {driver_name}\n"
        f"📍  Origin:     {origin}\n"
        f"{D()}\n"
        f"📦  Commodity:  {data.get('commodity', '—')}\n"
        f"{D()}\n"
        f"📐  Width:      {data.get('width',  '—')}\n"
        f"📐  Height:     {data.get('height', '—')}\n"
        f"📏  Length:     {data.get('length', '—')}\n"
        f"{D()}\n"
        f"{weight_block}\n"
        f"{D()}\n"
        f"🗺️  Route:      {data.get('route', '—')}\n"
        f"{D('═')}"
    )

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw  = update.message.web_app_data.data
    user = update.message.from_user
    chat = update.message.chat

    try:
        data = json.loads(raw)
    except Exception:
        await update.message.reply_text("⚠️ Could not read the form data. Please try again.")
        return

    origin      = chat.title or "Direct message"
    permit_text = build_permit_text(data, user.full_name, origin)

    # Send to permits group
    await context.bot.send_message(
        chat_id=PERMITS_GROUP_ID,
        text=permit_text,
        parse_mode="Markdown",
    )

    # Confirm to driver
    driver_text = (
        "✅  *Your request has been submitted!*\n\n"
        "_Here is a copy of what was sent to dispatch:_\n\n"
        + permit_text
    )
    await update.message.reply_text(
        driver_text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

# ── Dify AI assistant ─────────────────────────────────────────────────────────

async def ask_dify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()

    if query_text.lower().startswith("/info"):
        query_text = query_text[5:].strip()
        if not query_text:
            await update.message.reply_text(
                "❓ Please add your question after the command.\n"
                "_Example: /info curfew Illinois_",
                parse_mode="Markdown"
            )
            return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    user_key = f"dify_conv_{update.effective_user.id}"
    conv_id  = context.bot_data.get(user_key)

    payload = {
        "inputs":        {},
        "query":         query_text,
        "response_mode": "blocking",
        "user":          f"tg_{update.effective_user.id}",
    }
    if conv_id:
        payload["conversation_id"] = conv_id

    try:
        response = await asyncio.to_thread(
            requests.post, DIFY_API_URL,
            json=payload, headers=headers, timeout=60
        )
        result = response.json()

        new_conv_id = result.get("conversation_id")
        if new_conv_id:
            context.bot_data[user_key] = new_conv_id

        answer = result.get("answer") or "⚠️ No answer returned from the knowledge base."

        try:
            await update.message.reply_text(answer, allow_sending_without_reply=True)
        except Exception:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=answer)

    except Exception as e:
        logging.error(f"Dify API error: {e}")
        try:
            await update.message.reply_text(
                "⚠️ Could not reach the AI assistant. Please try again later.",
                allow_sending_without_reply=True
            )
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Could not reach the AI assistant. Please try again later."
            )

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("permit", permit))
    app.add_handler(CommandHandler("info", ask_dify))

    # Mini App form data
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    # Dify for private chat messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        ask_dify
    ))

    app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
