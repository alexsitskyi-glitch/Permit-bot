import os, re, logging, requests, asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN            = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])

# ── НАСТРОЙКИ DIFY ИИ-АССИСТЕНТА ──────────────────────────────────────────────
DIFY_API_KEY     = os.environ.get("DIFY_API_KEY", "app-z9qO9ZtpSV8CDnGhUOhdfQB1")
DIFY_API_URL     = "https://api.dify.ai/v1/chat-messages"

# ── states ────────────────────────────────────────────────────────────────────
COMMODITY, WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER, ROUTE = range(9)

STATES_ORDER = [COMMODITY, WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER, ROUTE]
FIELDS_ORDER = ["commodity", "width", "height", "length", "weight", "steer", "drives", "trailer", "route"]

NAME_TO_STATE = {
    "COMMODITY": COMMODITY, "WIDTH": WIDTH,   "HEIGHT": HEIGHT, "LENGTH": LENGTH,
    "WEIGHT":    WEIGHT,    "STEER": STEER,   "DRIVES": DRIVES, "TRAILER": TRAILER,
    "ROUTE":     ROUTE,
}

FIELD_LABELS = {
    "commodity": "📦 Commodity",
    "width":     "📐 Width    ",
    "height":    "📐 Height   ",
    "length":    "📏 Length   ",
    "weight":    "⚖️  Weight   ",
    "steer":     "     Steer  ",
    "drives":    "     Drives ",
    "trailer":   "     Trailer",
    "route":     "🗺️  Route    ",
}

# Minimum feet for dimension fields (validation)
MIN_FEET = {"width": 8, "height": 11, "length": 29}

# ── Интеграция с Dify ИИ-Ассистентом (С ДИАГНОСТИКОЙ ОШИБОК) ───────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привет! Я твой OS/OW ассистент.*

"
        "📝 Чтобы оформить запрос на пермит, введи команду: /permit
"
        "❓ Чтобы узнать комендантский час (Curfew) или ограничения в штатах, "
        "просто напиши мне любой вопрос ниже.

"
        "_Пример: Какие ограничения в Джорджии на эти выходные?_",
        parse_mode="Markdown"
    )

