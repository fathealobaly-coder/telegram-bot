import os
import sys
import time
import logging
import threading
import requests
import telebot
from fastapi import FastAPI, Request
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# قراءة المتغيرات السرية من Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
CALLBACK_URL = os.getenv("NOWPAYMENTS_CALLBACK_URL")

NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/payment"

def validate_environment():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not NOWPAYMENTS_API_KEY: missing.append("NOWPAYMENTS_API_KEY")
    if not SUPABASE_URL: missing.append("SUPABASE_URL")
    if not SUPABASE_KEY: missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        logger.error("MISSING ENVIRONMENT VARIABLES: %s", ", ".join(missing))
        sys.exit(1)

validate_environment()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
app = FastAPI()

# دالة تسليم المنتج من Supabase
def deliver_product(chat_id: str, file_path: str = "gaming_vault .zip"):
    bucket = "digital-products"
    logger.info("جاري تحميل الملف %s للمستخدم %s", file_path, chat_id)
    
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
    }
    
    download_url = f"{SUPABASE_URL}/storage/v1/object/authenticated/{bucket}/{requests.utils.quote(file_path, safe='/')}"
    res = requests.get(download_url, headers=headers, timeout=120)
    
    if res.status_code != 200:
        alt_url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{requests.utils.quote(file_path, safe='/')}"
        res = requests.get(alt_url, headers=headers, timeout=120)
        
    res.raise_for_status()
    
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    tg_res = requests.post(
        telegram_url,
        data={"chat_id": chat_id, "caption": "تم تأكيد دفعك بنجاح! إليك ملف التحميل الخاص بك."},
        files={"document": ("gaming_vault.zip", res.content, "application/zip")},
        timeout=120
    )
    tg_res.raise_for_status()
    logger.info("تم تسليم الملف بنجاح إلى %s", chat_id)

# Webhook لاستقبال تأكيد الدفع من NOWPayments
@app.post("/webhook/nowpayments")
async def nowpayments_webhook(request: Request):
    data = await request.json()
    logger.info("تم استلام إشعار دفع: %s", data)
    
    payment_status = data.get("payment_status")
    order_id = data.get("order_id", "")
    
    # عند اكتمال الدفع بنجاح
    if payment_status in ["finished", "confirmed"]:
        parts = order_id.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            user_chat_id = parts[1]
            try:
                deliver_product(user_chat_id)
            except Exception as e:
                logger.exception("فشل تسليم المنتج تلقائياً: %s", e)
    return {"status": "ok"}

# أوامر البوت
@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.reply_to(message, "مرحباً بك في المتجر الرقمي.\n\nالأوامر المتاحة:\n/products - عرض المنتجات\n/buy - إنشاء طلب دفع")

@bot.message_handler(commands=["products"])
def products_handler(message):
    bot.reply_to(message, "المنتجات المتاحة:\n\n1. Gaming Digital Vault\n\nاستخدم /buy لإنشاء طلب دفع.")

@bot.message_handler(commands=["buy"])
def buy_handler(message):
    chat_id = message.from_user.id
    order_id = f"TG-{chat_id}-{message.message_id}"
    
    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "price_amount": 15.00,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
        "ipn_callback_url": CALLBACK_URL,
        "order_id": order_id,
        "order_description": "Gaming Digital Vault"
    }
    try:
        res = requests.post(NOWPAYMENTS_URL, headers=headers, json=payload, timeout=30)
        res.raise_for_status()
        payment = res.json()
        
        bot.reply_to(
            message,
            f"تم إنشاء طلب الدفع بنجاح.\n\n"
            f"رقم الطلب: {order_id}\n"
            f"المبلغ المطلوب: {payment.get('pay_amount')} {payment.get('pay_currency')}\n\n"
            f"عنوان المحفظة للدفع:\n`{payment.get('pay_address')}`\n\n"
            f"بمجرد وصول التحويل، سيصلك الملف هنا تلقائياً.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("خطأ في إنشاء طلب الدفع: %s", e)
        bot.reply_to(message, "حدث خطأ أثناء الاتصال ببوابة الدفع.")

def run_telebot():
    bot.remove_webhook()
    time.sleep(2)
    bot.infinity_polling(timeout=30, long_polling_timeout=30, skip_pending=True)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_telebot, daemon=True)
    bot_thread.start()
    
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
