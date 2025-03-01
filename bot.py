import os
import logging
import json
import pytz
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, WebAppInfo, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, PicklePersistence
from config import BOT_TOKEN, WEB_APP_URL

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Константы
ADMIN_ID = "6441610380"
PORT = int(os.environ.get("PORT", 5000))
SET_NAME, SET_TIMEZONE, SET_WORKING_HOURS, SET_WORKING_HOURS_END, SET_ROLE = range(5)

# Вспомогательные функции
def is_admin(user_id):
    return str(user_id) == ADMIN_ID

def get_user_from_api(telegram_id):
    try:
        response = requests.get(f'https://Werdsaf.pythonanywhere.com/api/users/{telegram_id}')
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching user from API: {e}")
        return None

def is_developer(user_id):
    user = get_user_from_api(user_id)
    return user and user.get('role') == "developer"

def is_customer(user_id):
    user = get_user_from_api(user_id)
    return user and user.get('role') == "customer"

# Обработчики
async def start(update: Update, context: CallbackContext):
    user = get_user_from_api(update.message.from_user.id)
    if not user or not user.get('display_name'):
        await update.message.reply_text("Привет! Введите ваше имя:")
        return SET_NAME
    if not user.get('role'):
        await update.message.reply_text("Выберите роль:", reply_markup=ReplyKeyboardMarkup([["Разработчик", "Заказчик"]], one_time_keyboard=True))
        return SET_ROLE
    await update.message.reply_text(
        f"Привет, {user.get('display_name')} ({user.get('role')})! Нажмите кнопку, чтобы открыть веб-приложение:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Открыть Web App", web_app=WebAppInfo(url=WEB_APP_URL))]], resize_keyboard=True)
    )
    return ConversationHandler.END

async def set_name(update: Update, context: CallbackContext):
    context.user_data['user_name'] = update.message.text
    await update.message.reply_text("Укажите ваш часовой пояс (например, Europe/Moscow):")
    return SET_TIMEZONE

async def set_timezone(update: Update, context: CallbackContext):
    try:
        pytz.timezone(update.message.text)
        context.user_data['timezone'] = update.message.text
        await update.message.reply_text("Укажите время начала рабочего дня (например, 09:00):")
        return SET_WORKING_HOURS
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text("Неверный часовой пояс. Попробуйте снова:")
        return SET_TIMEZONE

async def set_working_hours(update: Update, context: CallbackContext):
    try:
        context.user_data['working_hours_start'] = datetime.strptime(update.message.text, "%H:%M").time()
        await update.message.reply_text("Укажите время окончания рабочего дня (например, 18:00):")
        return SET_WORKING_HOURS_END
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Попробуйте снова:")
        return SET_WORKING_HOURS

async def set_working_hours_end(update: Update, context: CallbackContext):
    try:
        context.user_data['working_hours_end'] = datetime.strptime(update.message.text, "%H:%M").time()
        user_data = {
            "telegram_id": update.message.from_user.id,
            "display_name": context.user_data.get('user_name'),
            "timezone": context.user_data.get('timezone'),
            "working_hours_start": context.user_data.get('working_hours_start').strftime("%H:%M"),
            "working_hours_end": context.user_data.get('working_hours_end').strftime("%H:%M")
        }
        requests.post('https://Werdsaf.pythonanywhere.com/api/users', headers={'Content-Type': 'application/json'}, data=json.dumps(user_data))
        await update.message.reply_text("Данные успешно сохранены.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Попробуйте снова:")
        return SET_WORKING_HOURS_END

async def help_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if is_admin(user_id):
        await update.message.reply_text(
            "/start - Запуск\n"
            "/help - Помощь\n"
            "/create_room [Название] - Создать комнату\n"
            "/list_rooms - Список комнат\n"
            "/list_users - Список пользователей"
        )
    else:
        await update.message.reply_text(
            "/start - Запуск\n"
            "/help - Помощь\n"
            "/list_rooms - Список комнат"
        )

async def list_users(update: Update, context: CallbackContext):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("У вас нет прав.")
        return
    try:
        users = requests.get('https://Werdsaf.pythonanywhere.com/api/users').json()
        await update.message.reply_text("\n".join([f"- {user['display_name']} (ID: {user['telegram_id']})" for user in users]))
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def create_room(update: Update, context: CallbackContext):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("У вас нет прав.")
        return
    room_name = " ".join(context.args)
    if not room_name:
        await update.message.reply_text("Укажите название комнаты.")
        return
    try:
        requests.post('https://Werdsaf.pythonanywhere.com/api/rooms', json={'creator_id': update.message.from_user.id, 'name': room_name})
        await update.message.reply_text(f"Комната '{room_name}' создана!")
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def list_rooms(update: Update, context: CallbackContext):
    try:
        rooms = requests.get('https://Werdsaf.pythonanywhere.com/api/rooms').json()
        await update.message.reply_text("\n".join([f"- {room['name']}" for room in rooms]))
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def post_init(application):
    await application.bot.set_my_commands([
        ('start', 'Запустить веб-приложение'),
        ('help', 'Помощь'),
        ('create_room', 'Создать комнату'),
        ('list_rooms', 'Список комнат'),
        ('list_users', 'Список пользователей'),
    ])

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).persistence(PicklePersistence(filepath="bot_data")).post_init(post_init).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
            SET_TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_timezone)],
            SET_WORKING_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_working_hours)],
            SET_WORKING_HOURS_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_working_hours_end)],
        },
        fallbacks=[CommandHandler('cancel', start)]
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("create_room", create_room))
    application.add_handler(CommandHandler("list_rooms", list_rooms))
    application.add_handler(CommandHandler("list_users", list_users))
    application.run_polling()

if __name__ == '__main__':
    main()