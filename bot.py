import asyncio
import logging
import aiohttp
import random
import re
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL, SYSTEM_PROMPT
from database import add_user, check_subscription

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from aiohttp import web
import threading

async def health_check(request):
    return web.Response(text="OK")

def run_health_server():
    """Запускает простой HTTP сервер для health checks."""
    app = web.Application()
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        loop.run_until_complete(site.start())
        print("Health check server started on port 8080")
        loop.run_forever()
    except Exception as e:
        print(f"Health server error: {e}")

# В функции main():
def main():
    # Запускаем health server в отдельном потоке
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # ... остальной код бота ...

def split_into_separate_messages(text: str) -> list:
    """Разделяет текст на отдельные сообщения по предложениям."""
    # Очищаем текст от лишних пробелов
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Разделяем на предложения
    sentences = re.split(r'(?<=[.!?…]) +', text)
    
    # Объединяем очень короткие предложения
    merged_sentences = []
    current_message = ""
    
    for sentence in sentences:
        if not sentence.strip():
            continue
            
        # Если текущее сообщение слишком короткое, объединяем с следующим
        if len(current_message) < 20 and current_message:
            current_message += " " + sentence
        else:
            if current_message:
                merged_sentences.append(current_message)
            current_message = sentence
    
    if current_message:
        merged_sentences.append(current_message)
    
    # Добавляем эмодзи к некоторым сообщениям
    result = []
    for i, message in enumerate(merged_sentences):
        # Добавляем эмодзи к каждому 2-3 сообщению
        if i % 4 == 0 and random.random() < 0.2:
            emojis = ['😊', '💫', '✨', '🤔', '💭', '❤️', '😂', '🎉', '👀', '🤗']
            message += f" {random.choice(emojis)}"
        result.append(message)
    
    return result

