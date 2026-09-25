import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from supabase import create_client, Client


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL")


# ============================================================
# ENVIRONMENT VALIDATION
# ============================================================

required_variables = {
    "BOT_TOKEN": BOT_TOKEN,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
    "RAILWAY_URL": RAILWAY_URL,
}

missing_variables = [
    name for name, value in required_variables.items()
    if not value
]

if missing_variables:
    raise RuntimeError(
        "Missing required environment variables: "
        + ", ".join(missing_variables)
    )


# ============================================================
# NORMALIZE RAILWAY URL
# ============================================================

RAILWAY_URL = RAILWAY_URL.rstrip("/")

WEBHOOK_PATH = "/telegram"

WEBHOOK_URL = f"{RAILWAY_URL}{WEBHOOK_PATH}"


# ============================================================
# SUPABASE
# ============================================================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)


# ============================================================
# TELEGRAM APPLICATION
# ============================================================

application = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)


# ============================================================
# /start
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_message:
        return

    user = update.effective_user

    user_id = user.id if user else 0

    username = user.username if user and user.username else ""

    logger.info(
        "START command from Telegram user_id=%s username=%s",
        user_id,
        username,
    )

    # --------------------------------------------------------
    # Marketing / referral link
    # --------------------------------------------------------

    try:
        bot_info = await context.bot.get_me()

        bot_username = bot_info.username

        referral_link = (
            f"https://t.me/{bot_username}?start=ref_{user_id}"
        )

    except Exception as exc:
        logger.exception(
            "Could not create referral link: %s",
            exc,
        )

        referral_link = "رابط الإحالة غير متاح حالياً."

    # --------------------------------------------------------
    # Read referral parameter if Telegram supplied one
    # --------------------------------------------------------

    referral_parameter = None

    if context.args:
        referral_parameter = context.args[0]

        logger.info(
            "Referral parameter received: %s",
            referral_parameter,
        )

    # --------------------------------------------------------
    # Welcome message
    # --------------------------------------------------------

    text = (
        "مرحباً بك في المتجر الرقمي 👋\n\n"
        "يمكنك استخدام الأوامر التالية:\n\n"
        "🛍 /products\n"
        "لعرض المنتجات المتاحة حالياً.\n\n"
        "💳 /buy\n"
        "لبدء عملية الشراء واختيار المنتج.\n\n"
        "🔗 رابط الإحالة التسويقية الخاص بك:\n"
        f"{referral_link}\n\n"
        "يمكنك مشاركة هذا الرابط مع الآخرين."
    )

    if referral_parameter:
        text += (
            "\n\n"
            f"تم استقبال رمز الإحالة: {referral_parameter}"
        )

    await update.effective_message.reply_text(text)


# ============================================================
# SUPABASE PRODUCTS READER
# ============================================================

def get_active_products():
    """
    قراءة المنتجات النشطة من جدول products في Supabase.
    """

    response = (
        supabase
        .table("products")
        .select(
            "id,sku,name,description,price_usd,pay_currency,delivery_type,active"
        )
        .eq("active", True)
        .order("created_at", desc=False)
        .execute()
    )

    return response.data or []


# ============================================================
# /products
# ============================================================

async def products_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_message:
        return

    logger.info(
        "PRODUCTS command from user_id=%s",
        update.effective_user.id if update.effective_user else "unknown",
    )

    try:
        products = get_active_products()

    except Exception as exc:
        logger.exception(
            "PRODUCTS ERROR: %s",
            exc,
        )

        await update.effective_message.reply_text(
            "حدث خطأ أثناء قراءة المنتجات.\n"
            "يرجى المحاولة مرة أخرى."
        )

        return

    if not products:
        await update.effective_message.reply_text(
            "لا توجد منتجات متاحة حالياً."
        )

        return

    lines = ["🛍 المنتجات المتاحة حالياً:\n"]

    for product in products:
        product_name = product.get("name") or "منتج بدون اسم"

        sku = product.get("sku") or ""

        description = product.get("description") or ""

        price_usd = product.get("price_usd")

        pay_currency = (
            product.get("pay_currency")
            or "usdttrc20"
        )

        lines.append(
            f"📦 {product_name}"
        )

        if sku:
            lines.append(
                f"🔖 SKU: {sku}"
            )

        if description:
            lines.append(
                f"📝 {description}"
            )

        if price_usd is not None:
            lines.append(
                f"💵 السعر: {price_usd} USD"
            )

        lines.append(
            f"💰 الدفع: {pay_currency}"
        )

        lines.append("")

    lines.append(
        "لشراء منتج استخدم الأمر:\n"
        "/buy"
    )

    await update.effective_message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# /buy
# ============================================================

async def buy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.effective_message:
        return

    logger.info(
        "BUY command from user_id=%s",
        update.effective_user.id if update.effective_user else "unknown",
    )

    try:
        products = get_active_products()

    except Exception as exc:
        logger.exception(
            "BUY PRODUCTS ERROR: %s",
            exc,
        )

        await update.effective_message.reply_text(
            "حدث خطأ أثناء تحميل المنتجات للشراء.\n"
            "يرجى المحاولة مرة أخرى."
        )

        return

    if not products:
        await update.effective_message.reply_text(
            "لا توجد منتجات متاحة للشراء حالياً."
        )

        return

    keyboard = []

    for product in products:
        product_id = product.get("id")

        product_name = (
            product.get("name")
            or product.get("sku")
            or "منتج"
        )

        price_usd = product.get("price_usd")

        if price_usd is not None:
            button_text = (
                f"{product_name} - ${price_usd}"
            )
        else:
            button_text = product_name

        keyboard.append(
            [
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"buy:{product_id}",
                )
            ]
        )

    keyboard_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(
        "🛒 اختر المنتج الذي تريد شراءه:",
        reply_markup=keyboard_markup,
    )