async def ask_dify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    
    if query_text.startswith('/info'):
        query_text = query_text.replace('/info', '').strip()
        if not query_text:
            await update.message.reply_text(
                "❌ Пожалуйста, напишите свой вопрос после команды.\n_Пример: /info Комендантский час Иллинойс_", 
                parse_mode="Markdown"
            )
            return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "inputs": {},
        "query": query_text,
        "response_mode": "blocking",
        "user": f"tg_{update.effective_user.id}"
    }
    
    try:
        response = await asyncio.to_thread(
            requests.post, DIFY_API_URL, json=data, headers=headers, timeout=30
        )
        
        # 1. Проверяем статус-код ответа
        if response.status_code != 200:
            await update.message.reply_text(
                f"❌ *Ошибка сервера Dify!*\n"
                f"*Статус-код:* {response.status_code}\n"
                f"*Ответ сервера:* `{response.text}`",
                parse_mode="Markdown"
            )
            return

        result = response.json()
        
        # 2. Проверяем наличие ответа от ИИ
        if 'answer' in result:
            await update.message.reply_text(result['answer'])
        else:
            await update.message.reply_text(
                f"⚠️ *Dify ответил кодом 200, но внутри нет текста.*\n"
                f"*Полный JSON ответа:* `{result}`",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logging.error(f"Dify API Error: {e}")
        await update.message.reply_text(
            f"⚠️ *Ошибка в коде Python (Исключение):*\n"
            f"`{type(e).__name__}: {e}`", 
            parse_mode="Markdown"
        )


# ── step definitions ──────────────────────────────────────────────────────────
STEP_META = {
    COMMODITY: {
        "num": 1, "total": 6,
        "title": "Commodity",
        "hint":  "What are you hauling?\n_Example: Front loader, Enclosure, Dozer, Excavator, Generator_",
        "presets":    [],
        "back_fixed": None,
    },
    WIDTH: {
        "num": 2, "total": 6,
        "title": "Width",
        "hint":  "Tap *Legal* or type a custom value\n_Minimum: 8′ — e.g. 11'4"_",
        "presets":    [("✅  Legal", "val:width:Legal")],
        "back_fixed": "go:COMMODITY",
    },
    HEIGHT: {
        "num": 3, "total": 6,
        "title": "Height",
        "hint":  "Tap *Legal* or type a custom value\n_Minimum: 11′ — e.g. 14'2"_",
        "presets":    [("✅  Legal", "val:height:Legal")],
        "back_fixed": "go:WIDTH",
    },
    LENGTH: {
        "num": 4, "total": 6,
        "title": "Length in the well",
        "hint":  "Tap *Not extended* or type a custom value\n_Minimum: 29′ — e.g. 41'_",
        "presets":    [("✅  Not extended", "val:length:Not extended")],
        "back_fixed": "go:HEIGHT",
    },
    WEIGHT: {
        "num": 5, "total": 6,
        "title": "Weight",
        "hint":  "Choose a category or type a custom value:",
        "presets": [
            ("✅  Legal",       "val:weight:Legal"),
            ("⚠️  Overweight",  "val:weight:Overweight"),
        ],
        "back_fixed": "go:LENGTH",
    },
    STEER: {
        "num": None, "total": None,
        "title": "Steer axle weight",
        "hint":  "Enter weight in lbs _(e.g. 13100)_",
        "presets":    [],
        "back_fixed": "go:WEIGHT",
    },
    DRIVES: {
        "num": None, "total": None,
        "title": "Drives axle weight",
        "hint":  "Enter weight in lbs _(e.g. 35000)_",
        "presets":    [],
        "back_fixed": "go:STEER",
    },
    TRAILER: {
        "num": None, "total": None,
        "title": "Trailer axle weight",
        "hint":  "Enter weight in lbs _(e.g. 41000)_",
        "presets":    [],
        "back_fixed": "go:DRIVES",
    },
    ROUTE: {
        "num": 6, "total": 6,
        "title": "Route Preference",
        "hint":  "Choose an option, or type your preferred route below:",
        "presets": [
            ("🔀  No preference",          "val:route:No preference"),
            ("✏️  Suggest my own route",   "val:route:__custom__"),
        ],
        "back_fixed": None,
    },
}

def parse_feet(text: str):
    m = re.match(r"(\d+(?:\.\d+)?)", text.strip())
    return float(m.group(1)) if m else None


def validate_dimension(field: str, text: str):
    minimum = MIN_FEET.get(field)
    if not minimum:
        return True, ""
    feet = parse_feet(text)
    if feet is None:
        return False, f"⚠️ *Invalid value.* Please enter a number _(e.g. `{minimum}'`)_."
    if feet < minimum:
        return (
            False,
            f"⚠️ *Below minimum.* {field.title()} must be at least *{minimum}'*."
            f" Please enter a larger value.",
        )
    return True, ""


def progress_bar(current: int, total: int) -> str:
    filled = round(current / total * 10)
    return "█" * filled + "░" * (10 - filled)


def D(char="─", n=30) -> str:
    return char * n


def build_header(state: int) -> str:
    meta = STEP_META[state]
    if meta["num"]:
        return (
            f"🚛  *PERMIT REQUEST*\n"
            f"`{progress_bar(meta['num'], meta['total'])}` · Step {meta['num']} of {meta['total']}\n"
            f"{D()}\n"
        )
    return f"🚛  *PERMIT REQUEST* —  Axle Weights\n{D()}\n"


def build_summary(data: dict) -> str:
    lines = []
    for field in FIELDS_ORDER:
        if field in data:
            lines.append(f"`{FIELD_LABELS[field]}:` *{data[field]}*")
    if not lines:
        return ""
    return "\n".join(lines) + f"\n{D()}\n"


def get_back(state: int, data: dict):
    if state == ROUTE:
        return "go:TRAILER" if data.get("weight", "").lower() == "overweight" else "go:WEIGHT"
    return STEP_META[state]["back_fixed"]


def build_keyboard(state: int, data: dict) -> InlineKeyboardMarkup | None:
    meta = STEP_META[state]
    rows = []

    if meta["presets"]:
        if state == ROUTE:
            for label, cb in meta["presets"]:
                rows.append([InlineKeyboardButton(label, callback_data=cb)])
        else:
            rows.append([InlineKeyboardButton(label, callback_data=cb)
                         for label, cb in meta["presets"]])

    back = get_back(state, data)
    if back:
        rows.append([InlineKeyboardButton("← Back  /  ✏️ Edit", callback_data=back)])

    return InlineKeyboardMarkup(rows) if rows else None


def build_step_text(state: int, data: dict) -> str:
    meta = STEP_META[state]
    return build_header(state) + build_summary(data) + f"*{meta['title']}*\n{meta['hint']}"


async def show_step(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    text = build_step_text(state, context.user_data)
    kb   = build_keyboard(state, context.user_data)
    q    = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return state


async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await show_step(update, context, COMMODITY)


async def get_commodity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["commodity"] = update.message.text.strip().title()
    return await show_step(update, context, WIDTH)


async def get_width(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ok, err = validate_dimension("width", text)
    if not ok:
        await update.message.reply_text(err, parse_mode="Markdown")
        return WIDTH
    context.user_data["width"] = text
    return await show_step(update, context, HEIGHT)


async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ok, err = validate_dimension("height", text)
    if not ok:
        await update.message.reply_text(err, parse_mode="Markdown")
        return HEIGHT
    context.user_data["height"] = text
    return await show_step(update, context, LENGTH)


async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ok, err = validate_dimension("length", text)
    if not ok:
        await update.message.reply_text(err, parse_mode="Markdown")
        return LENGTH
    context.user_data["length"] = text
    return await show_step(update, context, WEIGHT)


async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["weight"] = update.message.text.strip()
    if update.message.text.strip().lower() == "overweight":
        return await show_step(update, context, STEER)
    return await show_step(update, context, ROUTE)


async def get_steer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["steer"] = update.message.text.strip()
    return await show_step(update, context, DRIVES)


async def get_drives(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drives"] = update.message.text.strip()
    return await show_step(update, context, TRAILER)


async def get_trailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trailer"] = update.message.text.strip()
    return await show_step(update, context, ROUTE)


async def get_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["route"] = update.message.text.strip()
    await send_permit(update, context)
    return ConversationHandler.END


FIELD_TO_NEXT = {
    "commodity": WIDTH, "width": HEIGHT, "height": LENGTH,
    "length": WEIGHT, "steer": DRIVES, "drives": TRAILER,
}

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    if data.startswith("val:"):
        _, field, value = data.split(":", 2)

        if value == "__custom__":
            await query.answer()
            back = get_back(ROUTE, context.user_data)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=back)]]) if back else None
            text = (
                build_header(ROUTE)
                + build_summary(context.user_data)
                + "*Route Preference*\n"
                  "Type your preferred route below:\n"
                  "_Example: I-10 W → TX-18 → US-285_"
            )
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
            return ROUTE

        context.user_data[field] = value

        if field == "weight":
            if value.lower() == "overweight":
                return await show_step(update, context, STEER)
            return await show_step(update, context, ROUTE)

        if field == "route":
            await query.answer()
            await send_permit(update, context)
            return ConversationHandler.END

        return await show_step(update, context, FIELD_TO_NEXT[field])

    if data.startswith("go:"):
        target = NAME_TO_STATE[data.split(":")[1]]
        idx = STATES_ORDER.index(target)
        for f in FIELDS_ORDER[idx:]:
            context.user_data.pop(f, None)
        return await show_step(update, context, target)


