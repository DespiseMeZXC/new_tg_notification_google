import os
import asyncio
import logging
import signal
import sys
import json
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ForceReply,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.utils.markdown import hbold
from dotenv import load_dotenv

from google_calendar_client import GoogleCalendarClient
from queries import DatabaseQueries
from services import BotService
from inline_buttons import StatisticsCallbackFactory, FeedbackCallbackFactory
from buttons import KeyboardAccount, KeyboardAccountsList, KeyboardAccountActions
# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent

# Инициализация бота и диспетчера
db = DatabaseQueries(os.getenv("DATABASE_URL"))
calendar_client = GoogleCalendarClient(db)
bot = Bot(token=str(os.getenv("BOT_TOKEN")))
bot_service = BotService(db, calendar_client, bot)
dp = Dispatcher()


# Функция для периодической отправки сообщений
async def schedule_meetings_check():
    """"""
    while True:
        try:
            # Получаем всех пользователей из базы
            users = db.tokens.get_all_users()
            for user in users:
                (
                    success,
                    error_message,
                    meetings_by_day,
                    active_events,
                    deleted_events,
                    updated_events,
                ) = await bot_service.get_check_meetings(user)
                event_ids = tuple(event["id"] for event in active_events)
                if updated_events:
                    await bot_service.send_updated_events(user, updated_events)
                if deleted_events:
                    await bot_service.send_deleted_events(user, deleted_events)
                if db.notifications.check_all_notifications_sent(event_ids, user):
                    continue
                for i in range(len(active_events)):
                    status = db.events.save_event(user, active_events[i])
                await bot_service.send_meetings_check_by_day(user, meetings_by_day)
                if not success:
                    await bot.send_message(user, error_message)
        except Exception as e:
            logging.error(f"Ошибка при выполнении проверки встреч: {e}")
        await asyncio.sleep(int(os.getenv("CHECK_INTERVAL", 150)))
        # await asyncio.sleep(10)


# Добавляем обработчик сигналов для корректного завершения
async def on_shutdown(signal_type):
    """Корректное завершение работы бота при получении сигнала"""
    logging.info(f"Получен сигнал {signal_type.name}, завершаю работу...")

    # Закрываем соединения с базой данных
    db.db.close_all_sessions()

    # Закрываем сессию бота
    await bot.session.close()

    sys.exit(0)


# Команда /start
@dp.message(Command("start"))
async def command_start(message: Message) -> None:
    if message.from_user is None:
        logging.error("Не удалось получить пользователя из сообщения")
        return
    
    user_data = {
        "id": message.from_user.id,
        "username": message.from_user.username or "",
        "full_name": message.from_user.full_name or "",
        "is_bot": message.from_user.is_bot,
        "language_code": message.from_user.language_code or "",
    }
    
    db.users.add_user(user_data)
    user_id = message.from_user.id

    await message.answer(
        f"Привет, {message.from_user.full_name if message.from_user.full_name else 'пользователь'}!\n"
        "Я буду отправлять уведомления о предстоящих созвонах в Google Meet.\n\n"
        "Для начала работы вам нужно авторизоваться в Google Calendar.\n"
        "Выберите подходящий способ авторизации:\n\n"
        "1. Через браузер с кодом авторизации: /auth (Рекомендуется)\n"
        "2. Ручной ввод токена (для продвинутых пользователей): /manualtoken\n"
        "Если вы ещё не получали доступ к боту или у вас возникли проблемы, или предложения, напишите разработчику @ImTaske\n"
        "Обратную связь можно оставить с помощью команды /feedback",
        reply_markup=KeyboardAccount().keyboard_account
    )

    logging.info(
        f"Команда /start от пользователя ID: {user_id}, имя: {message.from_user.full_name if message.from_user.full_name else 'Неизвестно'}"
    )
    
    
