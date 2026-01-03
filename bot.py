import logging
import asyncio
import os
import time
import re
import json

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
    raise RuntimeError("BOT_TOKEN missing (set it in env)")

ADMIN_USER_ID = 8021775847
SUPPORT_USERNAME = "wesamhm1"
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME}"

USDT_ADDRESS = "TTmfGLZXWNxQGfi7YymVGk4CGhCaP2Q88J"
USDT_NETWORK = "TRC20"

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ================== SERVICES ==================
SERVICES = {
    "disney":   {"name": "Disney+ 1 Month",         "usd": "$5.49", "stars": 450},
    "chatgpt":  {"name": "ChatGPT 1 Month",         "usd": "$5.99", "stars": 470},
    "yt":       {"name": "YouTube Premium 1 Month", "usd": "$5.99", "stars": 470},
    "spotify":  {"name": "Spotify 1 Month",         "usd": "$4.99", "stars": 420},
    "donation": {"name": "☕ Donation / Test Payment", "usd": "$0.10", "stars": 1},
}

# ================== PERSISTENT USERS ==================
USERS_FILE = "users.json"

def load_users() -> set[int]:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(int(x) for x in data)
    except Exception:
        return set()

def save_users(users: set[int]):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(users)), f)
    except Exception:
        pass

USERS = load_users()

def track_user(user_id: int):
    if user_id not in USERS:
        USERS.add(user_id)
        save_users(USERS)

# ================== ORDERS (RAM) ==================
ORDERS = {}  # order_id -> dict

# ================== UTILS ==================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_USER_ID

def valid_email(e: str) -> bool:
    return re.match(r"[^@]+@[^@]+\.[^@]+", e or "") is not None

def new_order_id() -> str:
    return f"O{int(time.time())}"

def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "EN")

