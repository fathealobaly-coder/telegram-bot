import os
import logging
from fastapi import FastAPI, Request
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from supabase import create_client, Client

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# المتغيرات
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# تطبيق FastAPI
app = FastAPI()

# تطبيق تليجرام
telegram_app = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً بك 👋\n\nأهلاً بك في المتجر.\n\nاستخدم:\n/products - عرض المنتجات\n/buy رقم_المنتج - شراء منتج"
    )

async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = supabase.table("deals").select("*").execute()
        deals = res.data or []
        if not deals:
            await update.message.reply_text("لا توجد منتجات متاحة حالياً.")
            return
        
        msg = "🛍 المنتجات المتاحة:\n\n"
        for idx, deal in enumerate(deals, start=1):
            d_id = deal.get("id") or idx
            name = deal.get("product_name") or deal.get("name") or f"منتج {idx}"
            price = deal.get("price") or deal.get("price_usd") or "0"
            curr = deal.get("pay_currency") or "USDT"
            msg += f"🆔 {d_id} | 📦 {name}\n💰 {price} {curr}\n➡️ /buy {d_id}\n\n"
        await update.message.reply_text(msg)
    except Exception as e:
        logger.exception("Error in /products")
        await update.message.reply_text("حدث خطأ أثناء تحميل المنتجات.")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("يرجى كتابة رقم المنتج، مثال:\n/buy 1")
        return
    d_id = context.args[0]
    try:
        res = supabase.table("deals").select("*").eq("id", d_id).execute()
        deals = res.data or []
        if not deals:
            await update.message.reply_text("❌ المنتج غير موجود.")
            return
        deal = deals[0]
        name = deal.get("product_name") or deal.get("name") or "منتج"
        price = deal.get("price") or deal.get("price_usd") or "0"
        curr = deal.get("pay_currency") or "USDT"
        url = deal.get("deal_url") or "لا يوجد رابط"
        await update.message.reply_text(f"📦 المنتج: {name}\n💰 السعر: {price} {curr}\n🔗 الرابط: {url}")
    except Exception:
        await update.message.reply_text("حدث خطأ أثناء جلب تفاصيل المنتج.")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("products", products))
telegram_app.add_handler(CommandHandler("buy", buy))

@app.on_event("startup")
async def startup():
    await telegram_app.initialize()

@app.get("/")
def home():
    return {"status": "ok"}

# هذا المسار يحل مشكلة 405 نهائياً لأنه يقبل POST من تليجرام
@app.post("/")
async def telegram_webhook(request: Request):
    req_json = await request.json()
    update = Update.de_json(req_json, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
