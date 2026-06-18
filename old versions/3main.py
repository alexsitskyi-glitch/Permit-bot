import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]
PERMITS_GROUP_ID = int(os.environ["PERMITS_GROUP_ID"])

# ── states ────────────────────────────────────────────────────────────────────
COMMODITY, WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER = range(8)

STATES_ORDER  = [COMMODITY, WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER]
FIELDS_ORDER  = ["commodity", "width", "height", "length", "weight", "steer", "drives", "trailer"]
NAME_TO_STATE = {
    "COMMODITY": COMMODITY, "WIDTH": WIDTH, "HEIGHT": HEIGHT, "LENGTH": LENGTH,
    "WEIGHT": WEIGHT, "STEER": STEER, "DRIVES": DRIVES, "TRAILER": TRAILER,
}

FIELD_LABELS = {
    "commodity": "📦 Commodity",
    "width":     "📐 Width",
    "height":    "📐 Height",
    "length":    "📏 Length",
    "weight":    "⚖️  Weight",
    "steer":     "     Steer",
    "drives":    "     Drives",
    "trailer":   "     Trailer",
}

# ── step definitions ──────────────────────────────────────────────────────────
# total_steps counts only the main 5 steps (commodity + 4 dimensions/weight),
# axle sub-steps are shown separately in the UI

STEP_META = {
    COMMODITY: {
        "num": 1, "total": 5,
        "title": "Commodity",
        "hint": "What are you hauling?\n_Example: Front loader, Excavator, Steel beam_",
        "presets": [],
        "back": None,
    },
    WIDTH: {
        "num": 2, "total": 5,
        "title": "Width",
        "hint": "Tap *Legal* or type a custom value _(e.g. 14'6\")_",
        "presets": [("Legal", "val:width:Legal")],
        "back": "go:COMMODITY",
    },
    HEIGHT: {
        "num": 3, "total": 5,
        "title": "Height",
        "hint": "Tap *Legal* or type a custom value _(e.g. 13'6\")_",
        "presets": [("Legal", "val:height:Legal")],
        "back": "go:WIDTH",
    },
    LENGTH: {
        "num": 4, "total": 5,
        "title": "Length in the well",
        "hint": "Tap *Standard* or type a custom value _(e.g. 75')_",
        "presets": [("Standard", "val:length:Standard")],
        "back": "go:HEIGHT",
    },
    WEIGHT: {
        "num": 5, "total": 5,
        "title": "Weight",
        "hint": "Choose a category or type a custom value:",
        "presets": [
            ("Legal", "val:weight:Legal"),
            ("Overweight", "val:weight:Overweight"),
        ],
        "back": "go:LENGTH",
    },
    STEER: {
        "num": None, "total": None,
        "title": "Steer axle weight",
        "hint": "Enter weight in lbs _(e.g. 20000)_",
        "presets": [],
        "back": "go:WEIGHT",
    },
    DRIVES: {
        "num": None, "total": None,
        "title": "Drives axle weight",
        "hint": "Enter weight in lbs _(e.g. 34000)_",
        "presets": [],
        "back": "go:STEER",
    },
    TRAILER: {
        "num": None, "total": None,
        "title": "Trailer axle weight",
        "hint": "Enter weight in lbs _(e.g. 40000)_",
        "presets": [],
        "back": "go:DRIVES",
    },
}

# ── UI helpers ────────────────────────────────────────────────────────────────

def progress_bar(current: int, total: int, width: int = 10) -> str:
    filled = round(current / total * width)
    return "█" * filled + "░" * (width - filled)


def build_header(state: int) -> str:
    meta = STEP_META[state]
    if meta["num"] is not None:
        bar = progress_bar(meta["num"], meta["total"])
        return (
            f"🚛  *PERMIT REQUEST*\n"
            f"`{bar}` · Step {meta['num']} of {meta['total']}\n"
            f"{'─' * 28}\n"
        )
    else:
        # Axle sub-steps
        return (
            f"🚛  *PERMIT REQUEST*  ·  Axle Weights\n"
            f"{'─' * 28}\n"
        )


def build_summary(data: dict) -> str:
    lines = []
    for field in FIELDS_ORDER:
        if field in data:
            val = data[field]
            lines.append(f"`{FIELD_LABELS[field]}:` *{val}*")
    if not lines:
        return ""
    return "\n".join(lines) + "\n" + f"{'─' * 28}\n"


def build_keyboard(state: int) -> InlineKeyboardMarkup | None:
    meta = STEP_META[state]
    rows = []

    if meta["presets"]:
        rows.append([
            InlineKeyboardButton(f"  {label}  ", callback_data=cb)
            for label, cb in meta["presets"]
        ])

    if meta["back"]:
        rows.append([InlineKeyboardButton("← Back  /  ✏️ Edit", callback_data=meta["back"])])

    return InlineKeyboardMarkup(rows) if rows else None


def build_message(state: int, data: dict) -> str:
    meta = STEP_META[state]
    header  = build_header(state)
    summary = build_summary(data)
    prompt  = f"*{meta['title']}*\n{meta['hint']}"
    return header + summary + prompt


# ── send / edit helper ────────────────────────────────────────────────────────

