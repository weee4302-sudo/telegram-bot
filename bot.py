import logging
import asyncio
import re
import os
import time
import json
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

ADMIN_USER_ID = 8021775847

SUPPORT_USERNAME = "wesamhm1"  # without @
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME}"
SUPPORT_COOLDOWN_SECONDS = 60 * 60  # 1 hour

USDT_NETWORK = "TRON (TRC20)"
USDT_ADDRESS = "TTmfGLZXWNxQGfi7YymVGk4CGhCaP2Q88J"

SERVICES = {
    "disney_1m":  {"name": "Disney+ 1 Month",            "stars_price": 450, "usdt_price": "$5.49"},
    "chatgpt_1m": {"name": "ChatGPT 1 Month",            "stars_price": 470, "usdt_price": "$5.99"},
    "yt_premium": {"name": "YouTube Premium 1 Month",    "stars_price": 470, "usdt_price": "$5.99"},
    "spotify_1m": {"name": "Spotify 1 Month",            "stars_price": 420, "usdt_price": "$4.99"},
    "donation_1": {"name": "☕ Donation / Test Payment",  "stars_price": 1,   "usdt_price": "$0.10"},
}

ORDERS = {}  # order_id -> dict

USERS_FILE = "users.json"

def load_users() -> set[int]:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(int(x) for x in data)
    except Exception:
        return set()

def save_users(users: set[int]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(users)), f)

USERS = load_users()

def track_user(user_id: int):
    if user_id not in USERS:
        USERS.add(user_id)
        save_users(USERS)


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
                f"⭐ {s['name']} — {s['stars_price']} Stars",
                callback_data=f"service:{key}"
            )
        ])
    return InlineKeyboardMarkup(rows)

def pay_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Pay with Stars", callback_data="pay_stars")],
        [InlineKeyboardButton("💵 Pay with USDT", callback_data="pay_usdt")],
    ])

def continue_keyboard_stars() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Continue (Enter Email)", callback_data="stars_continue")]
    ])

def usdt_pay_keyboard() -> InlineKeyboardMarkup:
    # ✅ زر inline يساعد المستخدم ينسخ العنوان بسهولة من نفس الشات
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Copy Address", callback_data="copy_usdt_addr"),
            InlineKeyboardButton("🧾 Open Copy Box", switch_inline_query_current_chat=USDT_ADDRESS),
        ],
        [InlineKeyboardButton("✅ I've Paid (Send Screenshot)", callback_data="usdt_i_paid")],
    ])

def support_keyboard_locked(remaining_seconds: int) -> InlineKeyboardMarkup:
    mins = max(0, remaining_seconds) // 60
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔒 Contact Support (available in {mins} min)", callback_data="support_locked")]
    ])

def support_keyboard_unlocked() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Support", url=SUPPORT_URL)]
    ])

def admin_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"adm_confirm:{order_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"adm_cancel:{order_id}"),
        ],
        [
            InlineKeyboardButton("💬 Message Customer", callback_data=f"adm_msg:{order_id}"),
        ],
    ])

def format_mmss(seconds: int) -> str:
    seconds = max(0, seconds)
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

def new_order_id() -> str:
    return f"O{int(time.time())}"


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
        try:
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
            pass

        job.schedule_removal()
        return

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
        job.schedule_removal()


# ---------- Helpers ----------
def is_valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user.id)
    context.user_data.clear()

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Please choose the service you want to purchase:\n"
        "(Prices shown in Telegram Stars ⭐)",
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
    context.user_data["service_stars_price"] = service["stars_price"]
    context.user_data["service_usdt_price"] = service["usdt_price"]

    await query.message.reply_text(
        f"✅ You selected: *{service['name']}*\n"
        f"⭐ Stars price: *{service['stars_price']}*\n"
        f"💵 USDT price: *{service['usdt_price']}* (_Better price with USDT_)\n\n"
        "Choose a payment method:",
        reply_markup=pay_keyboard(),
        parse_mode="Markdown"
    )


# ===== Stars Payment Flow =====
async def pay_stars_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    service_key = context.user_data.get("service_key")
    if not service_key:
        await query.message.reply_text("❌ Please select a service first. Use /start.")
        return

    service = SERVICES[service_key]
    stars_price = service["stars_price"]

    context.user_data["payment_method"] = "STARS"
    context.user_data["paid"] = False

    prices = [LabeledPrice(label=service["name"], amount=stars_price)]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=service["name"],
        description="Service payment via Telegram Stars.",
        payload=f"order:{service_key}",
        provider_token="",   # MUST be empty for Stars
        currency="XTR",
        prices=prices,
        need_email=False,
    )

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user.id)

    sp = update.message.successful_payment
    context.user_data["paid"] = True
    context.user_data["paid_amount"] = sp.total_amount
    context.user_data["charge_id"] = sp.telegram_payment_charge_id

    await update.message.reply_text(
        "✅ Payment successful!\n\n"
        "Click below to continue and provide your email:",
        reply_markup=continue_keyboard_stars()
    )

