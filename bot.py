import os
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from dotenv import load_dotenv
from pathlib import Path
from google_calendar import (
    get_upcoming_events,
    create_auth_url,
    process_auth_code,
    get_credentials_with_local_server,
)
from queries import DatabaseQueries

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
BASE_DIR = Path(__file__).resolve().parent

# Инициализация бота и диспетчера
db = DatabaseQueries(str(BASE_DIR / "db.sqlite"))
bot = Bot(token=str(os.getenv("BOT_TOKEN")))
dp = Dispatcher()


# Команда /start
@dp.message(Command("start"))
async def command_start(message: Message) -> None:
    if message.from_user is None:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    user_id = message.from_user.id
    # Проверяем, существует ли пользователь в базе данных
    if not db.users.get_user(user_id):
        # Если нет, создаем нового пользователя
        full_name = (
            message.from_user.full_name
            if message.from_user.full_name
            else "Пользователь"
        )
        db.users.add_user(user_id, full_name)

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

    user_id = message.from_user.id

    # Создаем URL для авторизации с правильными параметрами
    auth_url = create_auth_url(user_id, db)

    await message.answer(
        "📱 <b>Инструкция по авторизации на сервере:</b>\n\n"
        "1️⃣ Перейдите по ссылке ниже в браузере:\n"
        f"{auth_url}\n\n"
        "2️⃣ Войдите в аккаунт Google и разрешите доступ к календарю\n\n"
        "3️⃣ Вы получите код авторизации. Скопируйте его\n\n"
        "4️⃣ Отправьте боту команду:\n"
        "/code ПОЛУЧЕННЫЙ_КОД\n\n"
        "❗ Если возникает ошибка при авторизации, попробуйте использовать команду /manualtoken",
        parse_mode="HTML",
    )


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

    try:
        # Проверяем, что это валидный JSON
        token_data = json.loads(token_json)

        # Проверяем наличие необходимых полей
        if "token" not in token_data or "refresh_token" not in token_data:
            await message.answer(
                "❌ JSON-данные токена должны содержать поля 'token' и 'refresh_token'"
            )
            return

        await message.answer(
            "✅ Токен успешно сохранен! Теперь вы можете использовать команды /week и /check."
        )
    except json.JSONDecodeError:
        await message.answer(
            "❌ Неверный формат JSON. Пожалуйста, проверьте данные и попробуйте снова."
        )
    except Exception as e:
        logging.error(f"Ошибка при установке токена вручную: {e}")
        await message.answer(f"❌ Произошла ошибка: {str(e)}")


# Команда /code для обработки кода авторизации
@dp.message(Command("code"))
async def process_auth_code_command(message: Message) -> None:
    if not message.from_user:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    user_id = message.from_user.id

    # Проверяем наличие кода
    if message.text is not None:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("❌ Пожалуйста, укажите код после команды /code")
            return

        # Получаем код
        code = message.text.split(maxsplit=1)[1].strip()
    else:
        # Обработка случая, когда строка равна None
        await message.answer("❌ Пожалуйста, укажите код после команды /code")
        return

    # Отправляем сообщение о начале обработки
    processing_msg = await message.answer("🔄 Обрабатываю код авторизации...")

    try:
        # Обрабатываем код авторизации
        success, result = await process_auth_code(user_id, code, db)

        # Обновляем сообщение с результатом
        await processing_msg.edit_text(result)
    except Exception as e:
        logging.error(f"Ошибка при обработке кода авторизации: {e}")
        await processing_msg.edit_text(f"❌ Произошла ошибка: {str(e)}")


# Команда /week для просмотра встреч на неделю
@dp.message(Command("week"))
async def check_week_meetings(message: Message) -> None:
    if not message.from_user:
        logging.error("Не удалось получить пользователя из сообщения")
        return

    user_id = message.from_user.id

    # Проверяем наличие токена в базе данных
    if not db.tokens.get_token(user_id):
        await message.answer(
            "Вы не авторизованы в Google Calendar.\n"
            "Используйте команду /serverauth для авторизации."
        )
        return

    await message.answer("Проверяю ваши онлайн-встречи на неделю...")

    try:
        # Получаем события на ближайшие 7 дней
        # Получаем текущее время в UTC для фильтрации только будущих встреч
        now = datetime.now(timezone.utc)

        # Запрашиваем события начиная с текущего момента
        events = await get_upcoming_events(
            time_min=now,
            time_max=now + timedelta(days=7),
            user_id=user_id,
            db=db,
            limit=20,
        )

        # Фильтруем события
        active_events = []
        for event in events:
            # Пропускаем события без ссылки на подключение
            if "hangoutLink" not in event:
                continue

            end_time = event["end"].get("dateTime", event["end"].get("date"))
            end_dt = safe_parse_datetime(end_time)
            if end_dt > now:
                active_events.append(event)

        if not active_events:
            await message.answer("У вас нет предстоящих онлайн-встреч на неделю.")
            return

        # Группируем встречи по дням
        meetings_by_day: dict[str, list[dict]] = {}  # type: ignore
        for event in active_events:
            start_time = event["start"].get("dateTime", event["start"].get("date"))
            start_dt = safe_parse_datetime(start_time)
            day_key = start_dt.strftime("%d.%m.%Y")

            if day_key not in meetings_by_day:
                meetings_by_day[day_key] = []

            meetings_by_day[day_key].append(event)

        # Отправляем встречи по дням
        for day, day_events in sorted(meetings_by_day.items()):
            day_message = f"📆 {hbold(f'Онлайн-встречи на {day}:')}\n\n"
            has_meetings = False

            for event in day_events:
                start_time = event["start"].get("dateTime", event["start"].get("date"))
                start_dt = safe_parse_datetime(start_time)

                day_message += (
                    f"🕒 {start_dt.strftime('%H:%M')} - {hbold(event['summary'])}\n"
                )
                day_message += f"🔗 {event['hangoutLink']}\n\n"
                has_meetings = True

            # Отправляем сообщение если есть встречи
            if has_meetings:
                await message.answer(day_message, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при получении встреч на неделю: {e}")
        await message.answer("Произошла ошибка при получении данных о встречах.")


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


# Функция для безопасного парсинга даты
def safe_parse_datetime(date_str: str) -> datetime:
    try:
        if date_str.endswith("Z"):
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        elif "+" in date_str or "-" in date_str and "T" in date_str:
            return datetime.fromisoformat(date_str)
        else:
            # Если дата без часового пояса, добавляем UTC
            return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except Exception as e:
        logging.error(f"Ошибка при парсинге даты {date_str}: {e}")
        return datetime.now(timezone.utc)


# Запуск бота
async def main() -> None:
    # Запускаем фоновую задачу для проверки встреч
    # asyncio.create_task(scheduled_meetings_check())

    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
