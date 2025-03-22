import os
import asyncio
import logging
import signal
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ForceReply
from aiogram.utils.markdown import hbold
from dotenv import load_dotenv

from google_calendar_client import GoogleCalendarClient
from queries import DatabaseQueries
from services import BotService

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
BASE_DIR = Path(__file__).resolve().parent.parent

# Инициализация бота и диспетчера
db = DatabaseQueries(str(BASE_DIR / "db.sqlite"))
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
                success, error_message, meetings_by_day, active_events = (
                    await bot_service.get_week_meetings(user)  # type: ignore
                )
                event_ids = tuple(event["id"] for event in active_events)
                if db.notifications.check_all_notifications_sent(event_ids, user):  # type: ignore
                    continue
                for i in range(len(active_events)):
                    status = db.events.save_event(user, active_events[i])  # type: ignore
                await bot_service.send_meetings_check_by_day(user, meetings_by_day)
                if not success:
                    await bot.send_message(user, error_message)
        except Exception as e:
            logging.error(f"Ошибка при отправке спам-сообщения: {e}")
        await asyncio.sleep(int(os.getenv("CHECK_INTERVAL", 300)))


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

    user_id = message.from_user.id

    await message.answer(
        f"Привет, {message.from_user.full_name if message.from_user.full_name else 'пользователь'}!\n"
        "Я буду отправлять уведомления о предстоящих созвонах в Google Meet.\n\n"
        "Для начала работы вам нужно авторизоваться в Google Calendar.\n"
        "Выберите подходящий способ авторизации:\n\n"
        "1. Через браузер с кодом авторизации: /auth\n"
        "2. Ручной ввод токена (для продвинутых пользователей): /manualtoken"
    )

    logging.info(
        f"Команда /start от пользователя ID: {user_id}, имя: {message.from_user.full_name if message.from_user.full_name else 'Неизвестно'}"
    )


# Команда /auth для авторизации на сервере
@dp.message(Command("auth"))
async def server_auth_command(message: Message) -> None:
    if not message.from_user:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    # Создаем URL для авторизации с правильными параметрами
    db.tokens.delete_token_by_user_id(message.from_user.id)
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
        "- Или используйте команду /manualtoken",
        parse_mode="HTML",
        reply_markup=ForceReply(
            selective=True, input_field_placeholder="Вставьте код авторизации"
        ),
    )
    db.tokens.set_auth_message_id(message.from_user.id, str(auth_message.message_id))

    # Добавляем обработчик для получения кода авторизации
    @dp.message()
    async def handle_auth_code(code_message: Message) -> None:
        auth_message_id = db.tokens.get_auth_message_id(code_message.from_user.id)  # type: ignore

        if (
            not code_message.reply_to_message
            or code_message.reply_to_message.message_id
            != int(auth_message_id)  # type: ignore
            or not code_message.from_user
            or code_message.from_user.id != code_message.from_user.id
        ):
            logging.info("Условия не совпадают, пропускаем обработку")
            return

        code = code_message.text.strip()  # type: ignore
        if not code:
            await code_message.answer(
                "❌ Пожалуйста, отправьте корректный код авторизации"
            )
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


@dp.message(Command("check"))
async def check_command(message: Message) -> None:
    message_check = await message.answer(
        "🔍 Проверяю на наличие новых встреч...\nПожалуйста, подождите."
    )
    success, error_message, meetings_by_day, active_events = (
        await bot_service.get_week_meetings(message.from_user.id)  # type: ignore
    )
    event_ids = tuple(event["id"] for event in active_events)
    if db.notifications.check_all_notifications_sent(event_ids, message.from_user.id):  # type: ignore
        await message_check.edit_text("Новых встреч не обнаружено.")
        return
    for i in range(len(active_events)):
        status = db.events.save_event(message.from_user.id, active_events[i])  # type: ignore
    await bot_service.send_meetings_check_by_day(message.from_user.id, meetings_by_day)  # type: ignore
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

    success, error_message, meetings_by_day, active_events = (
        await bot_service.get_week_meetings(user_id)
    )

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
            "✅ MOCK: Все данные успешно сброшены. Теперь вы получите уведомления о всех текущих встречах как о новых."
        )
    except Exception as e:
        logging.error(f"MOCK:Ошибка при сбросе данных: {e}")
        await message.answer("❌ MOCK: Произошла ошибка при сбросе данных.")


# Запуск бота
async def main() -> None:
    # Регистрируем обработчики сигналов
    for signal_type in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(
            signal_type, lambda s=signal_type: asyncio.create_task(on_shutdown(s))  # type: ignore
        )

    # Запускаем спам-сообщения
    asyncio.create_task(schedule_meetings_check())

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