@dp.message(F.text == "🔐 Аккаунты Google")
async def accounts_command(message: Message) -> None:
    if not message.from_user:
        return
    
    user_tokens = db.tokens.get_all_tokens_by_user_id(message.from_user.id)
    if not user_tokens:
        await message.answer(
            "У вас пока нет привязанных аккаунтов Google.\n"
            "Для добавления используйте команду /auth"
        )
        return

    user_emails = [f"🔐 Информация об аккаунте {token.email}" for token in user_tokens if token.email]
   
    await message.answer(
        "Выберите действие:",
        reply_markup=KeyboardAccountsList().get_keyboard_accounts_list(user_emails)
    )


@dp.message(F.text == "🔐 Добавить аккаунт")
async def add_account_command(message: Message) -> None:
    await message.answer("В разработке...")


@dp.message(lambda message: message.text and message.text.startswith("🔐 Информация об аккаунте ") and "@" in message.text)
async def account_info(message: Message) -> None:
    if not message.from_user:
        return
        
    email = message.text.replace("🔐 Информация об аккаунте ", "")
    user_tokens = db.tokens.get_all_tokens_by_user_id(message.from_user.id)
    selected_token = next((token for token in user_tokens if token.email == email), None)
    
    if selected_token:
        await message.answer(
            f"Информация об аккаунте:\n"
            f"Email: {email}\n"
            f"Дата добавления: {selected_token.created_at.strftime('%d.%m.%Y %H:%M')}\n",
            reply_markup=KeyboardAccountActions().get_keyboard_account_actions()
        )
    else:
        await message.answer(
            "Аккаунт не найден.",
            reply_markup=KeyboardAccount().keyboard_account
        )

@dp.message(F.text == "🔐 Удалить аккаунт")
async def handle_account_select(message: Message) -> None:
    if not message.from_user:
        return
    user_tokens = db.tokens.get_all_tokens_by_user_id(message.from_user.id)
    if not user_tokens:
        await message.answer(
            "У вас пока нет привязанных аккаунтов Google.\n"
            "Для добавления используйте команду /auth"
        )
        return

    # Формируем список кнопок в формате "❌ Удалить email@gmail.com"
    user_emails = [f"❌ Удалить {token.email}" for token in user_tokens if token.email]
    await message.answer(
        f"Выберите аккаунт для удаления:",
        reply_markup=KeyboardAccountsList().get_keyboard_accounts_list(user_emails)
    )

@dp.message(lambda message: message.text.startswith("❌ Удалить ") and "@" in message.text)
async def delete_specific_account(message: Message) -> None:
    if not message.from_user:
        return
        
    # Извлекаем email из текста кнопки
    email = message.text.replace("❌ Удалить ", "")
    user_tokens = db.tokens.get_all_tokens_by_user_id(message.from_user.id)
    selected_token = next((token for token in user_tokens if token.email == email), None)
    
    if selected_token:
        if db.tokens.delete_token_by_user_id(message.from_user.id):
            await message.answer(
                f"Аккаунт {email} успешно удален.",
                reply_markup=KeyboardAccount().keyboard_account
            )
        else:
            await message.answer(
                "Произошла ошибка при удалении аккаунта. Попробуйте позже.",
                reply_markup=KeyboardAccount().keyboard_account
            )
    else:
        await message.answer(
            "Аккаунт не найден.",
            reply_markup=KeyboardAccount().keyboard_account
        )
            