def calc_gross(data: dict):
    try:
        total = sum(
            int(re.sub(r"\D", "", data.get(ax, "") or ""))
            for ax in ("steer", "drives", "trailer")
        )
        return f"{total:,} lbs"
    except (ValueError, TypeError):
        return None


def build_permit_text(data: dict, driver_name: str, origin: str) -> str:
    is_ow = data.get("weight", "").lower() == "overweight"
    gross = calc_gross(data) if is_ow else None

    weight_block = f"⚖️  Weight:    {data.get('weight', '—')}"
    if is_ow:
        weight_block += (
            f"\n     Steer:    {data.get('steer',   '—')} lbs"
            f"\n     Drives:   {data.get('drives',  '—')} lbs"
            f"\n     Trailer:  {data.get('trailer', '—')} lbs"
        )
        if gross:
            weight_block += f"\n{D()}\n⚖️  Gross Weight:  *{gross}*"

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


async def send_permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data  = context.user_data
    query = update.callback_query

    user   = query.from_user    if query else update.message.from_user
    chat   = query.message.chat if query else update.message.chat
    origin = chat.title or "Direct message"

    permit_text = build_permit_text(data, user.full_name, origin)

    await context.bot.send_message(
        chat_id=PERMITS_GROUP_ID,
        text=permit_text,
        parse_mode="Markdown",
    )

    driver_text = (
        "✅  *Your request has been submitted\!*\n\n"
        "_We'll get back to you shortly.:_\n\n"
        + permit_text
    )

    if query:
        await query.edit_message_text(driver_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            driver_text,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌  *Request cancelled.*\nType /permit any time to start over.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def main():
    app = Application.builder().token(TOKEN).build()

    def h(fn):
        return [
            MessageHandler(filters.TEXT & ~filters.COMMAND, fn),
            CallbackQueryHandler(handle_button),
        ]

    conv = ConversationHandler(
        entry_points=[CommandHandler("permit", permit)],
        states={
            COMMODITY: h(get_commodity),
            WIDTH:     h(get_width),
            HEIGHT:    h(get_height),
            LENGTH:    h(get_length),
            WEIGHT:    h(get_weight),
            STEER:     h(get_steer),
            DRIVES:    h(get_drives),
            TRAILER:   h(get_trailer),
            ROUTE:     h(get_route),
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("info", ask_dify))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        ask_dify
    ))

    app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
