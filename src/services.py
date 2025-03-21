import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional

from google_calendar_client import GoogleCalendarClient
from queries import DatabaseQueries


class BotService:
    def __init__(self, db: DatabaseQueries, calendar_client: GoogleCalendarClient):
        self.db = db
        self.calendar_client = calendar_client

    def validate_token_json(
        self, token_json: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Проверяет валидность JSON-данных токена"""
        try:
            token_data = json.loads(token_json)

            # Проверяем наличие необходимых полей
            if "token" not in token_data or "refresh_token" not in token_data:
                return (
                    False,
                    "❌ JSON-данные токена должны содержать поля 'token' и 'refresh_token'",
                    None,
                )

            return (
                True,
                "✅ Токен успешно сохранен! Теперь вы можете использовать команды /week и /check.",
                token_data,
            )
        except json.JSONDecodeError:
            return (
                False,
                "❌ Неверный формат JSON. Пожалуйста, проверьте данные и попробуйте снова.",
                None,
            )
        except Exception as e:
            logging.error(f"Ошибка при валидации токена: {e}")
            return False, f"❌ Произошла ошибка: {str(e)}", None

    async def get_week_meetings(
        self, user_id: int
    ) -> Tuple[bool, str, Dict[str, List[Dict[str, Any]]]]:
        """Получает встречи на неделю и группирует их по дням"""
        try:
            # Проверяем наличие токена в базе данных
            if not self.db.tokens.get_token(user_id):
                return (
                    False,
                    "Вы не авторизованы в Google Calendar.\nИспользуйте команду /auth для авторизации.",
                    {},
                )

            # Получаем текущее время в UTC для фильтрации только будущих встреч
            now = datetime.now(timezone.utc)

            # Запрашиваем события начиная с текущего момента
            events = await self.calendar_client.get_upcoming_events(
                user_id=user_id,
                time_min=now,
                time_max=now + timedelta(days=7),
                limit=20,
            )

            # Фильтруем события
            active_events = []
            for event in events:
                # Пропускаем события без ссылки на подключение
                if "hangoutLink" not in event:
                    continue

                end_time = event["end"].get("dateTime", event["end"].get("date"))
                end_dt = self.safe_parse_datetime(end_time)
                if end_dt > now:
                    active_events.append(event)

            if not active_events:
                return True, "У вас нет предстоящих онлайн-встреч на неделю.", {}

            # Группируем встречи по дням
            meetings_by_day: Dict[str, List[Dict[str, Any]]] = {}
            for event in active_events:
                start_time = event["start"].get("dateTime", event["start"].get("date"))
                start_dt = self.safe_parse_datetime(start_time)
                day_key = start_dt.strftime("%d.%m.%Y")

                if day_key not in meetings_by_day:
                    meetings_by_day[day_key] = []

                meetings_by_day[day_key].append(event)

            return True, "", meetings_by_day

        except Exception as e:
            logging.error(f"Ошибка при получении встреч на неделю: {e}")
            return False, "Произошла ошибка при получении данных о встречах.", {}

    @staticmethod
    def safe_parse_datetime(date_str: str) -> datetime:
        """Безопасно парсит строку даты в объект datetime"""
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