# Команда /auth для авторизации на сервере
@dp.message(Command("auth"))
async def server_auth_command(message: Message) -> None:
    if not message.from_user:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    auth_url = calendar_client.create_auth_url(message.from_user.id)

    if isinstance(auth_url, str) and auth_url.startswith("Ошибка"):
        await message.answer(
            f"❌ {auth_url}\n" "Пожалуйста, сообщите об этой ошибке администратору."
        )
        return
    # Отправляем сообщение с инструкцией и сохраняем его ID
    auth_message = await message.answer(
        "📱 <b>Инструкция по авторизации на сервере:</b>\n\n"
        "1️⃣ Перейдите по ссылке ниже в браузере:\n"
        f"{auth_url}\n\n"
        "2️⃣ Войдите в аккаунт Google и разрешите доступ к календарю\n\n"
        "3️⃣ Вы получите код авторизации. Скопируйте его и отправьте в ответ на это сообщение\n\n"
        "❗ Если возникает ошибка при авторизации:\n"
        "- Убедитесь, что вы используете личный аккаунт Google (не корпоративный)\n"
        "- Попробуйте открыть ссылку в режиме инкогнито\n"
        "- Или используйте команду /manualtoken\n"
        "Если ничего не помогает, обратитесь к разработчику @ImTaske",
        parse_mode="HTML",
        reply_markup=ForceReply(
            selective=True, input_field_placeholder="Вставьте код авторизации"
        ),
    )
    db.tokens.set_auth_message_id(message.from_user.id, str(auth_message.message_id))


# Обработчик для кода авторизации - используем фильтр F.reply_to_message
@dp.message(F.reply_to_message)
async def handle_reply(message: Message) -> None:
    """Обрабатывает все ответы на сообщения"""
    user_id = message.from_user.id

    # Проверяем, является ли это ответом на сообщение авторизации
    auth_message_id = db.tokens.get_auth_message_id(user_id)
    if auth_message_id and int(message.reply_to_message.message_id) == int(
        auth_message_id
    ):
        await handle_auth_code_logic(message)
        return

    # Проверяем, является ли это ответом на сообщение обратной связи
    feedback_message_id = db.feedback.get_feedback_message_id(user_id)
    if feedback_message_id and int(message.reply_to_message.message_id) == int(
        feedback_message_id
    ):
        await handle_feedback_logic(message)
        return


async def handle_auth_code_logic(code_message: Message) -> None:
    """Логика обработки кода авторизации"""
    code = code_message.text.strip()
    if not code:
        await code_message.answer("❌ Пожалуйста, отправьте корректный код авторизации")
        return

    # Отправляем сообщение о начале обработки
    processing_msg = await code_message.answer("🔄 Обрабатываю код авторизации...")

    try:
        # Обрабатываем полученный код авторизации
        success, message_text = await calendar_client.process_auth_code(
            code_message.from_user.id,
            code,
            {
                "id": code_message.from_user.id,
                "username": code_message.from_user.username,
                "full_name": code_message.from_user.full_name,
                "is_bot": code_message.from_user.is_bot,
                "language_code": code_message.from_user.language_code,
            },
        )

        await processing_msg.edit_text(message_text)

        if not success:
            await code_message.answer(
                "Попробуйте еще раз или используйте /manualtoken для ручного ввода токена"
            )

    except Exception as e:
        await processing_msg.edit_text(
            "❌ Произошла ошибка при обработке кода.\n"
            "Попробуйте еще раз или используйте /manualtoken"
        )


async def handle_feedback_logic(feedback_msg: Message) -> None:
    """Логика обработки обратной связи"""
    # Обрабатываем обратную связь
    db.feedback.set_content_feedback(
        feedback_msg.from_user.id,
        feedback_msg.reply_to_message.message_id,
        feedback_msg.text,
    )

    logger.info(
        f"Получен отзыв от пользователя {feedback_msg.from_user.id}: {feedback_msg.text}"
    )

    await feedback_msg.answer(
        "✅ Спасибо за ваш отзыв! Мы обязательно его рассмотрим.\n"
        "Если у вас возникнут дополнительные вопросы, "
        "вы всегда можете связаться с разработчиком: @ImTaske\n\n"
        "Пожалуйста, оцените работу бота:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=FeedbackCallbackFactory(
                feedback_msg.reply_to_message.message_id
            ).get_feedback_buttons()
        ),
    )


