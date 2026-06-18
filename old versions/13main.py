import os, json, logging, requests, asyncio
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
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
    if context.args and context.args[0] == "permit":
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📋  Open Permit Form", web_app=WebAppInfo(url=WEBAPP_URL))]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            "🚛 *New Permit Request*\n\n"
            "Tap the button below to open the form.\n"
            "Fill in all the details and press *Submit*.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

    await update.message.reply_text(
        "👋 *Hi! I'm your OS/OW Permit Assistant.*\n\n"
        "📝 Submit a permit request: /permit\n"
        "❓ Ask about state restrictions anytime.",
        parse_mode="Markdown"
    )

# ── /permit ───────────────────────────────────────────────────────────────────

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEBAPP_URL.startswith("https://"):
        await update.message.reply_text("⚠️ Web App URL is not configured.")
        return

    if update.message.chat.type in ("group", "supergroup"):
        bot_username = (await context.bot.get_me()).username
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📋  Open Permit Form",
                url=f"https://t.me/{bot_username}?start=permit"
            )
        ]])
        await update.message.reply_text(
            "🚛 Tap the button below to open the permit form.",
            reply_markup=keyboard
        )
        return

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📋  Open Permit Form", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "🚛 *New Permit Request*\n\n"
        "Tap the button below to open the form.\n"
        "Fill in all the details and press *Submit*.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ── /setup ────────────────────────────────────────────────────────────────────

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ This command works only in groups.")
        return

    bot_username = (await context.bot.get_me()).username

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🚛  GET PERMIT",
            url=f"https://t.me/{bot_username}?start=permit"
        )
    ]])

    msg = await update.message.reply_text(
        "📋 *PERMIT REQUEST*\n\n"
        "Tap the button below to submit a new\n"
        "OS/OW permit request to dispatch.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    try:
        await context.bot.pin_chat_message(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            disable_notification=True
        )
        await update.message.delete()
    except Exception as e:
        logging.warning(f"Could not pin message: {e}")

# ── Welcome when bot is added to a group ─────────────────────────────────────

async def welcome_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when someone adds new members to a group — checks if the bot itself was added."""
    bot = await context.bot.get_me()
    added_ids = [m.id for m in update.message.new_chat_members]

    if bot.id not in added_ids:
        return  # Someone else was added, not our bot

    bot_username = bot.username

    welcome_text = (
        "👋 *Hey everyone! I'm your OS/OW Permit Assistant.*\n\n"
        "I help drivers submit oversize/overweight permit requests directly to dispatch — fast and easy.\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚛 *HOW TO REQUEST A PERMIT*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "*Step 1* — Tap the 📌 pinned *GET PERMIT* button at the top of this chat\n"
        "*(Admin needs to run /setup first to pin it)*\n\n"
        
        "*Step 2* — A form will open in private chat. Fill in:\n"
        "   📦 *Commodity* — what you're hauling\n"
        "      _e.g. Excavator, Front Loader, Crane_\n\n"
        "   📐 *Width* — Legal or custom value\n"
        "      _e.g. 14' 6\"_\n\n"
        "   📐 *Height* — Legal or custom value\n"
        "      _e.g. 13' 6\"_\n\n"
        "   📏 *Length in the well* — Standard or extended\n"
        "      _e.g. 53'_\n\n"
        "   ⚖️ *Weight* — Legal or Overweight\n"
        "      _If overweight, enter per-axle weights:_\n"
        "      _Steer: 13,100 · Drives: 35,000 · Trailer: 41,000_\n\n"
        "   🗺️ *Route* — No preference or your preferred route\n"
        "      _e.g. I-10 W → TX-18 → US-285_\n\n"
        
        "*Step 3* — Tap *Submit* — done! ✅\n"
        "Dispatch receives your request instantly.\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "❓ *ASK ABOUT STATE RESTRICTIONS*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "Message me privately and ask anything:\n"
        "   _• What are the curfews in Texas this weekend?_\n"
        "   _• Is travel allowed on GA highways Saturday?_\n"
        "   _• What's the max width without escort in Florida?_\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *COMMANDS*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "/permit — submit a new permit request\n"
        "/setup — pin the GET PERMIT button _(admin only)_\n"
        "/info — ask about state restrictions\n\n"
        
        f"💬 Or message me directly: @{bot_username}"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🚛  GET PERMIT",
            url=f"https://t.me/{bot_username}?start=permit"
        )
    ]])

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    # Auto-pin the welcome/button message
    try:
        msg = await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="📌 *Tap below to submit a permit request:*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await context.bot.pin_chat_message(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            disable_notification=True
        )
    except Exception as e:
        logging.warning(f"Could not auto-pin welcome message: {e}")

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
            "⚠️ Could not forward to the permits group. Check that the bot is an admin there."
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
    app.add_handler(CommandHandler("setup",  setup))
    app.add_handler(CommandHandler("info",   ask_dify))

    # Welcome when bot is added to a group
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_bot_added))

    # Mini App form submissions
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    # Dify for private chat messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        ask_dify
    ))

    logging.info("Bot started.")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
