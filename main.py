import os
import sys
import time
import logging

import requests
import telebot


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")

NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/payment"

CALLBACK_URL = os.getenv(
    "NOWPAYMENTS_CALLBACK_URL",
    "https://YOUR-RAILWAY-DOMAIN/webhook/nowpayments"
)


def validate_environment():
    missing = []

    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")

    if not NOWPAYMENTS_API_KEY:
        missing.append("NOWPAYMENTS_API_KEY")

    if missing:
        logger.error(
            "MISSING ENVIRONMENT VARIABLES: %s",
            ", ".join(missing)
        )
        logger.error(
            "Add these variables in Railway Service -> Variables."
        )
        sys.exit(1)

    logger.info("Environment variables verified successfully.")


validate_environment()


bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode=None
)


def create_nowpayments_payment(
    price_usd,
    order_id,
    product_name
):
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "price_amount": float(price_usd),
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
        "ipn_callback_url": CALLBACK_URL,
        "order_id": str(order_id),
        "order_description": product_name
    }

    logger.info(
        "Creating NOWPayments payment for order %s",
        order_id
    )

    response = requests.post(
        NOWPAYMENTS_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    logger.info(
        "NOWPayments HTTP status: %s",
        response.status_code
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("payment_id"):
        raise RuntimeError(
            "NOWPayments response does not contain payment_id"
        )

    if not data.get("pay_address"):
        raise RuntimeError(
            "NOWPayments response does not contain pay_address"
        )

    if not data.get("pay_amount"):
        raise RuntimeError(
            "NOWPayments response does not contain pay_amount"
        )

    return data


@bot.message_handler(commands=["start"])
def start_handler(message):
    logger.info(
        "Received /start from Telegram user %s",
        message.from_user.id
    )

    bot.reply_to(
        message,
        "مرحباً بك في المتجر الرقمي.\n\n"
        "الأوامر المتاحة:\n"
        "/products - عرض المنتجات\n"
        "/buy - إنشاء طلب دفع"
    )


@bot.message_handler(commands=["products"])
def products_handler(message):
    logger.info(
        "Received /products from Telegram user %s",
        message.from_user.id
    )

    bot.reply_to(
        message,
        "المنتجات المتاحة:\n\n"
        "1. Gaming Digital Vault\n"
        "2. Mobile Repair Pro\n"
        "3. Smart Profit Manager\n"
        "4. AI Sales Master Pack\n"
        "5. Startup Business Plan Kit\n\n"
        "استخدم /buy لإنشاء طلب دفع."
    )


@bot.message_handler(commands=["buy"])
def buy_handler(message):
    telegram_user_id = message.from_user.id
    telegram_message_id = message.message_id

    order_id = (
        f"TG-{telegram_user_id}-{telegram_message_id}"
    )

    product_name = "Smart Profit Manager"
    price_usd = 15.00

    logger.info(
        "Creating order %s for Telegram user %s",
        order_id,
        telegram_user_id
    )

    try:
        payment = create_nowpayments_payment(
            price_usd=price_usd,
            order_id=order_id,
            product_name=product_name
        )

        payment_id = payment.get("payment_id")
        pay_address = payment.get("pay_address")
        pay_amount = payment.get("pay_amount")
        pay_currency = payment.get("pay_currency")

        bot.reply_to(
            message,
            "تم إنشاء طلب الدفع بنجاح.\n\n"
            f"رقم الطلب: {order_id}\n"
            f"Payment ID: {payment_id}\n"
            f"المبلغ المطلوب: {pay_amount} {pay_currency}\n\n"
            f"عنوان الدفع:\n{pay_address}\n\n"
            "أرسل المبلغ المطلوب إلى العنوان أعلاه.\n"
            "سيتم تحديث حالة الدفع بواسطة NOWPayments."
        )

        logger.info(
            "Payment created successfully: %s",
            payment_id
        )

    except requests.exceptions.HTTPError as error:
        logger.exception(
            "NOWPayments HTTP error: %s",
            error
        )

        try:
            error_body = error.response.text
        except Exception:
            error_body = "No response body available."

        logger.error(
            "NOWPayments response: %s",
            error_body
        )

        bot.reply_to(
            message,
            "تعذر إنشاء طلب الدفع حالياً.\n"
            "راجع سجلات Railway لمعرفة الخطأ."
        )

    except requests.exceptions.RequestException as error:
        logger.exception(
            "NOWPayments network error: %s",
            error
        )

        bot.reply_to(
            message,
            "حدث خطأ في الاتصال بخدمة الدفع.\n"
            "حاول مرة أخرى."
        )

    except Exception as error:
        logger.exception(
            "Unexpected /buy error: %s",
            error
        )

        bot.reply_to(
            message,
            "حدث خطأ أثناء إنشاء طلب الدفع."
        )


@bot.message_handler(
    func=lambda message: True,
    content_types=["text"]
)
def text_handler(message):
    bot.reply_to(
        message,
        "استخدم:\n"
        "/start\n"
        "/products\n"
        "/buy"
    )


def start_bot():
    logger.info("Starting Telegram bot...")

    try:
        logger.info("Removing existing Telegram webhook...")

        bot.remove_webhook()

        logger.info(
            "Telegram webhook removed successfully."
        )

        time.sleep(2)

    except Exception as error:
        logger.exception(
            "Webhook removal failed: %s",
            error
        )

    while True:
        try:
            logger.info(
                "Starting Telegram long polling..."
            )

            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                skip_pending=True
            )

            logger.warning(
                "Polling stopped unexpectedly. Restarting..."
            )

        except KeyboardInterrupt:
            logger.info(
                "Bot stopped manually."
            )
            break

        except Exception as error:
            logger.exception(
                "Telegram polling crashed: %s",
                error
            )

            logger.info(
                "Restarting polling in 5 seconds..."
            )

            time.sleep(5)


if __name__ == "__main__":
    start_bot()
