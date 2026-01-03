import logging
import asyncio
import os
import time
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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

# ================== BASIC SETUP ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

ADMIN_USER_ID = 8021775847
USDT_ADDRESS = "TTmfGLZXWNxQGfi7YymVGk4CGhCaP2Q88J"
USDT_NETWORK = "TRC20"

logging.basicConfig(level=logging.INFO)

# ================== SERVICES ==================
SERVICES = {
    "disney":  {"name": "Disney+ 1 Month",         "usd": "$5.49", "stars": 450},
    "chatgpt": {"name": "ChatGPT 1 Month",         "usd": "$5.99", "stars": 470},
    "yt":      {"name": "YouTube Premium 1 Month", "usd": "$5.99", "stars": 470},
    "spotify": {"name": "Spotify 1 Month",         "usd": "$4.99", "stars": 420},
}

ORDERS = {}

# ================== UTILS ==================
def is_admin(uid): return uid == ADMIN_USER_ID
def valid_email(e): return re.match(r"[^@]+@[^@]+\.[^@]+", e)

def order_id():
    return f"O{int(time.time())}"

# ================== KEYBOARDS ==================
def services_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{v['name']} — {v['usd']}", callback_data=f"svc:{k}")]
        for k, v in SERVICES.items()
    ])

def pay_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Pay with USDT", callback_data="pay_usdt")],
        [InlineKeyboardButton("⭐ Pay with Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])

def usdt_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Copy Address", callback_data="copy")],
        [InlineKeyboardButton("✅ I've Paid (Send Screenshot)", callback_data="paid")]
    ])

def admin_kb(oid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"adm_ok:{oid}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"adm_no:{oid}")
        ],
        [InlineKeyboardButton("💬 Message Customer", callback_data=f"adm_msg:{oid}")]
    ])

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Welcome\n\n💲 Prices shown in USD\nChoose a service:",
        reply_markup=services_kb()
    )

# ================== SERVICE ==================
async def service_select(update: Update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split(":")[1]
    s = SERVICES[key]

    context.user_data["service"] = key

    await q.message.reply_text(
        f"📦 *{s['name']}*\n"
        f"💵 USDT: {s['usd']} (Best)\n"
        f"⭐ Stars: {s['stars']}\n\n"
        "Choose payment method:",
        parse_mode="Markdown",
        reply_markup=pay_kb()
    )

# ================== BACK ==================
async def go_back(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("⬅️ Choose service:", reply_markup=services_kb())

# ================== USDT FLOW ==================
async def pay_usdt(update, context):
    q = update.callback_query
    await q.answer()

    context.user_data["pay"] = "USDT"
    await q.message.reply_text(
        f"💵 *USDT Payment*\n\n"
        f"Network: {USDT_NETWORK}\n"
        f"Address:\n`{USDT_ADDRESS}`",
        parse_mode="Markdown",
        reply_markup=usdt_kb()
    )

async def copy_addr(update, context):
    q = update.callback_query
    await q.answer(USDT_ADDRESS, show_alert=True)

async def paid_usdt(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["await_img"] = True
    await q.message.reply_text("📸 Send payment screenshot")

async def get_photo(update, context):
    photo = update.message.photo[-1]
    context.user_data["photo"] = photo.file_id
    context.user_data["await_img"] = False
    context.user_data["await_email"] = True
    await update.message.reply_text("📧 Enter your email")

# ================== STARS ==================
async def pay_stars(update, context):
    q = update.callback_query
    await q.answer()

    svc = SERVICES[context.user_data["service"]]
    prices = [LabeledPrice(label=svc["name"], amount=svc["stars"])]

    await context.bot.send_invoice(
        chat_id=q.message.chat_id,
        title=svc["name"],
        description="Telegram Stars payment",
        payload="stars",
        provider_token="",
        currency="XTR",
        prices=prices,
    )

async def precheckout(update, context):
    await update.pre_checkout_query.answer(ok=True)

async def stars_success(update, context):
    context.user_data["pay"] = "STARS"
    context.user_data["await_email"] = True
    await update.message.reply_text("📧 Enter your email")

# ================== EMAIL ==================
async def get_email(update, context):
    if not context.user_data.get("await_email"):
        return

    email = update.message.text
    if not valid_email(email):
        await update.message.reply_text("❌ Invalid email")
        return

    oid = order_id()
    svc = SERVICES[context.user_data["service"]]

    ORDERS[oid] = {
        "user": update.effective_user.id,
        "email": email,
        "service": svc["name"],
        "pay": context.user_data["pay"],
        "photo": context.user_data.get("photo")
    }

    await update.message.reply_text("⏳ Order processing…")

    text = (
        f"🆕 NEW ORDER\n\n"
        f"ID: {oid}\n"
        f"Service: {svc['name']}\n"
        f"Payment: {context.user_data['pay']}\n"
        f"Email: {email}"
    )

    if ORDERS[oid]["photo"]:
        await context.bot.send_photo(
            ADMIN_USER_ID,
            ORDERS[oid]["photo"],
            caption=text,
            reply_markup=admin_kb(oid)
        )
    else:
        await context.bot.send_message(
            ADMIN_USER_ID,
            text,
            reply_markup=admin_kb(oid)
        )

# ================== ADMIN ==================
async def admin_actions(update, context):
    q = update.callback_query
    await q.answer()
    action, oid = q.data.split(":")
    order = ORDERS[oid]

    if action == "adm_ok":
        await context.bot.send_message(order["user"], "✅ Your order has been activated.")
        await q.edit_message_text(f"✅ CONFIRMED {oid}")

    elif action == "adm_no":
        await context.bot.send_message(order["user"], "❌ Your order was cancelled.")
        await q.edit_message_text(f"❌ CANCELLED {oid}")

    elif action == "adm_msg":
        context.user_data["msg_to"] = order["user"]
        await q.message.reply_text("✍️ Send message:")

async def admin_send_msg(update, context):
    if not is_admin(update.effective_user.id):
        return
    uid = context.user_data.get("msg_to")
    if not uid:
        return
    await context.bot.send_message(uid, update.message.text)
    await update.message.reply_text("✅ Sent")
    context.user_data.clear()

# ================== APP ==================
def build():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(service_select, r"^svc:"))
    app.add_handler(CallbackQueryHandler(go_back, r"^back$"))

    app.add_handler(CallbackQueryHandler(pay_usdt, r"^pay_usdt$"))
    app.add_handler(CallbackQueryHandler(copy_addr, r"^copy$"))
    app.add_handler(CallbackQueryHandler(paid_usdt, r"^paid$"))
    app.add_handler(MessageHandler(filters.PHOTO, get_photo))

    app.add_handler(CallbackQueryHandler(pay_stars, r"^pay_stars$"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_success))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_email))
    app.add_handler(CallbackQueryHandler(admin_actions, r"^adm_"))
    app.add_handler(MessageHandler(filters.User(ADMIN_USER_ID) & filters.TEXT, admin_send_msg))

    return app

# ================== RUN ==================
if __name__ == "__main__":
    app = build()
    app.run_polling()