async def get_ai_response(user_message: str, user_id: int) -> str:
    """Запрос к API."""
    try:
        from database import add_message, get_recent_messages
        
        add_message(user_id, "user", user_message)
        chat_history = get_recent_messages(user_id, limit=8)
        messages_for_api = [SYSTEM_PROMPT] + chat_history

        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages_for_api,
            "max_tokens": 150,  # Уменьшаем для более коротких ответов
            "temperature": 0.8,
        }

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_API_URL, json=payload, headers=headers, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()
                
                if 'choices' in data and len(data['choices']) > 0:
                    ai_response = data['choices'][0]['message']['content'].strip()
                    add_message(user_id, "assistant", ai_response)
                    return ai_response
                else:
                    return "Интересно! Расскажи мне больше?"

    except Exception as e:
        logger.error(f"Ошибка в get_ai_response: {e}")
        return "Извини, я немного задумалась... О чем расскажешь?"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик с отправкой каждого предложения как отдельного сообщения."""
    try:
        user = update.effective_user
        user_message = update.message.text

        if not check_subscription(user.id):
            keyboard = get_main_keyboard(user.id)
            await update.message.reply_text(
                "К сожалению, твой пробный период закончился 😔",
                reply_markup=keyboard
            )
            return

        # Показываем активность
        await update.message.chat.send_action(action="typing")
        await asyncio.sleep(1.0)  # Дольше для "обдумывания"

        # Получаем ответ от AI
        ai_response = await get_ai_response(user_message, user.id)
        
        logger.info(f"Получен ответ: {ai_response}")
        
        # Разделяем на отдельные сообщения
        message_parts = split_into_separate_messages(ai_response)
        
        logger.info(f"Разделено на {len(message_parts)} сообщений: {message_parts}")

        # Отправляем каждое сообщение отдельно
        for i, part in enumerate(message_parts):
            if i > 0:  # Для всех сообщений кроме первого
                # Случайная пауза между сообщениями (0.8-1.5 секунды)
                pause_time = random.uniform(0.8, 1.5)
                await asyncio.sleep(pause_time)
                
                # Показываем "печатает" перед каждым сообщением
                await update.message.chat.send_action(action="typing")
                await asyncio.sleep(0.4)
            
            # Клавиатуру добавляем только к последнему сообщению
            keyboard = get_main_keyboard(user.id) if i == len(message_parts) - 1 else None
            
            await update.message.reply_text(part, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")
        # Отправляем несколько сообщений об ошибке
        error_messages = [
            "Упс... что-то пошло не так 😅",
            "Давай попробуем еще раз? 💫",
            "Расскажи мне что-нибудь! 😊"
        ]
        
        for i, msg in enumerate(error_messages):
            if i > 0:
                await asyncio.sleep(0.8)
            keyboard = get_main_keyboard(user.id) if i == len(error_messages) - 1 else None
            await update.message.reply_text(msg, reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    try:
        user = update.effective_user
        add_user(user.id, user.username, user.full_name)

        # Отправляем несколько приветственных сообщений
        welcome_messages = [
            f"Привет, {user.first_name}! 👋",
            "Меня зовут Анна! 💫",
            "Я здесь, чтобы поддержать тебя и поболтать на разные темы ✨",
            "У тебя есть пробный период на 24 часа! 🎉",
            "Просто напиши мне сообщение"
        ]
        
        for i, message in enumerate(welcome_messages):
            if i > 0:
                await asyncio.sleep(0.8)
            keyboard = get_main_keyboard(user.id) if i == len(welcome_messages) - 1 else None
            await update.message.reply_text(message, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        error_messages = [
            "Привет! 👋",
            "Рада тебя видеть! 😊",
            "Напиши мне что-нибудь! 💭"
        ]
        for i, msg in enumerate(error_messages):
            if i > 0:
                await asyncio.sleep(0.6)
            await update.message.reply_text(msg)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки."""
    try:
        user = update.effective_user
        text = update.message.text
        
        if text == "👤 Мой профиль":
            await profile(update, context)
        elif text == "💎 Купить подписку":
            # Отправляем информацию о подписке несколькими сообщениями
            subscription_messages = [
                "💎 <b>Премиум подписка</b>",
                "• 🗣️ Неограниченное общение",
                "• 💾 Сохранение истории", 
                "• ⚡ Приоритетная обработка",
                "• 🎁 Эксклюзивные функции",
                "Стоимость: 299 руб./месяц 💫",
                "Напиши @dirtydonny для оформления! 😊"
            ]
            
            for i, msg in enumerate(subscription_messages):
                if i > 0:
                    await asyncio.sleep(0.7)
                parse_mode = 'HTML' if i == 0 else None
                await update.message.reply_text(msg, parse_mode=parse_mode)
                
        elif text == "💬 Написать сообщение":
            # Отправляем приглашение несколькими сообщениями
            invitation_messages = [
                "Отлично! 💫",
                "Я слушаю тебя... 👂",
                "Расскажи мне что-нибудь! 💖",
                "О чем хочешь поговорить? 😊"
            ]
            
            for i, msg in enumerate(invitation_messages):
                if i > 0:
                    await asyncio.sleep(0.6)
                keyboard = get_main_keyboard(user.id) if i == len(invitation_messages) - 1 else None
                await update.message.reply_text(msg, reply_markup=keyboard)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_button: {e}")
        error_messages = [
            "Ой... 😅",
            "Что-то пошло не так с кнопками...",
            "Попробуй еще раз! 💫"
        ]
        for i, msg in enumerate(error_messages):
            if i > 0:
                await asyncio.sleep(0.6)
            await update.message.reply_text(msg)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает профиль пользователя несколькими сообщениями."""
    try:
        user = update.effective_user
        from database import get_user_profile, check_subscription
        
        profile_data = get_user_profile(user.id)
        
        if not profile_data:
            await update.message.reply_text("Сначала напиши /start для регистрации!")
            return
        
        has_active_subscription = check_subscription(user.id)
        
        from datetime import datetime
        created_date = datetime.strptime(profile_data['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        
        # Отправляем информацию о профиле несколькими сообщениями
        profile_messages = [
            f"👤 <b>Твой профиль</b>",
            f"📛 Имя: {profile_data['full_name'] or 'Не указано'}",
            f"📅 Регистрация: {created_date}",
            f"📨 Сообщений: {profile_data['message_count']}",
            f"💎 <b>Статус:</b> {'✅ Активна' if has_active_subscription else '❌ Не активна'}"
        ]
        
        if not has_active_subscription:
            profile_messages.append("💫 Напиши @dirtydonny чтобы продолжить общение!")
        
        for i, msg in enumerate(profile_messages):
            if i > 0:
                await asyncio.sleep(0.7)
            parse_mode = 'HTML' if i == 0 or i == 4 else None
            keyboard = get_main_keyboard(user.id) if i == len(profile_messages) - 1 else None
            await update.message.reply_text(msg, parse_mode=parse_mode, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка в profile: {e}")
        error_messages = [
            "Не могу загрузить профиль... 😔",
            "Попробуй позже! 💫"
        ]
        for i, msg in enumerate(error_messages):
            if i > 0:
                await asyncio.sleep(0.6)
            await update.message.reply_text(msg)

def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    """Создает главную клавиатуру."""
    try:
        has_subscription = check_subscription(user_id) if user_id else False
        
        keyboard = [
            [KeyboardButton("💬 Написать сообщение")],
            [KeyboardButton("👤 Мой профиль")]
        ]
        
        if not has_subscription:
            keyboard.append([KeyboardButton("💎 Купить подписку")])
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
    
    except Exception as e:
        logger.error(f"Ошибка в get_main_keyboard: {e}")
        return ReplyKeyboardMarkup([[KeyboardButton("💬 Написать сообщение")]], resize_keyboard=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    try:
        if update and update.message:
            error_messages = [
                "Упс... что-то пошло не так 😅",
                "Давай попробуем еще раз? 💫"
            ]
            for i, msg in enumerate(error_messages):
                if i > 0:
                    await asyncio.sleep(0.7)
                await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

def main():
    """Основная функция запуска бота."""
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("profile", profile))
        application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^(💬 Написать сообщение|👤 Мой профиль|💎 Купить подписку)$'), handle_button))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        print("🤖 Бот запущен! Отправляет несколько сообщений вместо одного! 🚀")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()
