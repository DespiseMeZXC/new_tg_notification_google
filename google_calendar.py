import os
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
from google.auth.transport.requests import Request
from googleapiclient.discovery import build  # type: ignore
from dotenv import load_dotenv
from typing import Any

from queries import DatabaseQueries

# Загрузка переменных окружения
load_dotenv()

# Если изменить эти области, удалите файл token.json
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Директория для хранения токенов
TOKEN_DIR = os.getenv("TOKEN_DIR", ".")

# Убедимся, что директория существует
os.makedirs(TOKEN_DIR, exist_ok=True)


async def get_credentials(user_id: int, db: DatabaseQueries) -> Any:
    """Получение и обновление учетных данных Google."""
    creds = None

    if user_id:
        # Получаем токен из базы данных
        token_data = db.tokens.get_token(user_id)
        if token_data:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)  # type: ignore

    # Если нет действительных учетных данных, возвращаем None
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # type: ignore
            # Сохраняем обновленные учетные данные
            if user_id and db:
                db.tokens.save_token(user_id, json.loads(creds.to_json()))
        else:
            return None

    return creds


def create_auth_url(user_id: int, db: DatabaseQueries) -> Any:
    """Создает URL для авторизации и сохраняет состояние."""
    try:
        # Проверяем наличие файла credentials.json
        if not os.path.exists("credentials.json"):
            logging.error("Файл credentials.json не найден")
            return "Ошибка: файл credentials.json не найден"

        # Создаем flow
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json",
            SCOPES,
            redirect_uri="urn:ietf:wg:oauth:2.0:oob",  # Используем OOB для надежности
        )

        # Создаем URL авторизации
        auth_url, state = flow.authorization_url(
            access_type="offline", prompt="consent", include_granted_scopes="true"
        )

        # Сохраняем состояние авторизации в базу данных
        flow_state = {
            "client_id": flow.client_config["client_id"],
            "client_secret": flow.client_config["client_secret"],
            "state": state,
            "scopes": SCOPES,
            "auth_uri": flow.client_config["auth_uri"],
            "token_uri": flow.client_config["token_uri"],
        }

        db.tokens.save_auth_state(user_id, flow_state, flow.redirect_uri)

        return auth_url
    except Exception as e:
        logging.error(f"Ошибка при создании URL авторизации: {e}")
        return f"Ошибка при создании URL авторизации: {str(e)}"


async def process_auth_code(user_id: int, code: str, db: DatabaseQueries) -> Any:
    """Обрабатывает код авторизации и сохраняет токен."""
    try:
        # Получаем сохраненное состояние
        flow_state, redirect_uri = db.tokens.get_auth_state(user_id)
        if not flow_state:
            return (
                False,
                "Сессия авторизации истекла. Пожалуйста, начните заново с команды /serverauth",
            )

        # Создаем новый flow
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES, redirect_uri=redirect_uri
        )

        # Обновляем конфигурацию flow
        flow.client_config.update(
            {
                "client_id": flow_state["client_id"],
                "client_secret": flow_state["client_secret"],
                "auth_uri": flow_state["auth_uri"],
                "token_uri": flow_state["token_uri"],
            }
        )

        # Обмениваем код на токены
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Сохраняем учетные данные
        db.tokens.save_token(user_id, json.loads(creds.to_json()))

        return (
            True,
            "✅ Авторизация успешно завершена! Теперь вы можете использовать команды бота.",
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке кода авторизации: {e}")
        return False, f"❌ Ошибка при обработке кода авторизации: {str(e)}"


async def get_upcoming_events(
    time_min: datetime,
    time_max: datetime,
    user_id: int,
    db: DatabaseQueries,
    limit: int = 10,
) -> Any:
    """Получение предстоящих событий из Google Calendar."""
    loop = asyncio.get_event_loop()

    # Получаем учетные данные
    creds = await get_credentials(user_id, db)

    # Если нет учетных данных, возвращаем пустой список
    if not creds:
        return []

    # Создаем сервис
    service = await loop.run_in_executor(
        None, lambda: build("calendar", "v3", credentials=creds)
    )

    # Убедимся, что у datetime есть timezone и преобразуем в UTC
    if time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=timezone.utc)
    else:
        time_min = time_min.astimezone(timezone.utc)

    if time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=timezone.utc)
    else:
        time_max = time_max.astimezone(timezone.utc)

    # Удаляем микросекунды
    time_min = time_min.replace(microsecond=0)
    time_max = time_max.replace(microsecond=0)

    # Форматируем время в формат RFC3339
    time_min_str = time_min.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max_str = time_max.strftime("%Y-%m-%dT%H:%M:%SZ")

    logging.info(f"Запрашиваем события с {time_min_str} по {time_max_str}")

    try:
        # Вызываем API
        events_result = await loop.run_in_executor(
            None,
            lambda: service.events()
            .list(
                calendarId="primary",
                timeMin=time_min_str,
                timeMax=time_max_str,
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute(),
        )

        events = events_result.get("items", [])
        # Фильтруем только события с видеовстречами
        events = [event for event in events if "hangoutLink" in event]

        logging.info(f"Получено {len(events)} событий из календаря")
        return events
    except Exception as e:
        logging.error(f"Ошибка при получении событий: {e}")
        return []


async def get_credentials_with_local_server() -> Any:
    """Получение учетных данных с использованием локального сервера."""
    try:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        logging.info("Успешно получены учетные данные через локальный сервер")
        return creds
    except Exception as e:
        logging.error(
            f"Ошибка при получении учетных данных через локальный сервер: {e}"
        )
        return None