async def stars_continue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get("paid"):
        await query.message.reply_text("❌ No payment detected yet.")
        return

    context.user_data["awaiting_email"] = True
    await query.message.reply_text("📧 Please enter your email address so we can send you the activation:")


# ===== USDT Payment Flow =====
async def pay_usdt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    service_key = context.user_data.get("service_key")
    if not service_key:
        await query.message.reply_text("❌ Please select a service first. Use /start.")
        return

    context.user_data["payment_method"] = "USDT"
    context.user_data["paid"] = False  # ✅ صح: ما نعتبره مدفوع إلا بعد إرسال الصورة
    context.user_data["awaiting_usdt_screenshot"] = False
    context.user_data["awaiting_email"] = False

    service = SERVICES[service_key]
    usdt_price = service.get("usdt_price", "$5.99")

    await query.message.reply_text(
        "💵 Payment via USDT\n\n"
        f"Network: {USDT_NETWORK}\n"
        f"Amount: {usdt_price}\n\n"
        "Wallet address:\n"
        f"`{USDT_ADDRESS}`\n\n"
        "⚠️ Use TRC20 network only.\n"
        "_✨ Better price with USDT_",
        parse_mode="Markdown",
        reply_markup=usdt_pay_keyboard()
    )

async def copy_usdt_addr_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ بدل "كبسة فاضية": نطلع alert + نبعت رسالة عنوان قابلة للنسخ
    query = update.callback_query
    await query.answer(f"{USDT_ADDRESS}", show_alert=True)

    await query.message.reply_text(
        "📋 *USDT (TRC20) Address*\n\n"
        f"`{USDT_ADDRESS}`\n\n"
        "✅ You can *long-press* the address to copy it.",
        parse_mode="Markdown"
    )

async def usdt_i_paid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["awaiting_usdt_screenshot"] = True
    context.user_data["awaiting_email"] = False

    await query.message.reply_text("📸 Please upload a screenshot (any image is OK).")

async def usdt_screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_usdt_screenshot"):
        return

    track_user(update.effective_user.id)

    if not update.message.photo:
        await update.message.reply_text("❌ Please send the screenshot as an image (photo).")
        return

    photo = update.message.photo[-1]
    context.user_data["awaiting_usdt_screenshot"] = False
    context.user_data["usdt_screenshot_file_id"] = photo.file_id
    context.user_data["paid"] = True  # ✅ اعتبره مدفوع بعد الصورة

    # Now ask for email
    context.user_data["awaiting_email"] = True
    await update.message.reply_text("✉️ Now please enter your email address to activate your subscription.")


# ===== Email Handler (Stars + USDT) =====
async def email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_email"):
        return

    track_user(update.effective_user.id)

    email = update.message.text.strip()
    if not is_valid_email(email):
        await update.message.reply_text("❌ Invalid email. Please enter a valid email (example: name@gmail.com)")
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

    # --- Create order ---
    user = update.effective_user
    service_name = context.user_data.get("service_name", "Unknown")
    service_stars_price = context.user_data.get("service_stars_price")
    service_usdt_price = context.user_data.get("service_usdt_price")
    payment_method = context.user_data.get("payment_method", "STARS")

    order_id = new_order_id()

    order = {
        "order_id": order_id,
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "service_name": service_name,
        "service_stars_price": service_stars_price,
        "service_usdt_price": service_usdt_price,
        "payment_method": payment_method,
        "email": email,
        "status": "WAITING_ADMIN",
        "created_at": int(time.time()),
        "usdt_screenshot_file_id": context.user_data.get("usdt_screenshot_file_id"),
        "stars_paid_amount": context.user_data.get("paid_amount"),
        "stars_charge_id": context.user_data.get("charge_id"),
    }
    ORDERS[order_id] = order

    admin_text = (
        "🆕 NEW ORDER\n\n"
        f"Order ID: {order_id}\n"
        f"Service: {service_name}\n"
        f"Payment: {payment_method}\n"
        f"Email: {email}\n\n"
        f"Customer: {user.full_name}\n"
        f"Username: @{user.username if user.username else '(no username)'}\n"
        f"User ID: {user.id}\n"
    )

    try:
        if payment_method == "USDT" and order.get("usdt_screenshot_file_id"):
            admin_text += (
                f"\nNetwork: {USDT_NETWORK}\n"
                f"Amount: {service_usdt_price}\n"
            )
            await context.bot.send_photo(
                chat_id=ADMIN_USER_ID,
                photo=order["usdt_screenshot_file_id"],
                caption=admin_text + "\n📸 Image attached.",
                reply_markup=admin_order_keyboard(order_id),
            )
        else:
            # STARS
            if order.get("stars_paid_amount") is not None:
                admin_text += f"\nPaid: {order['stars_paid_amount']} Stars\n"
            if service_stars_price is not None:
                admin_text += f"Listed Price: {service_stars_price} Stars\n"
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=admin_text,
                reply_markup=admin_order_keyboard(order_id)
            )
    except Exception as e:
        logging.exception("Failed to notify admin: %s", e)


