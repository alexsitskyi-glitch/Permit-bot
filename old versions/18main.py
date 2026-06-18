import os, json, logging, requests, asyncio, sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, ReplyKeyboardRemove, KeyboardButton, \
    ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ChatMemberHandler
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TOKEN            = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])
WEBAPP_URL       = os.environ["WEBAPP_URL"].strip().rstrip("/")
WELCOME_URL      = os.environ.get("WELCOME_URL", WEBAPP_URL + "/welcome.html").strip()
DIFY_API_KEY     = os.environ.get("DIFY_API_KEY", "")
DIFY_API_URL     = "https://api.dify.ai/v1/chat-messages"
ADMIN_ID         = int(os.environ.get("ADMIN_ID", "0"))

# ── Database ──────────────────────────────────────────────────────────────────

DB = "stats.db"

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT,
                user_id    INTEGER,
                user_name  TEXT,
                group_id   INTEGER,
                group_name TEXT,
                ts         TEXT
            )""")
        c.commit()

def log_event(etype, user_id, user_name, group_id=None, group_name=None):
    try:
        with sqlite3.connect(DB) as c:
            c.execute(
                "INSERT INTO events (type,user_id,user_name,group_id,group_name,ts) VALUES(?,?,?,?,?,?)",
                (etype, user_id, str(user_name), group_id, str(group_name or ""), datetime.utcnow().isoformat())
            )
            c.commit()
    except Exception as e:
        logging.warning(f"DB log error: {e}")

def get_stats():
    try:
        with sqlite3.connect(DB) as c:
            now   = datetime.utcnow()
            day   = (now - timedelta(days=1)).isoformat()
            week  = (now - timedelta(days=7)).isoformat()
            month = (now - timedelta(days=30)).isoformat()
            def q(sql, *args): return c.execute(sql, args).fetchone()[0]

            return {
                "total_permits": q("SELECT COUNT(*) FROM events WHERE type='permit'"),
                "today_permits": q("SELECT COUNT(*) FROM events WHERE type='permit' AND ts > ?", day),
                "week_permits":  q("SELECT COUNT(*) FROM events WHERE type='permit' AND ts > ?", week),
                "month_permits": q("SELECT COUNT(*) FROM events WHERE type='permit' AND ts > ?", month),
                "total_info":    q("SELECT COUNT(*) FROM events WHERE type='info'"),
                "week_info":     q("SELECT COUNT(*) FROM events WHERE type='info' AND ts > ?", week),
                "total_drivers": q("SELECT COUNT(DISTINCT user_id) FROM events WHERE type='permit'"),
                "total_groups":  q("SELECT COUNT(DISTINCT group_id) FROM events WHERE type='welcome'"),
                "top_drivers":   c.execute("SELECT user_name, COUNT(*) n FROM events WHERE type='permit' GROUP BY user_id ORDER BY n DESC LIMIT 5").fetchall(),
                "top_groups":    c.execute("SELECT group_name, COUNT(*) n FROM events WHERE type='permit' AND group_name!='' GROUP BY group_id ORDER BY n DESC LIMIT 5").fetchall(),
            }
    except Exception as e:
        logging.error(f"Stats error: {e}")
        return None

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == "permit":
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📋  Open Permit Form", web_app=WebAppInfo(url=WEBAPP_URL))]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            "🚛 *New Permit Request*\n\nTap the button below to open the form.",
            parse_mode="Markdown", reply_markup=keyboard
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
            InlineKeyboardButton("📋  Open Permit Form", url=f"https://t.me/{bot_username}?start=permit")
        ]])
        await update.message.reply_text("🚛 Tap the button below to open the permit form.", reply_markup=keyboard)
        return
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📋  Open Permit Form", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "🚛 *New Permit Request*\n\nTap the button below to open the form.",
        parse_mode="Markdown", reply_markup=keyboard
    )

# ── /setup ────────────────────────────────────────────────────────────────────

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ This command works only in groups.")
        return
    bot_username = (await context.bot.get_me()).username
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚛  GET PERMIT", url=f"https://t.me/{bot_username}?start=permit")
    ]])
    msg = await update.message.reply_text(
        "📋 *PERMIT REQUEST*\n\nTap the button below to submit a new OS/OW permit request to dispatch.",
        parse_mode="Markdown", reply_markup=keyboard
    )
    try:
        await context.bot.pin_chat_message(chat_id=update.message.chat_id, message_id=msg.message_id, disable_notification=True)
        await update.message.delete()
    except Exception as e:
        logging.warning(f"Could not pin: {e}")

# ── /stats ────────────────────────────────────────────────────────────────────

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Access denied.")
        return
    s = get_stats()
    if not s:
        await update.message.reply_text("⚠️ Could not load stats.")
        return
    top_d = "\n".join([f"  {i+1}. {n} — {c} requests" for i,(n,c) in enumerate(s["top_drivers"])]) or "  No data yet"
    top_g = "\n".join([f"  {i+1}. {n} — {c} requests" for i,(n,c) in enumerate(s["top_groups"])]) or "  No data yet"
    await update.message.reply_text(
        f"📊 *PERMIT BOT STATISTICS*\n{'═'*28}\n\n"
        f"🚛 *Permit Requests*\n"
        f"  Today:      {s['today_permits']}\n"
        f"  This week:  {s['week_permits']}\n"
        f"  This month: {s['month_permits']}\n"
        f"  All time:   {s['total_permits']}\n\n"
        f"❓ *Info Queries*\n"
        f"  This week:  {s['week_info']}\n"
        f"  All time:   {s['total_info']}\n\n"
        f"👥 *Unique drivers:* {s['total_drivers']}\n"
        f"📍 *Active groups:* {s['total_groups']}\n\n"
        f"🏆 *Top Drivers*\n{top_d}\n\n"
        f"📍 *Top Groups*\n{top_g}\n\n"
        f"_Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_",
        parse_mode="Markdown"
    )

# ── Welcome when bot is added to group ───────────────────────────────────────

async def welcome_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when the bot's own membership status changes in any chat."""
    new_member = update.my_chat_member.new_chat_member
    chat       = update.my_chat_member.chat

    # Trigger only when bot is freshly added as member or admin
    if new_member.status not in ("member", "administrator"):
        return

    if chat.type not in ("group", "supergroup"):
        return

    chat_id        = chat.id
    bot_username   = (await context.bot.get_me()).username
    get_permit_url = f"https://t.me/{bot_username}?start=permit"

    log_event("welcome", new_member.user.id, new_member.user.username, chat_id, chat.title)
    logging.info(f"Bot added to group: {chat.title} ({chat_id})")

    # Welcome message — user taps the button to open the Web App guide
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text="📖  View Quick Guide",
            web_app=WebAppInfo(url=WELCOME_URL)
        )],
        [InlineKeyboardButton(
            text="🚛  GET PERMIT",
            url=get_permit_url
        )]
    ])

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="👋 *OS/OW Permit Bot is here!*\n\n"
                 "I help drivers submit oversize/overweight permit requests "
                 "to dispatch in seconds.\n\n"
                 "Tap *View Quick Guide* to see how it works 👇",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Could not send welcome: {e}")
        return

    # Auto-pin GET PERMIT button
    try:
        pin_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚛  GET PERMIT", url=get_permit_url)
        ]])
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="📌 *Tap below to submit a permit request:*",
            parse_mode="Markdown",
            reply_markup=pin_kb
        )
        await context.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=msg.message_id,
            disable_notification=True
        )
    except Exception as e:
        logging.warning(f"Could not auto-pin: {e}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def D(char="─", n=28): return char * n

def build_permit_text(data, driver_name, origin):
    is_ow = data.get("weight", "").lower() == "overweight"
    wb = f"⚖️  Weight:    {data.get('weight','—')}"
    if is_ow:
        wb += (f"\n     Steer:    {data.get('steer','—')} lbs"
               f"\n     Drives:   {data.get('drives','—')} lbs"
               f"\n     Trailer:  {data.get('trailer','—')} lbs")
        if data.get("gross"):
            wb += f"\n{D()}\n⚖️  Gross:  *{data['gross']}*"
    return (
        f"🚛  *NEW PERMIT REQUEST*\n{D('═')}\n"
        f"👤  Driver:    {driver_name}\n"
        f"📍  Group:     {origin}\n{D()}\n"
        f"📦  Commodity: {data.get('commodity','—')}\n{D()}\n"
        f"📐  Width:     {data.get('width','—')}\n"
        f"📐  Height:    {data.get('height','—')}\n"
        f"📏  Length:    {data.get('length','—')}\n{D()}\n"
        f"{wb}\n{D()}\n"
        f"🗺️  Route:     {data.get('route','—')}\n{D('═')}"
    )

# ── Mini App data receiver ────────────────────────────────────────────────────

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw  = update.message.web_app_data.data
    user = update.message.from_user
    chat = update.message.chat
    try:
        data = json.loads(raw)
    except Exception:
        await update.message.reply_text("⚠️ Could not read form data. Please try again.")
        return

    origin = chat.title or "Direct message"
    permit_text = build_permit_text(data, user.full_name, origin)
    log_event("permit", user.id, user.full_name, chat.id, origin)

    try:
        await context.bot.send_message(chat_id=PERMITS_GROUP_ID, text=permit_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send to permits group {PERMITS_GROUP_ID}: {e}")
        await update.message.reply_text(f"⚠️ Could not reach the permits group.\nError: {e}")
        return

    await update.message.reply_text(
        "✅  *Request submitted!*\n\n_Copy sent to dispatch:_\n\n" + permit_text,
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

# ── Dify AI ───────────────────────────────────────────────────────────────────

async def ask_dify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    if query_text.lower().startswith("/info"):
        query_text = query_text[5:].strip()
        if not query_text:
            await update.message.reply_text("❓ Example: /info curfew Illinois")
            return

    log_event("info", update.effective_user.id, update.effective_user.full_name)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    user_key = f"dify_{update.effective_user.id}"
    payload  = {"inputs": {}, "query": query_text, "response_mode": "blocking",
                "user": f"tg_{update.effective_user.id}"}
    if context.bot_data.get(user_key):
        payload["conversation_id"] = context.bot_data[user_key]

    try:
        r = await asyncio.to_thread(
            requests.post, DIFY_API_URL, json=payload,
            headers={"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"},
            timeout=60
        )
        result = r.json()
        if result.get("conversation_id"):
            context.bot_data[user_key] = result["conversation_id"]
        await update.message.reply_text(result.get("answer") or "⚠️ No answer returned.")
    except Exception as e:
        logging.error(f"Dify error: {e}")
        await update.message.reply_text("⚠️ Could not reach AI assistant. Try again later.")

# ── Error handler ─────────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Error: {context.error}", exc_info=context.error)

# ── main ──────────────────────────────────────────────────────────────────────

async def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("permit", permit))
    app.add_handler(CommandHandler("setup",  setup))
    app.add_handler(CommandHandler("info",   ask_dify))
    app.add_handler(CommandHandler("stats",  stats))

    # ← KEY FIX: ChatMemberHandler tracks bot being added/removed from groups
    app.add_handler(ChatMemberHandler(welcome_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, ask_dify
    ))

    logging.info("Bot started.")
    async with app:
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.start()
        await app.updater.start_polling(
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
                "my_chat_member",
                "web_app_data",
            ]
        )
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())