# ================== TEXTS ==================
TEXT = {
    "EN": {
        "choose_lang": "🌐 Please choose your language:",
        "welcome": (
            "👋 *Welcome!*\n\n"
            "Please choose the service you want to purchase:\n\n"
            "💲 *Prices shown in USD*\n"
            "_You can pay using USDT (best price) or Telegram Stars ⭐_"
        ),
        "choose_service": "⬇️ Please choose a service:",
        "choose_payment": "Choose payment method:",
        "usdt_payment": (
            "💵 *USDT Payment*\n\n"
            f"Network: {USDT_NETWORK}\n"
            "Address:\n"
            f"`{USDT_ADDRESS}`\n\n"
            "✅ After you pay, click *I've Paid* and send a screenshot."
        ),
        "send_screenshot": "📸 Please send a screenshot of your USDT transfer confirmation.",
        "enter_email": "📧 Please enter the email you want the service activated on:",
        "invalid_email": "❌ Invalid email address. Example: name@gmail.com",
        "processing": (
            "⏳ Your order is being processed.\n\n"
            "If you need help, contact support below 👇"
        ),
        "copy_hint": (
            "📋 *USDT (TRC20) Address*\n\n"
            f"`{USDT_ADDRESS}`\n\n"
            "✅ You can *tap/long-press* the address to copy it."
        ),
        "admin_panel": "🛠 *Admin Control Panel*",
        "broadcast_prompt": "✍️ Send the broadcast message now:",
        "broadcast_done": "✅ Broadcast done.\nSent: {sent}\nFailed: {failed}",
        "no_orders": "📦 No orders yet.",
        "users_count": "👥 Total users: {n}",
        "msg_prompt": "✍️ Type the message you want to send to the customer:",
        "msg_sent": "✅ Message sent to customer.",
        "confirm_text": (
            "✅ *Your order has been activated successfully!*\n\n"
            "📧 Please check your email for activation details.\n\n"
            "If you need help, contact support below 👇"
        ),
        "cancel_text": (
            "❌ *Your order has been cancelled.*\n\n"
            "If you have any questions, contact support below 👇"
        ),
        "admin_notify_sent": "📨 Customer was notified successfully for order {oid}.",
        "admin_notify_failed": "⚠️ Failed to notify customer for order {oid}: {err}",
    },
    "AR": {
        "choose_lang": "🌐 اختر اللغة:",
        "welcome": (
            "👋 *أهلاً وسهلاً!*\n\n"
            "اختر الخدمة التي تريد شراءها:\n\n"
            "💲 *الأسعار بالدولار*\n"
            "_يمكنك الدفع بـ USDT (أفضل سعر) أو نجوم تيليجرام ⭐_"
        ),
        "choose_service": "⬇️ اختر خدمة:",
        "choose_payment": "اختر طريقة الدفع:",
        "usdt_payment": (
            "💵 *الدفع بـ USDT*\n\n"
            f"الشبكة: {USDT_NETWORK}\n"
            "العنوان:\n"
            f"`{USDT_ADDRESS}`\n\n"
            "✅ بعد الدفع اضغط (I’ve Paid) وأرسل لقطة شاشة."
        ),
        "send_screenshot": "📸 أرسل لقطة شاشة لتأكيد تحويل USDT.",
        "enter_email": "📧 اكتب الإيميل الذي تريد تفعيل الخدمة عليه:",
        "invalid_email": "❌ الإيميل غير صحيح. مثال: name@gmail.com",
        "processing": (
            "⏳ طلبك قيد المعالجة.\n\n"
            "للمساعدة تواصل معنا 👇"
        ),
        "copy_hint": (
            "📋 *عنوان USDT (TRC20)*\n\n"
            f"`{USDT_ADDRESS}`\n\n"
            "✅ اضغط مطوّلًا على العنوان لنسخه."
        ),
        "admin_panel": "🛠 *لوحة تحكم الأدمن*",
        "broadcast_prompt": "✍️ اكتب رسالة الإعلان الآن:",
        "broadcast_done": "✅ تم الإرسال.\nتم: {sent}\nفشل: {failed}",
        "no_orders": "📦 لا يوجد طلبات بعد.",
        "users_count": "👥 عدد المستخدمين: {n}",
        "msg_prompt": "✍️ اكتب الرسالة لإرسالها للعميل:",
        "msg_sent": "✅ تم إرسال الرسالة للعميل.",
        "confirm_text": (
            "✅ *تم تفعيل طلبك بنجاح!*\n\n"
            "📧 تحقق من الإيميل للتفاصيل.\n\n"
            "للمساعدة تواصل معنا 👇"
        ),
        "cancel_text": (
            "❌ *تم إلغاء طلبك.*\n\n"
            "للاستفسار تواصل معنا 👇"
        ),
        "admin_notify_sent": "📨 تم إرسال إشعار للعميل للطلب {oid}.",
        "admin_notify_failed": "⚠️ فشل إرسال إشعار للعميل للطلب {oid}: {err}",
    }
}

# ================== KEYBOARDS ==================
def lang_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:EN"),
            InlineKeyboardButton("🇸🇦 العربية", callback_data="lang:AR"),
        ]
    ])

def support_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Support", url=SUPPORT_URL)]
    ])

def support_and_start_kb(lang="EN"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Support", url=SUPPORT_URL)],
        [InlineKeyboardButton("🔄 Start Again" if lang=="EN" else "🔄 ابدأ من جديد", callback_data="start_again")]
    ])

def services_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{v['name']} — {v['usd']} USD", callback_data=f"svc:{k}")]
        for k, v in SERVICES.items()
    ])

def pay_kb(lang="EN"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Pay with USDT (Best Price)" if lang=="EN" else "💵 دفع USDT (أفضل سعر)", callback_data="pay_usdt")],
        [InlineKeyboardButton("⭐ Pay with Telegram Stars" if lang=="EN" else "⭐ الدفع بنجوم تيليجرام", callback_data="pay_stars")],
        [InlineKeyboardButton("⬅️ Back" if lang=="EN" else "⬅️ رجوع", callback_data="back_services")],
    ])

