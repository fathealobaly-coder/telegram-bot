import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from supabase import create_client, Client


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing")

if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY is missing")


# ============================================================
# SUPABASE
# ============================================================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# /start
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "مرحباً بك 👋\n\n"
        "أهلاً بك في المتجر.\n\n"
        "استخدم:\n"
        "/products - عرض المنتجات\n"
        "/buy رقم_المنتج - عرض تفاصيل المنتج"
    )


# ============================================================
# /products
# ============================================================

async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        result = (
            supabase
            .table("deals")
            .select("*")
            .execute()
        )

        deals = result.data or []

        if not deals:
            await update.message.reply_text(
                "لا توجد منتجات متاحة حالياً."
            )
            return

        message = "🛍 المنتجات المتاحة:\n\n"

        for index, deal in enumerate(deals, start=1):

            deal_id = (
                deal.get("id")
                or deal.get("deal_id")
                or index
            )

            name = (
                deal.get("name")
                or deal.get("title")
                or deal.get("product_name")
                or f"Product {index}"
            )

            price = (
                deal.get("price_usd")
                or deal.get("price")
                or "غير محدد"
            )

            currency = (
                deal.get("pay_currency")
                or "USDT"
            )

            message += (
                f"🆔 {deal_id}\n"
                f"📦 {name}\n"
                f"💰 {price} {currency}\n"
                f"➡️ /buy {deal_id}\n\n"
            )

        await update.message.reply_text(message)

    except Exception as e:

        logger.exception("PRODUCTS ERROR")

        await update.message.reply_text(
            "حدث خطأ أثناء قراءة المنتجات."
        )


# ============================================================
# /buy
# ============================================================

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:

        await update.message.reply_text(
            "استخدم الأمر بهذا الشكل:\n\n"
            "/buy رقم_المنتج"
        )

        return

    deal_id = context.args[0]

    try:

        result = (
            supabase
            .table("deals")
            .select("*")
            .eq("id", deal_id)
            .limit(1)
            .execute()
        )

        deals = result.data or []

        if not deals:

            await update.message.reply_text(
                "❌ المنتج غير موجود."
            )

            return

        deal = deals[0]

        name = (
            deal.get("name")
            or deal.get("title")
            or deal.get("product_name")
            or "منتج"
        )

        description = (
            deal.get("description")
            or "لا يوجد وصف."
        )

        price = (
            deal.get("price_usd")
            or deal.get("price")
            or "غير محدد"
        )

        currency = (
            deal.get("pay_currency")
            or "USDT"
        )

        message = (
            f"📦 {name}\n\n"
            f"{description}\n\n"
            f"💰 السعر: {price} {currency}\n\n"
            f"🆔 ID: {deal_id}\n\n"
            "تم العثور على المنتج بنجاح."
        )

        await update.message.reply_text(message)

    except Exception:

        logger.exception("BUY ERROR")

        await update.message.reply_text(
            "حدث خطأ أثناء قراءة المنتج."
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "Telegram error: %s",
        context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info("Starting Telegram bot...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("products", products)
    )

    application.add_handler(
        CommandHandler("buy", buy)
    )

    application.add_error_handler(
        error_handler
    )

    logger.info("Deleting old Telegram webhook...")

    # مهم جداً:
    # إزالة أي Webhook قديم حتى لا يمنع Polling
    application.run_polling(
        drop_pending_updates=False
    )


if __name__ == "__main__":
    main()
