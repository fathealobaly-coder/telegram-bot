import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from supabase import create_client, Client

# إعداد السجلات (Logs)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# جلب المتغيرات
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing!")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials are missing!")

# الاتصال بقاعدة بيانات Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# أمر البداية /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "مرحباً بك 👋\n\n"
        "أهلاً بك في المتجر الإلكتروني.\n\n"
        "📌 الأوامر المتاحة:\n"
        "🔹 /products - لعرض المنتجات المتاحة\n"
        "🔹 /buy <رقم_المنتج> - لعرض تفاصيل شراء المنتج"
    )
    await update.message.reply_text(welcome_text)

# أمر عرض المنتجات /products
async def products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = supabase.table("deals").select("*").execute()
        deals = response.data or []

        if not deals:
            await update.message.reply_text("عذراً، لا توجد منتجات متاحة حالياً.")
            return

        message = "🛍️ **قائمة المنتجات المتاحة:**\n\n"
        for item in deals:
            item_id = item.get("id", "")
            title = item.get("product_name") or item.get("name") or "منتج رقم " + str(item_id)
            price = item.get("price") or item.get("price_usd") or "0"
            currency = item.get("pay_currency") or "USDT"

            message += f"🆔 الرقم: `{item_id}`\n"
            message += f"📦 الاسم: {title}\n"
            message += f"💰 السعر: {price} {currency}\n"
            message += f"👉 للشراء: /buy {item_id}\n"
            message += "──────────────\n"

        await update.message.reply_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"خطأ أثناء جلب المنتجات: {e}")
        await update.message.reply_text("حدث خطأ أثناء تحميل المنتجات، يرجى المحاولة لاحقاً.")

# أمر الشراء والتفاصيل /buy
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("يرجى تحديد رقم المنتج بعد الأمر، مثال:\n`/buy 1`", parse_mode="Markdown")
        return

    product_id = context.args[0]

    try:
        response = supabase.table("deals").select("*").eq("id", product_id).execute()
        deals = response.data or []

        if not deals:
            await update.message.reply_text(f"❌ لم يتم العثور على منتج يحمل الرقم {product_id}.")
            return

        deal = deals[0]
        title = deal.get("product_name") or deal.get("name") or f"منتج {product_id}"
        price = deal.get("price") or deal.get("price_usd") or "0"
        currency = deal.get("pay_currency") or "USDT"
        link = deal.get("deal_url") or deal.get("url") or "لا يوجد رابط مباشر"

        reply = (
            f"🛒 **تفاصيل المنتج:**\n\n"
            f"📦 **الاسم:** {title}\n"
            f"💰 **السعر:** {price} {currency}\n"
            f"🔗 **رابط الشراء/التفاصيل:** {link}\n"
        )
        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"خطأ في أمر الشراء: {e}")
        await update.message.reply_text("حدث خطأ أثناء جلب تفاصيل المنتج.")

def main():
    logger.info("Starting Telegram Bot with Polling...")
    
    # بناء تطبيق البوت
    app = Application.builder().token(BOT_TOKEN).build()

    # تسجيل الأوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("products", products_command))
    app.add_handler(CommandHandler("buy", buy_command))

    # تشغيل مستمر بدون توقف (Polling)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
