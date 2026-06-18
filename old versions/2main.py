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

WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER = range(7)

# Maps state int → field name and vice versa (for back-navigation)
STATE_TO_FIELD = {
    WIDTH: "width", HEIGHT: "height", LENGTH: "length",
    WEIGHT: "weight", STEER: "steer", DRIVES: "drives", TRAILER: "trailer",
}
FIELDS_ORDER = ["width", "height", "length", "weight", "steer", "drives", "trailer"]
STATES_ORDER = [WIDTH, HEIGHT, LENGTH, WEIGHT, STEER, DRIVES, TRAILER]

NAME_TO_STATE = {
    "WIDTH": WIDTH, "HEIGHT": HEIGHT, "LENGTH": LENGTH,
    "WEIGHT": WEIGHT, "STEER": STEER, "DRIVES": DRIVES, "TRAILER": TRAILER,
}

# ── step definitions ──────────────────────────────────────────────────────────

STEPS = {
    WIDTH: {
        "text": "Step 1/7 — *Width*\nTap *Legal* or type a custom value (e.g. `14'6\"`):",
        "presets": [("✅ Legal", "val:width:Legal")],
        "back": None,
    },
    HEIGHT: {
        "text": "Step 2/7 — *Height*\nTap *Legal* or type a custom value (e.g. `13'6\"`):",
        "presets": [("✅ Legal", "val:height:Legal")],
        "back": "go:WIDTH",
    },
    LENGTH: {
        "text": "Step 3/7 — *Length in the well*\nTap *Standard* or type a custom value (e.g. `75'`):",
        "presets": [("✅ Standard", "val:length:Standard")],
        "back": "go:HEIGHT",
    },
    WEIGHT: {
        "text": "Step 4/7 — *Weight*\nChoose or type a custom value:",
        "presets": [
            ("✅ Legal", "val:weight:Legal"),
            ("⚠️ Overweight", "val:weight:Overweight"),
        ],
        "back": "go:LENGTH",
    },
    STEER: {
        "text": "Step 5/7 — *Steer* axle weight (lbs)\nExample: `20000`",
        "presets": [],
        "back": "go:WEIGHT",
    },
    DRIVES: {
        "text": "Step 6/7 — *Drives* axle weight (lbs)\nExample: `34000`",
        "presets": [],
        "back": "go:STEER",
    },
    TRAILER: {
        "text": "Step 7/7 — *Trailer* axle weight (lbs)\nExample: `40000`",
        "presets": [],
        "back": "go:DRIVES",
    },
}

FIELD_LABELS = {
    "width":   "📐 Width",
    "height":  "📐 Height",
    "length":  "📏 Length",
    "weight":  "⚖️ Weight",
    "steer":   "  ↳ Steer",
    "drives":  "  ↳ Drives",
    "trailer": "  ↳ Trailer",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def build_summary(data: dict) -> str:
    lines = []
    for field in FIELDS_ORDER:
        if field in data:
            lines.append(f"{FIELD_LABELS[field]}: *{data[field]}*")
    if not lines:
        return ""
    return "📋 *Entered so far:*\n" + "\n".join(lines) + "\n\n"


def build_keyboard(state: int) -> InlineKeyboardMarkup:
    step = STEPS[state]
    rows = []
    if step["presets"]:
        rows.append([InlineKeyboardButton(label, callback_data=data)
                     for label, data in step["presets"]])
    if step["back"]:
        rows.append([InlineKeyboardButton("← Back / Edit", callback_data=step["back"])])
    return InlineKeyboardMarkup(rows) if rows else None


async def show_step(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    """Render a step — edits the message for callbacks, sends new one for text."""
    step = STEPS[state]
    text = build_summary(context.user_data) + step["text"]
    kb = build_keyboard(state)

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    return state


# ── entry point ───────────────────────────────────────────────────────────────

async def permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await show_step(update, context, WIDTH)


# ── text-input handlers ───────────────────────────────────────────────────────

async def get_width(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["width"] = update.message.text
    return await show_step(update, context, HEIGHT)

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["height"] = update.message.text
    return await show_step(update, context, LENGTH)

async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["length"] = update.message.text
    return await show_step(update, context, WEIGHT)

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["weight"] = update.message.text
    if update.message.text.strip().lower() == "overweight":
        return await show_step(update, context, STEER)
    await send_permit(update, context)
    return ConversationHandler.END

async def get_steer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["steer"] = update.message.text
    return await show_step(update, context, DRIVES)

async def get_drives(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drives"] = update.message.text
    return await show_step(update, context, TRAILER)

async def get_trailer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trailer"] = update.message.text
    await send_permit(update, context)
    return ConversationHandler.END


# ── button callback handler ───────────────────────────────────────────────────

NEXT_STATE = {
    "width": HEIGHT, "height": LENGTH, "length": WEIGHT,
    "steer": DRIVES, "drives": TRAILER,
}

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # ── preset value selected: val:field:value ────────────────────────────
    if data.startswith("val:"):
        _, field, value = data.split(":", 2)
        context.user_data[field] = value

        if field == "weight":
            if value.lower() == "overweight":
                return await show_step(update, context, STEER)
            else:
                await query.answer()
                await send_permit(update, context)
                return ConversationHandler.END

        if field == "trailer":
            await query.answer()
            await send_permit(update, context)
            return ConversationHandler.END

        return await show_step(update, context, NEXT_STATE[field])

    # ── back / edit: go:STATENAME ─────────────────────────────────────────
    if data.startswith("go:"):
        state_name = data.split(":")[1]
        target_state = NAME_TO_STATE[state_name]
        # Clear this field and all subsequent fields
        idx = STATES_ORDER.index(target_state)
        for field in FIELDS_ORDER[idx:]:
            context.user_data.pop(field, None)
        return await show_step(update, context, target_state)


# ── send permit to group ──────────────────────────────────────────────────────

async def send_permit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    query = update.callback_query

    if query:
        user = query.from_user
        chat = query.message.chat
    else:
        user = update.message.from_user
        chat = update.message.chat

    weight_line = f"⚖️ Weight: {data['weight']}"
    if data["weight"].lower() == "overweight":
        weight_line += (
            f"\n   • Steer: {data.get('steer', '—')}"
            f"\n   • Drives: {data.get('drives', '—')}"
            f"\n   • Trailer: {data.get('trailer', '—')}"
        )

    msg = (
        f"🚛 PERMIT REQUEST\n\n"
        f"👤 Driver: {user.full_name}\n"
        f"📍 Group: {chat.title or 'Direct message'}\n\n"
        f"📐 Width: {data['width']}\n"
        f"📐 Height: {data['height']}\n"
        f"📏 Length in the well: {data['length']}\n"
        f"{weight_line}"
    )

    await context.bot.send_message(chat_id=PERMITS_GROUP_ID, text=msg)

    success_text = "✅ Permit request submitted! We will process it shortly."
    if query:
        await query.edit_message_text(success_text)
    else:
        await update.message.reply_text(success_text, reply_markup=ReplyKeyboardRemove())


# ── cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Request cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    # Every state handles both text input AND inline button callbacks
    state_handlers = lambda text_handler: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler),
        CallbackQueryHandler(handle_button),
    ]

    conv = ConversationHandler(
        entry_points=[CommandHandler("permit", permit)],
        states={
            WIDTH:   state_handlers(get_width),
            HEIGHT:  state_handlers(get_height),
            LENGTH:  state_handlers(get_length),
            WEIGHT:  state_handlers(get_weight),
            STEER:   state_handlers(get_steer),
            DRIVES:  state_handlers(get_drives),
            TRAILER: state_handlers(get_trailer),
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