@dp.message(Command("statistics"))
async def statistics_command(message: Message) -> None:
    # Создаем инлайн клавиатуру
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=StatisticsCallbackFactory().get_buttons()
    )

    await message.answer(
        "📊 Выберите период для просмотра статистики:", reply_markup=keyboard
    )


@dp.callback_query(lambda c: json.loads(c.data).get("t") == "statistics")
async def process_statistics_callback(callback_query: CallbackQuery) -> None:
    """Обрабатывает нажатие кнопок статистики
    t - тип callback
    d - период
    """
    data = json.loads(callback_query.data)
    period = data.get("d")
    logger.info(f"Получен период: {period}")
    user_id = callback_query.from_user.id

    await callback_query.answer()
    statistics = bot_service.get_statistics(user_id, period)
    await callback_query.message.edit_text(f"📊 Статистика за {period}:\n{statistics}")


@dp.message(Command("check"))
async def check_command(message: Message) -> None:
    if not db.tokens.get_token(message.from_user.id):
        await message.answer(
            "Вы не авторизованы в Google Calendar.\nИспользуйте команду /auth для авторизации."
        )
        return
    message_check = await message.answer(
        "🔍 Проверяю на наличие новых встреч...\nПожалуйста, подождите."
    )
    (
        success,
        error_message,
        meetings_by_day,
        active_events,
        deleted_events,
        updated_events,
    ) = await bot_service.get_check_meetings(message.from_user.id)

    event_ids = tuple(event["id"] for event in active_events)
    logger.info(f"event_ids: {event_ids}")
    if deleted_events:
        await bot_service.send_deleted_events(message.from_user.id, deleted_events)
        await message_check.edit_text("Обнаружены удаленные встречи.")
        return
    if updated_events:
        await bot_service.send_updated_events(message.from_user.id, updated_events)
        await message_check.edit_text("Обнаружены обновленные встречи.")
        return
    if db.notifications.check_all_notifications_sent(event_ids, message.from_user.id):
        await message_check.edit_text("Новых встреч не обнаружено.")
        return
    for i in range(len(active_events)):
        status = db.events.save_event(message.from_user.id, active_events[i])
    await bot_service.send_meetings_check_by_day(message.from_user.id, meetings_by_day)
    if not success:
        await message.answer(error_message)
        return


# Команда /manualtoken для ручного создания токена
@dp.message(Command("manualtoken"))
async def manual_token_command(message: Message) -> None:
    await message.answer(
        "Для ручного создания токена авторизации, пожалуйста, отправьте JSON-данные токена в формате:\n\n"
        '/settoken {"token": "ваш_токен", "refresh_token": "ваш_рефреш_токен", ...}\n\n'
        "Эти данные можно получить, выполнив авторизацию на другом устройстве или через API Console."
    )


# Команда /settoken для установки токена вручную
@dp.message(Command("settoken"))
async def set_token_command(message: Message) -> None:
    if not message.from_user:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    user_id = message.from_user.id

    # Извлекаем JSON из сообщения
    if message.text is not None:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "Пожалуйста, укажите JSON-данные токена после команды /settoken"
            )
            return

        token_json = parts[1].strip()
    else:
        # Обработка случая, когда строка равна None
        await message.answer(
            "Пожалуйста, укажите JSON-данные токена после команды /settoken"
        )
        return

    # Валидируем токен
    is_valid, message_text, token_data = bot_service.validate_token_json(token_json)
    await message.answer(message_text)


# Команда /week для просмотра встреч на неделю
@dp.message(Command("week"))
async def check_week_meetings(message: Message) -> None:
    if not message.from_user:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    user_id = message.from_user.id
    await message.answer("Проверяю ваши онлайн-встречи на неделю...")

    (
        success,
        error_message,
        meetings_by_day,
        active_events,
        deleted_events,
        updated_events,
    ) = await bot_service.get_week_meetings(user_id)

    if not success:
        await message.answer(error_message)
        return

    if not meetings_by_day:
        await message.answer("У вас нет предстоящих онлайн-встреч на неделю.")
        return

    await bot_service.send_meetings_week_by_day(message.from_user.id, meetings_by_day)


