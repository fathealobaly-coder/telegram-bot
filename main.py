import os
import telebot
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")

if not NOWPAYMENTS_API_KEY:
    raise RuntimeError("NOWPAYMENTS_API_KEY is not configured")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=["start"])
def start_handler(message):
    bot.reply_to(message, "مرحباً بك في المتجر الرقمي!\n\n/products - عرض المنتجات\n/buy - الشراء")

@bot.message_handler(commands=["products"])
def products_handler(message):
    bot.reply_to(message, "قائمة المنتجات:\n1. Digital Vault\n2. Smart Profit\nالسعر: $5 أرسل /buy للشراء")

@bot.message_handler(commands=["buy"])
def buy_handler(message):
    bot.reply_to(message, "جاري إنشاء رابط الفاتورة...")
    url = "https://api.nowpayments.io/v1/invoice"
    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "price_amount": 5.0,
        "price_currency": "usd",
        "order_description": f"User {message.chat.id}"
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=20)
        data = res.json()
        if "invoice_url" in data:
            bot.send_message(message.chat.id, f"تم إنشاء الفاتورة ✅:\n{data['invoice_url']}")
        else:
            bot.send_message(message.chat.id, "حدث خطأ من بوابة الدفع ❌")
    except Exception as e:
        bot.send_message(message.chat.id, f"فشل الاتصال: {e}")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, "أرسل /start أو /products أو /buy")

if __name__ == "__main__":
    print("البوت شغال...")
    bot.infinity_polling(skip_pending=True)
