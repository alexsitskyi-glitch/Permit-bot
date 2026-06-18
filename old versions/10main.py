import os, json, logging, requests, asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

TOKEN            = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])
WEBAPP_URL       = os.environ["WEBAPP_URL"].strip()

DIFY_API_KEY = os.environ.get("DIFY_API_KEY", "")
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Hi! I'm your OS/OW assistant.*\n\n"
        "📝 To submit a permit request: /permit\n"
        "❓ To ask about state restrictions or curfews — just message me in *private chat*.\n\n"
        "_Example: What are the GA restrictions this weekend?_",
        parse_mode="Markdown"
    )

# ── /permit ───────────────────────────────────────────────────────────────────

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEBAPP_URL.startswith("https://"):
        await update.message.reply_text(
            "⚠️ Web App URL is not configured. Contact your admin."
        )
        return

    try:
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
    except Exception as e:
        logging.error(f"permit() error: {e}")
        # Fallback: plain URL button if WebApp domain isn't whitelisted in BotFather
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📋  Open Permit Form", url=WEBAPP_URL)
        ]])
        await update.message.reply_text(
            "🚛 *New Permit Request*\n\n"
            "Tap the button below to open the form.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

# ── Helpers ───────────────────────────────────────────────────────────────────

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

# ── Mini App data receiver ────────────────────────────────────────────────────

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

    try:
        await context.bot.send_message(
            chat_id=PERMITS_GROUP_ID,
            text=permit_text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Failed to send to group {PERMITS_GROUP_ID}: {e}")
        await update.message.reply_text(
            "⚠️ Could not forward to the permits group. Check PERMITS_GROUP_ID and that the bot is an admin there."
        )
        return

    await update.message.reply_text(
        "✅  *Your request has been submitted!*\n\n"
        "_Here is a copy of what was sent to dispatch:_\n\n"
        + permit_text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

# ── Dify AI ───────────────────────────────────────────────────────────────────

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

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

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

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type":  "application/json",
    }

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
        await update.message.reply_text(answer)

    except Exception as e:
        logging.error(f"Dify API error: {e}")
        await update.message.reply_text(
            "⚠️ Could not reach the AI assistant. Please try again later."
        )

# ── Error handler ─────────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error: {context.error}", exc_info=context.error)

# ── main ──────────────────────────────────────────────────────────────────────

async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("permit", permit))
    app.add_handler(CommandHandler("info",   ask_dify))

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        ask_dify
    ))

    logging.info("Bot started.")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()   # run forever until Ctrl+C

if __name__ == "__main__":
    asyncio.run(main())
