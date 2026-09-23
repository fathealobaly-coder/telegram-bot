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
    bot.reply_to(
        message,
        "مرحباً بك في المتجر الرقمي!\n\n"
        "للإطلاع على قائمة المنتجات أرسل:\n/products\n\n"
        "لطلب وشراء منتج تجريبي أرسل:\n/buy"
    )


@bot.message_handler(commands=["products"])
def products_handler(message):
    bot.reply_to(
        message,
        "المنتجات المتاحة:\n"
        "1. Gaming Digital Vault\n"
        "2. Mobile Repair Pro\n"
        "3. Smart Profit Manager\n"
        "4. AI Sales Master Pack\n"
        "5. Startup Business Plan Kit\n\n"
        "لشراء المنتج الحالي (Smart Profit Manager) بسعر 5$ أرسل:\n/buy"
    )


@bot.message_handler(commands=["buy", "pay"])
def buy_handler(message):
    bot.reply_to(message, "جاري إنشاء رابط الفاتورة، انتظر لحظة...")

    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "price_amount": 5.0,
        "price_currency": "usd",
        "order_description": f"Purchase for user {message.chat.id}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        data = response.json()

        if "invoice_url" in data:
            bot.send_message(
                message.chat.id,
                f"✅ تم تجهيز الفاتورة بنجاح!\n\n"
                f"المبلغ: 5.00 USD (اختر العملة التي تناسبك للدفع)\n\n"
                f"اضغط على الرابط التالي للسداد:\n{data['invoice_url']}"
            )
        else:
            bot.send_message(
                message.chat.id,
                f"❌ حدث خطأ من بوابة الدفع:\n{data.get('message', 'خطأ غير معروف')}"
            )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ فشل الاتصال بخادم الدفع: {str(e)}"
        )


@bot.message_handler(func=lambda message: True, content_types=["text"])
def text_handler(message):
    bot.reply_to(
        message,
        "استخدم /products لعرض المنتجات أو /buy لطلب الفاتورة."
    )


if __name__ == "__main__":
    print("البوت بدأ العمل بنجاح...")
    bot.infinity_polling(skip_pending=True)