def usdt_kb(lang="EN"):
    # Better UX: copy alert + send-address message for all devices
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Copy Address" if lang=="EN" else "📋 نسخ العنوان", callback_data="copy"),
            InlineKeyboardButton("📨 Send Address" if lang=="EN" else "📨 إرسال العنوان", callback_data="send_addr"),
        ],
        [InlineKeyboardButton("✅ I've Paid (Send Screenshot)" if lang=="EN" else "✅ دفعت (أرسل لقطة شاشة)", callback_data="paid")],
        [InlineKeyboardButton("⬅️ Back" if lang=="EN" else "⬅️ رجوع", callback_data="back_payment")],
    ])

def admin_order_kb(oid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"adm_ok:{oid}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"adm_no:{oid}"),
        ],
        [InlineKeyboardButton("💬 Message Customer", callback_data=f"adm_msg:{oid}")],
    ])

def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("📦 Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
    ])

# ================== START / LANGUAGE ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("✅ /start triggered - language screen")
    track_user(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text(TEXT["EN"]["choose_lang"], reply_markup=lang_kb())

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data.split(":")[1]
    context.user_data["lang"] = lang
    track_user(q.from_user.id)

    await q.message.reply_text(
        TEXT[lang]["welcome"],
        parse_mode="Markdown",
        reply_markup=services_kb()
    )

async def start_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Start again should go back to language selection (true fresh start)
    q = update.callback_query
    await q.answer()

    track_user(q.from_user.id)
    context.user_data.clear()

    await q.message.reply_text(TEXT["EN"]["choose_lang"], reply_markup=lang_kb())

# ================== ADMIN PANEL ==================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(TEXT["EN"]["admin_panel"], parse_mode="Markdown", reply_markup=admin_panel_kb())

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.message.reply_text(TEXT["EN"]["users_count"].format(n=len(USERS)))

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    if not ORDERS:
        await q.message.reply_text(TEXT["EN"]["no_orders"])
        return

    lines = ["📦 All Orders:\n"]
    for oid, o in list(ORDERS.items())[::-1]:
        lines.append(
            f"🆔 {oid}\n"
            f"📦 {o['service']}\n"
            f"💳 {o['pay']}\n"
            f"📧 {o['email']}\n"
            f"👤 {o.get('user_name','')}\n"
            f"———"
        )
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[-3800:]
    await q.message.reply_text(text)

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.chat_data["broadcast_mode"] = True
    await q.message.reply_text(TEXT["EN"]["broadcast_prompt"])

# ================== USER FLOW ==================
async def service_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    track_user(q.from_user.id)

    lang = get_lang(context)

    key = q.data.split(":")[1]
    s = SERVICES[key]
    context.user_data["service"] = key

    await q.message.reply_text(
        f"📦 *{s['name']}*\n"
        f"💵 USDT: {s['usd']} (Best price)\n"
        f"⭐ Telegram Stars: {s['stars']}\n\n"
        f"{TEXT[lang]['choose_payment']}",
        parse_mode="Markdown",
        reply_markup=pay_kb(lang)
    )

async def back_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    track_user(q.from_user.id)
    lang = get_lang(context)
    await q.message.reply_text(TEXT[lang]["choose_service"], reply_markup=services_kb())

async def back_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = get_lang(context)

    key = context.user_data.get("service")
    if not key:
        await q.message.reply_text(TEXT[lang]["choose_service"], reply_markup=services_kb())
        return

    s = SERVICES[key]
    await q.message.reply_text(
        f"📦 *{s['name']}*\n"
        f"💵 USDT: {s['usd']} (Best price)\n"
        f"⭐ Telegram Stars: {s['stars']}\n\n"
        f"{TEXT[lang]['choose_payment']}",
        parse_mode="Markdown",
        reply_markup=pay_kb(lang)
    )

# ---------- USDT ----------
async def pay_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    track_user(q.from_user.id)

    lang = get_lang(context)

    context.user_data["pay"] = "USDT"
    context.user_data["await_img"] = False
    context.user_data["await_email"] = False
    context.user_data.pop("photo", None)

    await q.message.reply_text(
        TEXT[lang]["usdt_payment"],
        parse_mode="Markdown",
        reply_markup=usdt_kb(lang)
    )

async def copy_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer(USDT_ADDRESS, show_alert=True)
    lang = get_lang(context)
    await q.message.reply_text(TEXT[lang]["copy_hint"], parse_mode="Markdown")

async def send_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = get_lang(context)
    await q.message.reply_text(TEXT[lang]["copy_hint"], parse_mode="Markdown")

async def paid_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    track_user(q.from_user.id)

    lang = get_lang(context)
    context.user_data["await_img"] = True
    context.user_data["await_email"] = False
    await q.message.reply_text(TEXT[lang]["send_screenshot"])

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("await_img"):
        return

    track_user(update.effective_user.id)
    lang = get_lang(context)

    if not update.message.photo:
        return

    context.user_data["photo"] = update.message.photo[-1].file_id
    context.user_data["await_img"] = False
    context.user_data["await_email"] = True

    await update.message.reply_text(TEXT[lang]["enter_email"])

# ---------- STARS ----------
async def pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    track_user(q.from_user.id)

    key = context.user_data.get("service")
    if not key:
        lang = get_lang(context)
        await q.message.reply_text(TEXT[lang]["choose_service"], reply_markup=services_kb())
        return

    svc = SERVICES[key]
    prices = [LabeledPrice(label=svc["name"], amount=svc["stars"])]

    context.user_data["pay"] = "STARS"

    await context.bot.send_invoice(
        chat_id=q.message.chat_id,
        title=svc["name"],
        description="Telegram Stars payment",
        payload=f"stars:{key}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def stars_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user.id)
    lang = get_lang(context)
    context.user_data["pay"] = "STARS"
    context.user_data["await_email"] = True
    await update.message.reply_text(TEXT[lang]["enter_email"])

# ---------- EMAIL (create order + notify admin) ----------
async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("await_email"):
        return

    track_user(update.effective_user.id)
    lang = get_lang(context)

    email = (update.message.text or "").strip()
    if not valid_email(email):
        await update.message.reply_text(TEXT[lang]["invalid_email"])
        return

    key = context.user_data.get("service")
    if not key:
        await update.message.reply_text(TEXT[lang]["choose_service"], reply_markup=services_kb())
        return

    svc = SERVICES[key]
    oid = new_order_id()

    ORDERS[oid] = {
        "user": update.effective_user.id,
        "user_name": update.effective_user.full_name,
        "email": email,
        "service": svc["name"],
        "pay": context.user_data.get("pay", "USDT"),
        "photo": context.user_data.get("photo"),
        "lang": lang,
        "created_at": int(time.time()),
        "status": "WAITING_ADMIN",
    }

    context.user_data["await_email"] = False

    await update.message.reply_text(TEXT[lang]["processing"], reply_markup=support_and_start_kb(lang))

    admin_text = (
        f"🆕 NEW ORDER\n\n"
        f"🆔 {oid}\n"
        f"📦 {svc['name']}\n"
        f"💳 {ORDERS[oid]['pay']}\n"
        f"📧 {email}\n"
        f"👤 {update.effective_user.full_name}\n"
        f"🆔 {update.effective_user.id}"
    )

    try:
        if ORDERS[oid].get("photo"):
            await context.bot.send_photo(
                chat_id=ADMIN_USER_ID,
                photo=ORDERS[oid]["photo"],
                caption=admin_text,
                reply_markup=admin_order_kb(oid)
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=admin_text,
                reply_markup=admin_order_kb(oid)
            )
    except Exception as e:
        logging.exception("Failed to notify admin: %s", e)

# ================== ADMIN ACTIONS ==================
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return

    action, oid = q.data.split(":", 1)
    order = ORDERS.get(oid)
    if not order:
        await q.message.reply_text("❌ Order not found (maybe bot restarted).")
        return

    user_id = order["user"]
    lang = order.get("lang", "EN")

    if action == "adm_ok":
        order["status"] = "CONFIRMED"
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=TEXT[lang]["confirm_text"],
                parse_mode="Markdown",
                reply_markup=support_and_start_kb(lang)
            )
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=TEXT["EN"]["admin_notify_sent"].format(oid=oid)
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=TEXT["EN"]["admin_notify_failed"].format(oid=oid, err=str(e))
            )
        await q.edit_message_text(f"✅ CONFIRMED — {oid}")

    elif action == "adm_no":
        order["status"] = "CANCELLED"
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=TEXT[lang]["cancel_text"],
                parse_mode="Markdown",
                reply_markup=support_and_start_kb(lang)
            )
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=TEXT["EN"]["admin_notify_sent"].format(oid=oid)
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=TEXT["EN"]["admin_notify_failed"].format(oid=oid, err=str(e))
            )
        await q.edit_message_text(f"❌ CANCELLED — {oid}")

    elif action == "adm_msg":
        context.chat_data["msg_target"] = user_id
        context.chat_data["msg_order_id"] = oid
        await q.message.reply_text(TEXT["EN"]["msg_prompt"])

