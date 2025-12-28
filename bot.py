import logging
import asyncio
import re
import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# EDIT THESE
# =========================
BOT_TOKEN = os.getenv("8400569898:AAH5s3bRm7BiC-tSHcrIOG1hjbSOaNKG_kc")
ADMIN_CHAT_ID = 8021775847# your Telegram chat ID (number only)

# Your services
SERVICES = {
    "yt_premium": {"name": "YouTube Premium", "price": 500},
    "adobe": {"name": "Adobe", "price": 250},
    "chatgpt_1m": {"name": "ChatGPT 1 Month", "price": 1},
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# ---------- Keyboards ----------
def services_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, s in SERVICES.items():
        rows.append([
            InlineKeyboardButton(
                f"⭐ {s['name']} — {s['price']} Stars",
                callback_data=f"service:{key}"
            )
        ])
    return InlineKeyboardMarkup(rows)


def pay_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay Now", callback_data="pay_now")]
    ])


def continue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I've Paid (Continue)", callback_data="i_paid")]
    ])


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Please choose the service you want to purchase "
        "(prices are in Telegram Stars ⭐):",
        reply_markup=services_keyboard()
    )


async def service_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    service_key = query.data.split(":", 1)[1]
    service = SERVICES.get(service_key)

    if not service:
        await query.message.reply_text("❌ Service not found. Please use /start again.")
        return

    context.user_data["service_key"] = service_key
    context.user_data["service_name"] = service["name"]
    context.user_data["service_price"] = service["price"]

    await query.message.reply_text(
        f"✅ You selected: *{service['name']}*\n"
        f"💰 Price: *{service['price']} Stars*\n\n"
        "Click **Pay Now** to continue with payment:",
        reply_markup=pay_keyboard(),
        parse_mode="Markdown"
    )


async def pay_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    service_key = context.user_data.get("service_key")
    if not service_key:
        await query.message.reply_text("❌ Please select a service first. Use /start.")
        return

    service = SERVICES[service_key]
    prices = [LabeledPrice(label=service["name"], amount=service["price"])]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=service["name"],
        description="Service payment via Telegram Stars.",
        payload=f"order:{service_key}",
        provider_token="",   # MUST be empty for Stars
        currency="XTR",      # Telegram Stars currency
        prices=prices,
        need_email=False,    # we ask for email after payment
    )


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sp = update.message.successful_payment

    context.user_data["paid"] = True
    context.user_data["paid_amount"] = sp.total_amount
    context.user_data["charge_id"] = sp.telegram_payment_charge_id

    await update.message.reply_text(
        "✅ Payment successful!\n\n"
        "Click the button below to continue and provide your email:",
        reply_markup=continue_keyboard()
    )


async def i_paid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get("paid"):
        await query.message.reply_text("❌ No payment detected yet.")
        return

    context.user_data["awaiting_email"] = True

    await query.message.reply_text(
        "📧 Please enter your email address so we can send you the activation:"
    )


def is_valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


async def email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_email"):
        return

    email = update.message.text.strip()
    if not is_valid_email(email):
        await update.message.reply_text(
            "❌ Invalid email. Please enter a valid email (example: name@gmail.com)"
        )
        return

    context.user_data["awaiting_email"] = False
    context.user_data["email"] = email

    await update.message.reply_text(
        "✅ Thank you!\n"
        "Your activation will be sent to your email shortly."
    )

    # Notify admin
    user = update.effective_user
    service_name = context.user_data.get("service_name")
    service_price = context.user_data.get("service_price")
    paid_amount = context.user_data.get("paid_amount")

    admin_text = (
        "🆕 NEW ORDER (PAID)\n\n"
        f"Service: {service_name}\n"
        f"Price: {service_price} Stars\n"
        f"Paid: {paid_amount} Stars\n"
        f"Email: {email}\n\n"
        f"Customer: {user.full_name}\n"
        f"Username: @{user.username if user.username else '(no username)'}\n"
        f"User ID: {user.id}"
    )

    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Type /start to begin.")


# ---------- App ----------
def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(service_select_handler, pattern=r"^service:"))
    app.add_handler(CallbackQueryHandler(pay_now_handler, pattern=r"^pay_now$"))

    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    app.add_handler(CallbackQueryHandler(i_paid_handler, pattern=r"^i_paid$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    return app


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_app()
    application.run_polling()
