# bot.py
import os
import telegram
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, \
    PicklePersistence
from dotenv import load_dotenv
import pytz
from datetime import time, datetime
import logging
import requests  # Убедитесь, что requests установлен
import json
from config import BOT_TOKEN, WEB_APP_URL  # Добавьте импорт токена из config.py
from app import User, UserRole  # Импортируем модели из app.py (если есть, иначе удалить)

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Укажите ADMIN_ID непосредственно в bot.py
ADMIN_ID = "YOUR_ADMIN_ID"  # Замените на ваш Telegram ID
PORT = int(os.environ.get("PORT", 5000))  # Heroku provides PORT env var

# Состояния для диалога
SET_NAME, SET_TIMEZONE, SET_WORKING_HOURS, SET_WORKING_HOURS_END, SET_ROLE = range(5)

# Вспомогательные функции
def is_admin(user_id):
    return str(user_id) == ADMIN_ID

def get_user_from_api(telegram_id):
    try:
        api_url = f'http://127.0.0.1:8000/api/users/{telegram_id}'
        response = requests.get(api_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching user from API: {e}")
        return None

def is_developer(user_id):
    user = get_user_from_api(user_id)
    return user and user.get('role') == "DEVELOPER"

def is_customer(user_id):
    user = get_user_from_api(user_id)
    return user and user.get('role') == "CUSTOMER"

# --- Обработчики ---
async def start(update: Update, context: CallbackContext):
    """Обрабатывает команду /start."""
    logging.info("Обработка команды /start")  # Добавлено логирование
    user = await authenticate_user(update, context)

    if not user or not user.get('display_name'): # Если пользователь не аутентифицирован или у него нет имени
      await update.message.reply_text("Привет! Я чат-бот для работы с Telegram Web App. Пожалуйста, введите ваше имя, которое будет отображаться в чатах:")
      return SET_NAME

    if not user.get('role'):
        keyboard = [
            ["Разработчик", "Заказчик"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text("Пожалуйста, выберите свою роль:", reply_markup=reply_markup)
        return SET_ROLE

    role = user.get('role')
    welcome_message = f"Привет, {user.get('display_name')} ({role})! " \
                      f"Нажмите кнопку, чтобы открыть веб-приложение:"

    if not WEB_APP_URL:
        await update.message.reply_text("Веб-приложение не настроено. Проверьте файл config.py.")
        return ConversationHandler.END  # Завершить диалог, если нет URL веб-приложения

    keyboard = [
        [KeyboardButton(
            text="Открыть Web App",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    return ConversationHandler.END

async def set_name(update: Update, context: CallbackContext):
    """Обрабатывает установку имени пользователя."""
    logging.info("Обработка ввода имени пользователя")  # Добавлено логирование
    user_name = update.message.text
    context.user_data['user_name'] = user_name
    await update.message.reply_text(f"Отлично, теперь ваше имя: {user_name}. Теперь, пожалуйста, укажите свой часовой пояс (например, Europe/Moscow):")
    return SET_TIMEZONE

async def set_timezone(update: Update, context: CallbackContext):
    """Обрабатывает установку часового пояса пользователя."""
    logging.info("Обработка ввода часового пояса")  # Добавлено логирование
    timezone_str = update.message.text
    try:
        pytz.timezone(timezone_str) # Проверка строки часового пояса
        context.user_data['timezone'] = timezone_str
        await update.message.reply_text(f"Отлично, ваш часовой пояс: {timezone_str}. Теперь укажите ваше рабочее время. Сначала время начала рабочего дня в формате ЧЧ:ММ (например, 09:00)")
        return SET_WORKING_HOURS
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text("Неверный часовой пояс. Пожалуйста, введите часовой пояс, например, Europe/Moscow:")
        return SET_TIMEZONE # Повторить ввод часового пояса

async def set_working_hours(update: Update, context: CallbackContext):
    """Обрабатывает установку рабочего времени пользователя."""
    logging.info("Обработка ввода времени начала работы")  # Добавлено логирование
    try:
        start_time_str = update.message.text
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        context.user_data['working_hours_start'] = start_time

        await update.message.reply_text("Теперь время окончания рабочего дня в формате ЧЧ:ММ (например, 18:00)")
        return SET_WORKING_HOURS_END  # Переход к следующему состоянию для получения времени окончания
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ (например, 09:00)")
        return SET_WORKING_HOURS # Повторить ввод времени начала

async def set_working_hours_end(update: Update, context: CallbackContext):
    """Обрабатывает установку времени окончания рабочего дня пользователя."""
    logging.info("Обработка ввода времени окончания работы")  # Добавлено логирование
    try:
        end_time_str = update.message.text
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        context.user_data['working_hours_end'] = end_time

        # --- Сохранить информацию о пользователе в Flask app ---
        user_id = update.message.from_user.id
        user_name = context.user_data.get('user_name')
        timezone = context.user_data.get('timezone')
        start_time = context.user_data.get('working_hours_start')
        end_time = context.user_data.get('working_hours_end')

        # Подготовить данные для вызова API
        user_data = {
            "telegram_id": user_id,
            "display_name": user_name,
            "timezone": timezone,
            "working_hours_start": start_time.strftime("%H:%M") if start_time else None,  # Format time as string
            "working_hours_end": end_time.strftime("%H:%M") if end_time else None    # Format time as string
        }

        # Log the data being sent
        logging.info(f"Данные для отправки на бэкенд: {user_data}")

        # Вызов API Flask backend
        try:
            #  API Endpoint URL
            api_url = 'http://127.0.0.1:8000/api/users'  # Используем порт 8000
            headers = {'Content-Type': 'application/json'}
            response = requests.post(api_url, headers=headers, data=json.dumps(user_data))
            response.raise_for_status()  # Вызвать исключение для плохих кодов статуса
            await update.message.reply_text(f"Ваши данные успешно сохранены.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при сохранении пользователя: {e}")
            await update.message.reply_text(f"Произошла ошибка при сохранении данных. Обратитесь к администратору.")

        return ConversationHandler.END  # Завершить диалог
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ (например, 18:00)")
        return SET_WORKING_HOURS_END # Повторить ввод времени окончания

async def help_command(update: Update, context: CallbackContext):
    """Обрабатывает команду /help."""
    logging.info("Обработка команды /help")  # Добавлено логирование
    user_id = update.message.from_user.id
    if is_admin(user_id):
        await update.message.reply_text(
            "Доступные команды:\n"
            "/start - Запуск бота и регистрация\n"
            "/help - Помощь\n"
            "/create_room [Название комнаты] - Создать комнату (только для администраторов)\n"
            "/list_rooms - Список комнат, в которых вы состоите\n"
            "/show_users - Посмотреть ID пользователей"
        )
    elif is_developer(user_id):
        await update.message.reply_text(
            "Доступные команды:\n"
            "/start - Запуск бота и регистрация\n"
            "/help - Помощь\n"
            "/list_rooms - Список комнат, в которых вы состоите"
        )
    elif is_customer(user_id):
        await update.message.reply_text(
            "Доступные команды:\n"
            "/start - Запуск бота и регистрация\n"
            "/help - Помощь\n"
            "/list_rooms - Список комнат, в которых вы состоите"
        )

async def create_room(update: Update, context: CallbackContext):
    """Обрабатывает команду /create_room."""
    logging.info("Обработка команды /create_room")  # Добавлено логирование
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("У вас нет прав для создания комнат.")
        return

    room_name = " ".join(context.args) # получить имя комнаты
    if not room_name:
        await update.message.reply_text("Пожалуйста, укажите название комнаты после команды /create_room.")
        return

    #  API Endpoint URL
    api_url = f'http://127.0.0.1:8000/api/rooms'  # Используем порт 8000
    try:
        headers = {'Content-Type': 'application/json'}
        data = {'creator_id': update.message.from_user.id, 'name': room_name}  # Corrected key to "name"
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()

        await update.message.reply_text(f"Комната '{room_name}' успешно создана!")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при создании комнаты: {e}")
        await update.message.reply_text(f"Произошла ошибка при создании комнаты: {e}")

async def list_rooms(update: Update, context: CallbackContext):
    """Обрабатывает команду /list_rooms."""
    logging.info("Обработка команды /list_rooms")  # Добавлено логирование
    try:
        #  API Endpoint URL
        api_url = f'http://127.0.0.1:8000/api/rooms'  # Используем порт 8000
        response = requests.get(api_url)
        response.raise_for_status()
        rooms = response.json()
        room_list = "\n".join([f"- {room['name']}" for room in rooms])
        await update.message.reply_text(f"Вы состоите в следующих комнатах:\n{room_list}")
        logging.info(f"Rooms listed: {room_list}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при получении списка комнат: {e}")
        await update.message.reply_text(f"Произошла ошибка при получении списка комнат: {e}")

async def authenticate_user(update: Update, context: CallbackContext):
    """Authenticates user, creates a new user if not exists."""
    logging.info("Аутентификация пользователя")  # Добавлено логирование
    telegram_id = update.message.from_user.id
    #  API Endpoint URL
    api_url = f'http://127.0.0.1:8000/api/users/{telegram_id}'  # Используем порт 8000
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        user_data = response.json() # Ожидаем данные пользователя в JSON формате
        return user_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при аутентификации пользователя: {e}")
        return None

async def set_role(update: Update, context: CallbackContext):
    """Sets the user's role."""
    logging.info("Обработка выбора роли пользователя")
    role = update.message.text.lower()
    if role not in ["разработчик", "заказчик"]:
        await update.message.reply_text("Пожалуйста, выберите роль из предложенных вариантов.")
        return SET_ROLE

    context.user_data['role'] = role

    # Send data to API to save the user's role
    user_id = update.message.from_user.id
    user_name = context.user_data.get('user_name')
    timezone = context.user_data.get('timezone')
    start_time = context.user_data.get('working_hours_start')
    end_time = context.user_data.get('working_hours_end')

    user_data = {
        "telegram_id": user_id,
        "display_name": user_name,
        "timezone": timezone,
        "working_hours_start": start_time.strftime("%H:%M") if start_time else None,
        "working_hours_end": end_time.strftime("%H:%M") if end_time else None,
        "role": role
    }

    try:
        api_url = 'http://127.0.0.1:8000/api/users'  # Используем порт 8000
        headers = {'Content-Type': 'application/json'}
        response = requests.post(api_url, headers=headers, data=json.dumps(user_data))
        response.raise_for_status()

        await update.message.reply_text(f"Роль успешно установлена как {role}.")
        await start(update, context)  # Go to the next step (start again)
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при сохранении роли пользователя: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении роли. Пожалуйста, попробуйте позже.")

    return ConversationHandler.END

# Add command handler for getting a list of users
async def show_users(update: Update, context: CallbackContext):
    """Lists all users and their IDs to the admin."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("У вас нет прав для просмотра списка пользователей.")
        return

    try:
        api_url = f'http://127.0.0.1:8000/api/users'
        response = requests.get(api_url)
        response.raise_for_status()
        users = response.json()
        if users:
            user_list = "\n".join([f"- {user['display_name']} (ID: {user['telegram_id']})" for user in users])
            await update.message.reply_text(f"Список пользователей:\n{user_list}")
        else:
            await update.message.reply_text("Пользователи не найдены.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при получении списка пользователей: {e}")
        await update.message.reply_text(f"Произошла ошибка при получении списка пользователей: {e}")

async def post_init(application: ApplicationBuilder):
    logging.info("Бот инициализирован") # Добавлено логирование
    await application.bot.set_my_commands([
        ('start', 'Запустить веб-приложение'),
        ('help', 'Помощь'),
        ('create_room', 'Создать комнату (только для администраторов)'),
        ('list_rooms', 'Список комнат, в которых вы состоите'),
        ('show_users', 'Посмотреть ID пользователей'),
    ])

# --- Main ---
def main():
    # Create the Application
    persistence = PicklePersistence(filepath="bot_data")
    application = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).post_init(post_init).build()
    logging.info("ApplicationBuilder успешно создан") # Добавлено логирование

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
            SET_TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_timezone)],
            SET_WORKING_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_working_hours)],
            SET_WORKING_HOURS_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_working_hours_end)],
            SET_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_role)],
        },
        fallbacks=[CommandHandler('cancel', start)]  # Использовать start для отмены
    )
    logging.info("Conversation handler успешно создан") # Добавлено логирование

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("create_room", create_room))
    application.add_handler(CommandHandler("list_rooms", list_rooms))

    # Добавляем новый обработчик для show_users
    application.add_handler(CommandHandler("show_users", show_users))
    logging.info("Все обработчики успешно добавлены")  # Добавлено логирование

    # Замените эту строку (и удалите set_webhook.py!)
    application.run_polling()

    logging.info("Бот запущен в режиме polling")

if __name__ == '__main__':
    main()
