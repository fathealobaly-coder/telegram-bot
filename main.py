import os
import telebot

# جلب توكن البوت من المتغيرات
BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع_توكن_البوت_هنا")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "مرحباً بك! البوت يعمل الآن بنجاح على Railway 🚀")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)

if __name__ == "__main__":
    print("البوت بدأ العمل...")
    bot.infinity_polling()