# ===== Support Lock Button =====
async def support_locked_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    start_ts = context.user_data.get("support_start_ts")
    if not start_ts:
        await query.answer("Support will be available later.", show_alert=True)
        return

    remaining = SUPPORT_COOLDOWN_SECONDS - int(time.time() - start_ts)
    await query.answer(
        f"Please wait. Support will be available in {format_mmss(remaining)}.",
        show_alert=True
    )


# ===== Admin Actions =====
async def admin_actions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("Not allowed.", show_alert=True)
        return

    data = query.data
    action, order_id = data.split(":", 1)

    order = ORDERS.get(order_id)
    if not order:
        await query.message.reply_text("❌ Order not found (maybe bot restarted).")
        return

    customer_id = order["user_id"]

    if action == "adm_confirm":
        ORDERS[order_id]["status"] = "CONFIRMED"
        await context.bot.send_message(
            chat_id=customer_id,
            text=(
                "✅ تم تفعيل اشتراكك بنجاح.\n"
                f"📧 Email: {order['email']}\n\n"
                "إذا واجهت أي مشكلة تواصل معنا 👇"
            ),
            reply_markup=support_keyboard_unlocked()
        )
        try:
            await query.edit_message_caption(caption=f"✅ CONFIRMED — Order {order_id}", reply_markup=None)
        except Exception:
            await query.edit_message_text(text=f"✅ CONFIRMED — Order {order_id}")

    elif action == "adm_cancel":
        ORDERS[order_id]["status"] = "CANCELLED"
        await context.bot.send_message(
            chat_id=customer_id,
            text=(
                "❌ تم إلغاء طلبك للأسف.\n"
                "للمزيد من التفاصيل تواصل معنا 👇"
            ),
            reply_markup=support_keyboard_unlocked()
        )
        try:
            await query.edit_message_caption(caption=f"❌ CANCELLED — Order {order_id}", reply_markup=None)
        except Exception:
            await query.edit_message_text(text=f"❌ CANCELLED — Order {order_id}")

    elif action == "adm_msg":
        context.user_data["admin_msg_target"] = customer_id
        context.user_data["admin_msg_order_id"] = order_id
        await query.message.reply_text("✍️ اكتب الرسالة الآن وسأرسلها للعميل (رسالة واحدة).")


async def admin_message_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ مهم: ما يشتغل إلا للأدمن ووقت يكون فعلًا بوضع إرسال رسالة
    if not is_admin(update.effective_user.id):
        return

    target = context.user_data.get("admin_msg_target")
    order_id = context.user_data.get("admin_msg_order_id")
    if not target or not order_id:
        return

    text = update.message.text.strip()
    if not text:
        return

    await context.bot.send_message(
        chat_id=target,
        text=text,
        reply_markup=support_keyboard_unlocked()
    )

    context.user_data.pop("admin_msg_target", None)
    context.user_data.pop("admin_msg_order_id", None)

    await update.message.reply_text(f"✅ Sent to customer (Order {order_id}).")


# ===== Broadcast =====
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    msg = " ".join(context.args)

    sent = 0
    failed = 0

    for uid in list(USERS):
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await update.message.reply_text(f"✅ Broadcast done.\nSent: {sent}\nFailed: {failed}")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(f"👥 Total users: {len(USERS)}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Type /start to begin.")


# ---------- App ----------
def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(service_select_handler, pattern=r"^service:"))

    app.add_handler(CallbackQueryHandler(pay_stars_handler, pattern=r"^pay_stars$"))
    app.add_handler(CallbackQueryHandler(pay_usdt_handler, pattern=r"^pay_usdt$"))

    app.add_handler(CallbackQueryHandler(copy_usdt_addr_handler, pattern=r"^copy_usdt_addr$"))
    app.add_handler(CallbackQueryHandler(usdt_i_paid_handler, pattern=r"^usdt_i_paid$"))

    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CallbackQueryHandler(stars_continue_handler, pattern=r"^stars_continue$"))

    app.add_handler(MessageHandler(filters.PHOTO, usdt_screenshot_handler))

    app.add_handler(CallbackQueryHandler(support_locked_handler, pattern=r"^support_locked$"))
    app.add_handler(CallbackQueryHandler(admin_actions_handler, pattern=r"^adm_"))

    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("users", users_cmd))

    # ✅ الترتيب + الفلاتر الصحيحة:
    # 1) admin message mode ONLY for admin
    app.add_handler(MessageHandler(filters.User(ADMIN_USER_ID) & filters.TEXT & ~filters.COMMAND, admin_message_text_handler))
    # 2) email capture for everyone (including admin if he is buying)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    return app


if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()

    asyncio.set_event_loop(asyncio.new_event_loop())
    application = build_app()
    application.run_polling()
