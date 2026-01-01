import logging
import asyncio
import re
import os
import time

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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Dummy HTTP server for Render ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        return

def start_dummy_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


# =========================
# EDIT THESE
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in Render Environment Variables.")
ADMIN_CHAT_ID = 8021775847  # your Telegram chat ID (number only)
SUPPORT_USERNAME = "wesamhm1"  # without @
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME}"
SUPPORT_COOLDOWN_SECONDS = 60 * 60  # 1 hour

# Your services (UPDATED PRICES)
SERVICES = {
    "disney_1m": {"name": "Disney+ 1 Month", "price": 150},
    "chatgpt_1m": {"name": "ChatGPT 1 Month", "price": 270},
    "yt_premium": {"name": "YouTube Premium 1 Month", "price": 270},
    "spotify_1m": {"name": "Spotify 1 Month", "price": 225},

    # 🔧 Test / Donation (for owner testing)
    "donation_1": {"name": "☕ Donation / Test Payment", "price": 1},
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


def support_keyboard_locked(remaining_seconds: int) -> InlineKeyboardMarkup:
    # Button stays locked (callback), so we can show a popup message if clicked
    mins = max(0, remaining_seconds) // 60
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔒 Contact Support (available in {mins} min)", callback_data="support_locked")]
    ])


def support_keyboard_unlocked() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Support", url=SUPPORT_URL)]
    ])


def format_mmss(seconds: int) -> str:
    seconds = max(0, seconds)
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


# ---------- Countdown job ----------
async def update_support_countdown(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data or {}

    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    start_ts = data.get("start_ts")

    if not (chat_id and message_id and start_ts):
        job.schedule_removal()
        return

    elapsed = int(time.time() - start_ts)
    remaining = SUPPORT_COOLDOWN_SECONDS - elapsed

    if remaining <= 0:
        # Unlock support
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=support_keyboard_unlocked()
            )
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(
                    "✅ Your order is still being processed.\n\n"
                    "If you did not receive the activation within the expected time, "
                    "you can now contact support below."
                ),
                reply_markup=support_keyboard_unlocked()
            )
        except Exception:
            # If edit fails (message changed/deleted), just stop job.
            pass

        job.schedule_removal()
        return

    # Update countdown text (every minute)
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "✅ Payment received successfully!\n\n"
                "⚙️ Your order is being processed\n"
                "📦 Preparing your activation...\n"
                "⏳ This usually takes a few minutes (up to 60 minutes).\n\n"
                "📧 Activation details will be sent to your email.\n\n"
                "⬇️⬇️⬇️\n"
                f"⏱ Support will be available in: {format_mmss(remaining)}"
            ),
            reply_markup=support_keyboard_locked(remaining)
        )
    except Exception:
        # If edit fails, stop to avoid spam/errors
        job.schedule_removal()


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


async def support_locked_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Calculate remaining from stored timestamp if available
    start_ts = context.user_data.get("support_start_ts")
    if not start_ts:
        await query.answer("Support will be available later.", show_alert=True)
        return

    remaining = SUPPORT_COOLDOWN_SECONDS - int(time.time() - start_ts)
    await query.answer(
        f"Please wait. Support will be available in {format_mmss(remaining)}.",
        show_alert=True
    )


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

    # --- Send processing message with countdown + locked support button ---
    start_ts = time.time()
    context.user_data["support_start_ts"] = start_ts

    processing_msg = await update.message.reply_text(
        "✅ Payment received successfully!\n\n"
        "⚙️ Your order is being processed\n"
        "📦 Preparing your activation...\n"
        "⏳ This usually takes a few minutes (up to 60 minutes).\n\n"
        "📧 Activation details will be sent to your email.\n\n"
        "⬇️⬇️⬇️\n"
        f"⏱ Support will be available in: {format_mmss(SUPPORT_COOLDOWN_SECONDS)}",
        reply_markup=support_keyboard_locked(SUPPORT_COOLDOWN_SECONDS)
    )

    # Start a repeating job to update countdown every 60 seconds
    # (It will unlock support automatically when time is over.)
    context.job_queue.run_repeating(
        update_support_countdown,
        interval=60,
        first=60,
        data={
            "chat_id": processing_msg.chat_id,
            "message_id": processing_msg.message_id,
            "start_ts": start_ts
        },
        name=f"support_cd_{update.effective_user.id}"
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

    # Support locked button handler
    app.add_handler(CallbackQueryHandler(support_locked_handler, pattern=r"^support_locked$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    return app


if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()

    asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_app()

    application.run_polling()



