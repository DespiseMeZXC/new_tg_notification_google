import os
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from requests_oauthlib import OAuth2Session

from queries import DatabaseQueries

logger = logging.getLogger(__name__)

# Области доступа для Google Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly", 
          "https://www.googleapis.com/auth/userinfo.email"]  # Добавляем scope для доступа к email


class GoogleCalendarClient:
    """Класс для работы с Google Calendar API"""

    def __init__(self, db: DatabaseQueries):
        self.db = db
        self.credentials_file = "credentials.json"

    async def get_credentials(self, user_id: int) -> Optional[Credentials]:
        """Получение и обновление учетных данных Google."""
        creds = None

        # Получаем токен из базы данных
        token_data = self.db.tokens.get_token(user_id)
        if token_data:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)

        # Если нет действительных учетных данных, возвращаем None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Сохраняем обновленные учетные данные
                self.db.tokens.save_token(user_id, json.loads(creds.to_json()))
            else:
                logger.info(f"Учетные данные не найдены для пользователя: {user_id}")
                return None

        logger.info(f"Учетные данные найдены для пользователя: {user_id}")
        return creds

    def create_auth_url(self, user_id: int) -> str:
        """Создает URL для авторизации и сохраняет состояние."""
        try:
            # Проверяем наличие файла credentials.json
            if not os.path.exists(self.credentials_file):
                logging.error(f"Файл {self.credentials_file} не найден")
                return f"Ошибка: файл {self.credentials_file} не найден"

            # Создаем flow
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file,
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
                "scopes": SCOPES,  # Сохраняем точный список scopes
                "auth_uri": flow.client_config["auth_uri"],
                "token_uri": flow.client_config["token_uri"],
            }
            self.db.users.add_user(user_id)
            state_auth = self.db.tokens.save_auth_state(user_id, flow_state, flow.redirect_uri, "auth")
            if not state_auth:
                return "❌ Вы исчерпали лимит на количество авторизаций(5)."
            logger.info(f"URL авторизации создан для пользователя: {user_id}")
            return auth_url
        except Exception as e:
            logging.error(f"Ошибка при создании URL авторизации: {e}")
            return f"Ошибка при создании URL авторизации: {str(e)}"

    async def process_auth_code(
        self, user_id: int, code: str, user_data: dict
    ) -> Tuple[bool, str]:
        """Обрабатывает код авторизации и сохраняет токен."""
        try:
            # Получаем сохраненное состояние
            flow_state, redirect_uri = self.db.tokens.get_auth_state(user_id)
            if not flow_state:
                logger.info(f"Сессия авторизации истекла для пользователя: {user_id}")
                return (
                    False,
                    "Сессия авторизации истекла. Пожалуйста, начните заново с команды /auth",
                )

            # Создаем новый flow с сохраненными scopes
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, SCOPES, redirect_uri=redirect_uri
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
            
            # Устанавливаем состояние из сохраненного flow_state
            flow.state = flow_state["state"]

            try:
                # Обмениваем код на токены, игнорируя изменения в scope
                flow.oauth2session.scope = None  # Игнорируем проверку scope
                flow.fetch_token(code=code)
                creds = flow.credentials
            except Exception as e:
                logger.error(f"Ошибка при обмене кода на токены: {e}")
                # Альтернативный способ получения токена
                try:
                    
                    redirect_response = f"urn:ietf:wg:oauth:2.0:oob?code={code}"
                    oauth2_session = OAuth2Session(
                        client_id=flow_state["client_id"],
                        redirect_uri=redirect_uri,
                        scope=SCOPES
                    )
                    
                    # Отключаем проверку scope
                    oauth2_session._client.verify_token = lambda token_data: None
                    
                    token = oauth2_session.fetch_token(
                        token_url=flow_state["token_uri"],
                        client_secret=flow_state["client_secret"],
                        authorization_response=redirect_response
                    )
                    
                    creds = Credentials(
                        token=token.get('access_token'),
                        refresh_token=token.get('refresh_token'),
                        token_uri=flow_state["token_uri"],
                        client_id=flow_state["client_id"],
                        client_secret=flow_state["client_secret"],
                        scopes=SCOPES
                    )
                except Exception as inner_e:
                    logger.error(f"Альтернативный способ получения токена также не удался: {inner_e}")
                    return False, f"❌ Ошибка при обработке кода авторизации: {str(e)}"
            
            try:
                # Получаем email пользователя
                service = build('oauth2', 'v2', credentials=creds)
                user_info = service.userinfo().get().execute()
                email = user_info.get('email')
            except Exception as e:
                logger.warning(f"Не удалось получить email пользователя: {e}")
                email = None

            # Сохраняем учетные данные и email
            token_data = json.loads(creds.to_json())
            if email:
                token_data['email'] = email
            
            success, message = self.db.tokens.save_token(user_id, token_data)
            if not success:
                return False, message
            logger.info(f"Учетные данные сохранены для пользователя: {user_id} с email: {email}")
            return (
                True,
                "✅ Авторизация успешно завершена! Теперь вы можете использовать команды бота.",
            )
        except Exception as e:
            logging.error(f"Ошибка при обработке кода авторизации: {e}")
            return False, f"❌ Ошибка при обработке кода авторизации: {str(e)}"

    async def get_upcoming_events(
        self,
        user_id: int,
        time_min: datetime,
        time_max: datetime,
        limit: int = 10,
        timezone_str: str = "UTC",
    ) -> List[Dict[str, Any]]:
        """Получение предстоящих событий из Google Calendar."""
        loop = asyncio.get_event_loop()

        # Получаем учетные данные
        creds = await self.get_credentials(user_id)

        # Если нет учетных данных, возвращаем пустой список
        if not creds:
            logger.info(f"Учетные данные не найдены для пользователя: {user_id}")
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

        logger.info(f"Запрашиваем события с {time_min_str} по {time_max_str}")

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
                    timeZone=timezone_str,
                )
                .execute(),
            )

            events = events_result.get("items", [])
            # Фильтруем только события с видеовстречами
            events = [event for event in events if "hangoutLink" in event]

            logger.info(f"Получено {len(events)} событий из календаря")
            return events
        except Exception as e:
            logger.error(f"Ошибка при получении событий: {e}")
            return []
