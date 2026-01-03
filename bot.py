import logging
import asyncio
import os
import time
import re
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

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

ADMIN_USER_ID = 8021775847
SUPPORT_USERNAME = "wesamhm1"
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME}"

USDT_ADDRESS = "TTmfGLZXWNxQGfi7YymVGk4CGhCaP2Q88J"
USDT_NETWORK = "TRC20"

logging.basicConfig(level=logging.INFO)

# ================== DATA ==================
SERVICES = {
    "disney":  {"name": "Disney+ 1 Month",         "usd": "$5.49", "stars": 450},
    "chatgpt": {"name": "ChatGPT 1 Month",         "usd": "$5.99", "stars": 470},
    "yt":      {"name": "YouTube Premium 1 Month", "usd": "$5.99", "stars": 470},
    "spotify": {"name": "Spotify 1 Month",         "usd": "$4.99", "stars": 420},
}

ORDERS = {}
USERS = set()

# ================== UTILS ==================
def is_admin(uid): 
    return uid == ADMIN_USER_ID

def valid_email(e): 
    return re.match(r"[^@]+@[^@]+\.[^@]+", e)

def new_order_id():
    return f"O{int(time.time())}"

def support_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Support", url=SUPPORT_URL)]
    ])

# ================== KEYBOARDS ==================
def services_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{v['name']} — {v['usd']} USD", callback_data=f"svc:{k}")]
        for k, v in SERVICES.items()
    ])

def pay_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Pay with USDT (Best Price)", callback_data="pay_usdt")],
        [InlineKeyboardButton("⭐ Pay with Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])

def usdt_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Copy Address", callback_data="copy")],
        [InlineKeyboardButton("✅ I've Paid (Send Screenshot)", callback_data="paid")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])

def admin_order_kb(oid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"adm_ok:{oid}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"adm_no:{oid}")
        ],
        [InlineKeyboardButton("💬 Message Customer", callback_data=f"adm_msg:{oid}")]
    ])

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("📦 Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
    ])

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USERS.add(update.effective_user.id)
    context.user_data.clear()

    await update.message.reply_text(
        "👋 *Welcome!*\n\n"
        "Please choose the service you want to purchase:\n\n"
        "💲 *Prices shown in USD*\n"
        "_You can pay using USDT (best price) or Telegram Stars ⭐_",
        parse_mode="Markdown",
        reply_markup=services_kb()
    )

# ================== ADMIN PANEL ==================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛠 *Admin Control Panel*",
        parse_mode="Markdown",
        reply_markup=admin_panel_kb()
    )

async def admin_users(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(f"👥 Total users: {len(USERS)}")

async def admin_orders(update, context):
    q = update.callback_query
    await q.answer()
    if not ORDERS:
        await q.message.reply_text("📦 No orders yet.")
        return

    text = "📦 *All Orders:*\n\n"
    for oid, o in ORDERS.items():
        text += f"🆔 {oid}\n📧 {o['email']}\n📦 {o['service']}\n💳 {o['pay']}\n———\n"

    await q.message.reply_text(text, parse_mode="Markdown")

async def admin_broadcast(update, context):
    q = update.callback_query
    await q.answer()
    context.chat_data["broadcast"] = True
    await q.message.reply_text("✍️ Send broadcast message:")

# ================== SERVICE ==================
async def service_select(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split(":")[1]
    s = SERVICES[key]
    context.user_data["service"] = key

    await q.message.reply_text(
        f"📦 *{s['name']}*\n"
        f"💵 USDT: {s['usd']} (Best price)\n"
        f"⭐ Telegram Stars: {s['stars']}\n\n"
        "Choose payment method:",
        parse_mode="Markdown",
        reply_markup=pay_kb()
    )

async def go_back(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("⬅️ Choose a service:", reply_markup=services_kb())

# ================== USDT ==================
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
    context.user_data["await_email"] = True
    await q.message.reply_text("📸 Send payment screenshot")

async def get_photo(update, context):
    context.user_data["photo"] = update.message.photo[-1].file_id
    context.user_data["await_email"] = True
    await update.message.reply_text("📧 Enter your email address")

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
    await update.message.reply_text("📧 Enter your email address")

# ================== EMAIL ==================
async def get_email(update, context):
    if not context.user_data.get("await_email"):
        return

    email = update.message.text
    if not valid_email(email):
        await update.message.reply_text("❌ Invalid email address")
        return

    oid = new_order_id()
    svc = SERVICES[context.user_data["service"]]

    ORDERS[oid] = {
        "user": update.effective_user.id,
        "email": email,
        "service": svc["name"],
        "pay": context.user_data["pay"],
        "photo": context.user_data.get("photo")
    }

    await update.message.reply_text(
        "⏳ Your order is being processed.\n\n"
        "If you need help, contact support below 👇",
        reply_markup=support_kb()
    )

    admin_text = (
        f"🆕 NEW ORDER\n\n"
        f"🆔 {oid}\n"
        f"📦 {svc['name']}\n"
        f"💳 {context.user_data['pay']}\n"
        f"📧 {email}"
    )

    if ORDERS[oid]["photo"]:
        await context.bot.send_photo(
            ADMIN_USER_ID,
            ORDERS[oid]["photo"],
            caption=admin_text,
            reply_markup=admin_order_kb(oid)
        )
    else:
        await context.bot.send_message(
            ADMIN_USER_ID,
            admin_text,
            reply_markup=admin_order_kb(oid)
        )

# ================== ADMIN ACTIONS ==================
async def admin_actions(update, context):
    q = update.callback_query
    await q.answer()
    action, oid = q.data.split(":")
    order = ORDERS[oid]

    if action == "adm_ok":
        await context.bot.send_message(
            order["user"],
            "✅ *Your order has been activated successfully!*\n\n"
            "If you need help, contact support below 👇",
            parse_mode="Markdown",
            reply_markup=support_kb()
        )
        await q.edit_message_text(f"✅ CONFIRMED {oid}")

    elif action == "adm_no":
        await context.bot.send_message(
            order["user"],
            "❌ *Your order has been cancelled.*\n\n"
            "Contact support for assistance 👇",
            parse_mode="Markdown",
            reply_markup=support_kb()
        )
        await q.edit_message_text(f"❌ CANCELLED {oid}")

    elif action == "adm_msg":
        context.chat_data["msg_to"] = order["user"]
        await q.message.reply_text("✍️ Type your message to the customer:")

async def admin_send_msg(update, context):
    if not is_admin(update.effective_user.id):
        return

    if context.chat_data.get("broadcast"):
        for uid in USERS:
            try:
                await context.bot.send_message(uid, update.message.text)
            except:
                pass
        context.chat_data.pop("broadcast")
        await update.message.reply_text("✅ Broadcast sent.")
        return

    target = context.chat_data.get("msg_to")
    if not target:
        return

    await context.bot.send_message(
        target,
        update.message.text,
        reply_markup=support_kb()
    )
    context.chat_data.pop("msg_to")
    await update.message.reply_text("✅ Message sent.")

# ================== APP ==================
def build():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

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
    app.add_handler(CallbackQueryHandler(admin_users, r"^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_orders, r"^admin_orders$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast, r"^admin_broadcast$"))

    app.add_handler(MessageHandler(filters.User(ADMIN_USER_ID) & filters.TEXT, admin_send_msg))

    return app

if __name__ == "__main__":
    build().run_polling()