# Команда /reset для сброса кэша обработанных встреч
@dp.message(Command("reset"))
async def reset_processed_events(message: Message) -> None:
    try:
        # Сбрасываем все данные в базе
        await message.answer(
            "Все данные успешно сброшены. Теперь вы получите уведомления о всех текущих встречах как о новых."
        )
        db.notifications.reset_notifications(message.from_user.id)
        db.events.reset_processed_events(message.from_user.id)
    except Exception as e:
        logging.error(f"MOCK:Ошибка при сбросе данных: {e}")
        await message.answer("❌ MOCK: Произошла ошибка при сбросе данных.")


@dp.message(Command("feedback"))
async def feedback_command(message: Message) -> None:
    feedback_message = await message.answer(
        "📝 Пожалуйста, напишите ваш отзыв или предложение в ответ на это сообщение.\n"
        "Ваше мнение очень важно для нас и поможет сделать бота лучше!",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="Введите ваш отзыв или предложение здесь",
        ),
    )
    db.feedback.create_feedback_message_id(
        message.from_user.id, feedback_message.message_id
    )


@dp.callback_query(lambda c: json.loads(c.data).get("t") == "f")
async def process_rating_callback(callback_query: CallbackQuery) -> None:
    """Обрабатывает нажатие кнопок рейтинга
    t - тип callback
    d - рейтинг
    m - id сообщения
    """
    data = json.loads(callback_query.data)
    rating = data.get("d")
    logger.info(f"Получен рейтинг: {rating}")
    user_id = callback_query.from_user.id
    message_id = data.get("m")
    await callback_query.answer()
    db.feedback.set_rating(user_id, rating, message_id)
    await callback_query.message.edit_text(
        f"📊 Спасибо за ваш рейтинг! Мы обязательно его рассмотрим.\n"
    )


@dp.message(Command("info"))
async def info_command(message: Message) -> None:
    await message.answer(
        "📋 Список доступных команд:\n\n"
        "/start - Начало работы с ботом и получение основной информации\n"
        "/auth - Авторизация через браузер с кодом авторизации (рекомендуется)\n"
        "/manualtoken - Инструкция по ручному вводу токена\n"
        "/settoken - Установка токена вручную\n"
        "/check - Проверка наличия новых встреч\n"
        "/week - Просмотр встреч на текущую неделю\n"
        "/statistics - Просмотр статистики использования\n"
        "/reset - Сброс кэша обработанных встреч\n"
        "/feedback - Отправка отзыва или предложения\n"
        "/info - Показать этот список команд\n\n"
        "По всем вопросам обращайтесь к разработчику @ImTaske"
    )


# Запуск бота
async def main() -> None:
    # Регистрируем обработчики сигналов
    for signal_type in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(
            signal_type, lambda s=signal_type: asyncio.create_task(on_shutdown(s))
        )

    # asyncio.create_task(schedule_meetings_check())

    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Проверяем, не запущен ли уже бот
    try:
        # Создаем файл блокировки
        lock_file = BASE_DIR / ".bot.lock"

        if lock_file.exists():
            # Проверяем, активен ли процесс
            with open(lock_file, "r") as f:
                pid = int(f.read().strip())

            try:
                # Проверяем, существует ли процесс с таким PID
                os.kill(pid, 0)
                logging.error(f"Бот уже запущен (PID: {pid}). Завершаю работу.")
                sys.exit(1)
            except OSError:
                # Процесс не существует, можно продолжить
                logging.warning(f"Найден устаревший файл блокировки. Перезаписываю.")

        # Записываем текущий PID в файл блокировки
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))

        # Запускаем бота
        asyncio.run(main())
    finally:
        # Удаляем файл блокировки при завершении
        if lock_file.exists():
            lock_file.unlink()