# ================== ADMIN TEXT HANDLER (priority) ==================
async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    # Broadcast mode
    if context.chat_data.get("broadcast_mode"):
        msg = update.message.text
        sent, failed = 0, 0
        for uid in list(USERS):
            try:
                await context.bot.send_message(chat_id=uid, text=msg)
                sent += 1
                await asyncio.sleep(0.03)
            except Exception:
                failed += 1

        context.chat_data.pop("broadcast_mode", None)
        await update.message.reply_text(TEXT["EN"]["broadcast_done"].format(sent=sent, failed=failed))
        return

    # Message customer mode
    target = context.chat_data.get("msg_target")
    oid = context.chat_data.get("msg_order_id")
    if target and oid:
        try:
            await context.bot.send_message(
                chat_id=target,
                text=update.message.text,
                reply_markup=support_kb()
            )
            await update.message.reply_text(TEXT["EN"]["msg_sent"])
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"📨 Message delivered to customer (Order {oid})."
            )
        except Exception as e:
            await update.message.reply_text(f"⚠️ Failed to send: {e}")

        context.chat_data.pop("msg_target", None)
        context.chat_data.pop("msg_order_id", None)
        return

# ================== APP ==================
def build():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

    # Start again button
    app.add_handler(CallbackQueryHandler(start_again, pattern=r"^start_again$"))

    # Language
    app.add_handler(CallbackQueryHandler(set_language, pattern=r"^lang:"))

    # Admin panel buttons
    app.add_handler(CallbackQueryHandler(admin_users, pattern=r"^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_orders, pattern=r"^admin_orders$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast, pattern=r"^admin_broadcast$"))

    # User flow
    app.add_handler(CallbackQueryHandler(service_select, pattern=r"^svc:"))
    app.add_handler(CallbackQueryHandler(back_services, pattern=r"^back_services$"))
    app.add_handler(CallbackQueryHandler(back_payment, pattern=r"^back_payment$"))

    app.add_handler(CallbackQueryHandler(pay_usdt, pattern=r"^pay_usdt$"))
    app.add_handler(CallbackQueryHandler(copy_addr, pattern=r"^copy$"))
    app.add_handler(CallbackQueryHandler(send_addr, pattern=r"^send_addr$"))
    app.add_handler(CallbackQueryHandler(paid_usdt, pattern=r"^paid$"))
    app.add_handler(MessageHandler(filters.PHOTO, get_photo))

    app.add_handler(CallbackQueryHandler(pay_stars, pattern=r"^pay_stars$"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_success))

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(admin_actions, pattern=r"^adm_"))

    # Admin text handler must run BEFORE email handler
    app.add_handler(
        MessageHandler(filters.User(ADMIN_USER_ID) & filters.TEXT & ~filters.COMMAND, admin_text_handler),
        group=0
    )

    # Email handler for everyone
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_email), group=1)

    return app

if __name__ == "__main__":
    build().run_polling()