async def show_step(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    text = build_message(state, context.user_data)
    kb   = build_keyboard(state)
    q    = update.callback_query

    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    return state


# ── entry ─────────────────────────────────────────────────────────────────────

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await show_step(update, context, COMMODITY)


# ── text-input handlers ───────────────────────────────────────────────────────

async def get_commodity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["commodity"] = update.message.text.strip().title()
    return await show_step(update, context, WIDTH)

async def get_width(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["width"] = update.message.text.strip()
    return await show_step(update, context, HEIGHT)

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["height"] = update.message.text.strip()
    return await show_step(update, context, LENGTH)

async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["length"] = update.message.text.strip()
    return await show_step(update, context, WEIGHT)

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["weight"] = update.message.text.strip()
    if update.message.text.strip().lower() == "overweight":
        return await show_step(update, context, STEER)
    await send_permit(update, context)
    return ConversationHandler.END

async def get_steer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["steer"] = update.message.text.strip()
    return await show_step(update, context, DRIVES)

async def get_drives(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drives"] = update.message.text.strip()
    return await show_step(update, context, TRAILER)

async def get_trailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trailer"] = update.message.text.strip()
    await send_permit(update, context)
    return ConversationHandler.END


# ── button callback ───────────────────────────────────────────────────────────

NEXT_AFTER = {
    "commodity": WIDTH, "width": HEIGHT, "height": LENGTH,
    "length": WEIGHT, "steer": DRIVES, "drives": TRAILER,
}

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    if data.startswith("val:"):
        _, field, value = data.split(":", 2)
        context.user_data[field] = value

        if field == "weight":
            if value.lower() == "overweight":
                return await show_step(update, context, STEER)
            await query.answer()
            await send_permit(update, context)
            return ConversationHandler.END

        if field == "trailer":
            await query.answer()
            await send_permit(update, context)
            return ConversationHandler.END

        return await show_step(update, context, NEXT_AFTER[field])

    if data.startswith("go:"):
        target_state = NAME_TO_STATE[data.split(":")[1]]
        idx = STATES_ORDER.index(target_state)
        for field in FIELDS_ORDER[idx:]:
            context.user_data.pop(field, None)
        return await show_step(update, context, target_state)


# ── gross weight ──────────────────────────────────────────────────────────────

def calc_gross_weight(data: dict) -> str | None:
    """Sum steer + drives + trailer if all are present and numeric."""
    try:
        total = (
            int("".join(filter(str.isdigit, data.get("steer",   "")))) +
            int("".join(filter(str.isdigit, data.get("drives",  "")))) +
            int("".join(filter(str.isdigit, data.get("trailer", ""))))
        )
        return f"{total:,} lbs"
    except (ValueError, TypeError):
        return None


# ── send permit ───────────────────────────────────────────────────────────────

def divider(char: str = "─", n: int = 30) -> str:
    return char * n

async def send_permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data  = context.user_data
    query = update.callback_query

    user = (query.from_user  if query else update.message.from_user)
    chat = (query.message.chat if query else update.message.chat)

    # Weight block
    is_overweight = data["weight"].lower() == "overweight"
    if is_overweight:
        gross = calc_gross_weight(data)
        axle_block = (
            f"\n"
            f"     Steer:    {data.get('steer',   '—')} lbs\n"
            f"     Drives:   {data.get('drives',  '—')} lbs\n"
            f"     Trailer:  {data.get('trailer', '—')} lbs\n"
            + (f"{divider()}\n⚖️  Gross Weight:  *{gross}*" if gross else "")
        )
    else:
        axle_block = ""

    msg = (
        f"🚛  *NEW PERMIT REQUEST*\n"
        f"{divider('═')}\n"
        f"👤  Driver:    {user.full_name}\n"
        f"📍  Origin:    {chat.title or 'Direct message'}\n"
        f"{divider()}\n"
        f"📦  Commodity: {data.get('commodity', '—')}\n"
        f"{divider()}\n"
        f"📐  Width:     {data['width']}\n"
        f"📐  Height:    {data['height']}\n"
        f"📏  Length:    {data['length']}\n"
        f"{divider()}\n"
        f"⚖️   Weight:    {data['weight']}"
        f"{axle_block}\n"
        f"{divider('═')}"
    )

    await context.bot.send_message(
        chat_id=PERMITS_GROUP_ID,
        text=msg,
        parse_mode="Markdown",
    )

    success = (
        "✅  *Request submitted!*\n\n"
        "Your permit request has been sent to the dispatch team.\n"
        "We'll get back to you shortly."
    )
    if query:
        await query.edit_message_text(success, parse_mode="Markdown")
    else:
        await update.message.reply_text(success, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


# ── cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌  Request cancelled.\nType /permit any time to start a new one.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    def handlers(text_fn):
        return [
            MessageHandler(filters.TEXT & ~filters.COMMAND, text_fn),
            CallbackQueryHandler(handle_button),
        ]

    conv = ConversationHandler(
        entry_points=[CommandHandler("permit", permit)],
        states={
            COMMODITY: handlers(get_commodity),
            WIDTH:     handlers(get_width),
            HEIGHT:    handlers(get_height),
            LENGTH:    handlers(get_length),
            WEIGHT:    handlers(get_weight),
            STEER:     handlers(get_steer),
            DRIVES:    handlers(get_drives),
            TRAILER:   handlers(get_trailer),
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