# ============================================================
# PRODUCT SELECTION
# ============================================================

async def product_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    if not data.startswith("buy:"):
        return

    product_id = data.split(":", 1)[1]

    logger.info(
        "Product selected: product_id=%s user_id=%s",
        product_id,
        query.from_user.id,
    )

    try:
        response = (
            supabase
            .table("products")
            .select(
                "id,sku,name,description,price_usd,pay_currency,delivery_type,active"
            )
            .eq("id", product_id)
            .eq("active", True)
            .limit(1)
            .execute()
        )

        products = response.data or []

    except Exception as exc:
        logger.exception(
            "PRODUCT SELECTION ERROR: %s",
            exc,
        )

        await query.edit_message_text(
            "حدث خطأ أثناء قراءة المنتج."
        )

        return

    if not products:
        await query.edit_message_text(
            "هذا المنتج غير متاح حالياً."
        )

        return

    product = products[0]

    product_name = product.get("name") or "منتج"

    description = product.get("description") or ""

    price_usd = product.get("price_usd")

    pay_currency = (
        product.get("pay_currency")
        or "usdttrc20"
    )

    text = (
        "🛒 المنتج المختار:\n\n"
        f"📦 {product_name}\n"
    )

    if description:
        text += f"\n📝 {description}\n"

    if price_usd is not None:
        text += f"\n💵 السعر: {price_usd} USD\n"

    text += (
        f"💰 العملة: {pay_currency}\n\n"
        "تم اختيار المنتج بنجاح.\n"
        "خطوة إنشاء فاتورة الدفع يمكن ربطها هنا "
        "بـ NOWPayments."
    )

    await query.edit_message_text(text)


# ============================================================
# REGISTER ALL TELEGRAM HANDLERS
# ============================================================

application.add_handler(
    CommandHandler("start", start_command)
)

application.add_handler(
    CommandHandler("products", products_command)
)

application.add_handler(
    CommandHandler("buy", buy_command)
)

application.add_handler(
    CallbackQueryHandler(
        product_selected,
        pattern=r"^buy:"
    )
)


# ============================================================
# FASTAPI LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifecycle.

    startup:
        initialize Telegram application
        start Telegram application
        configure Telegram webhook

    shutdown:
        delete webhook
        stop Telegram application
        shutdown Telegram application
    """

    logger.info("Starting Telegram application...")

    try:
        # ----------------------------------------------------
        # Initialize Telegram Application
        # ----------------------------------------------------

        await application.initialize()

        logger.info(
            "Telegram application initialized."
        )

        # ----------------------------------------------------
        # Start Telegram Application
        # ----------------------------------------------------

        await application.start()

        logger.info(
            "Telegram application started."
        )

        # ----------------------------------------------------
        # Configure Webhook
        # ----------------------------------------------------

        await application.bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=False,
        )

        logger.info(
            "Telegram webhook configured: %s",
            WEBHOOK_URL,
        )

        logger.info(
            "Bot is now running."
        )

        yield

    except Exception as exc:
        logger.exception(
            "Telegram startup error: %s",
            exc,
        )

        raise

    finally:
        # ----------------------------------------------------
        # SHUTDOWN
        # ----------------------------------------------------

        logger.info(
            "Shutting down Telegram application..."
        )

        try:
            await application.bot.delete_webhook(
                drop_pending_updates=False
            )

        except Exception as exc:
            logger.warning(
                "Could not delete webhook: %s",
                exc,
            )

        try:
            await application.stop()

        except Exception as exc:
            logger.warning(
                "Could not stop Telegram application: %s",
                exc,
            )

        try:
            await application.shutdown()

        except Exception as exc:
            logger.warning(
                "Could not shutdown Telegram application: %s",
                exc,
            )

        logger.info(
            "Telegram application stopped."
        )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Telegram Digital Store",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "telegram-digital-store",
        "webhook": WEBHOOK_URL,
    }


# ============================================================
# STATUS
# ============================================================

@app.get("/status")
async def status():
    return {
        "status": "running",
        "telegram": "webhook",
        "supabase": "configured",
        "webhook_url": WEBHOOK_URL,
    }


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@app.post("/telegram")
async def telegram_webhook(request: Request):
    """
    Receives Telegram webhook updates and sends them
    into the SAME python-telegram-bot Application.
    """

    try:
        update_data = await request.json()

        telegram_update = Update.de_json(
            update_data,
            application.bot,
        )

        await application.process_update(
            telegram_update
        )

        return {
            "ok": True
        }

    except Exception as exc:
        logger.exception(
            "Telegram webhook processing error: %s",
            exc,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "Webhook processing failed",
            },
        )


# ============================================================
# RAILWAY STARTUP
# ============================================================

if __name__ == "__main__":
    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "8000"
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
