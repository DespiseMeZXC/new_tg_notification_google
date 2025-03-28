import logging
import json
import pytz
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional, NamedTuple

from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram import Bot

from google_calendar_client import GoogleCalendarClient
from queries import DatabaseQueries
from utils import safe_parse_datetime

# Инициализация логгера
logger = logging.getLogger(__name__)


# Создаем типизированные структуры данных для возвращаемых значений
class TokenValidationResult(NamedTuple):
    is_valid: bool
    message: str
    token_data: Optional[Dict[str, Any]]


class WeekMeetingsResult(NamedTuple):
    success: bool
    message: str
    meetings_by_day: Dict[str, List[Dict[str, Any]]]
    active_events: List[Dict[str, Any]]
    deleted_events: List[Dict[str, Any]]
    updated_events: List[Dict[str, Any]]


class EventService:
    """Сервис для работы с событиями календаря"""

    def __init__(self, db: DatabaseQueries, calendar_client: GoogleCalendarClient):
        self.db = db
        self.calendar_client = calendar_client

    async def get_upcoming_events(
        self, user_id: int, time_min: datetime, time_max: datetime, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Получает предстоящие события из календаря"""
        events = await self.calendar_client.get_upcoming_events(
            user_id=user_id,
            time_min=time_min,
            time_max=time_max,
            limit=limit,
        )

        # Фильтруем только онлайн-встречи и нормализуем даты
        active_events = []
        for event in events:
            if "hangoutLink" not in event:
                continue

            start_dt = safe_parse_datetime(
                event["start"]["dateTime"], event["start"]["timeZone"]
            )
            end_dt = safe_parse_datetime(
                event["end"]["dateTime"], event["end"]["timeZone"]
            )

            event["start"]["dateTime"] = start_dt.isoformat()
            event["end"]["dateTime"] = end_dt.isoformat()

            if end_dt > time_min:
                active_events.append(event)

        return active_events

    def group_events_by_day(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Группирует события по дням"""
        meetings_by_day: Dict[str, List[Dict[str, Any]]] = {}

        for event in events:
            start_time = event["start"].get("dateTime", event["start"].get("date"))
            start_dt = safe_parse_datetime(start_time)
            day_key = start_dt.strftime("%d.%m.%Y")

            if day_key not in meetings_by_day:
                meetings_by_day[day_key] = []

            meetings_by_day[day_key].append(event)

        return meetings_by_day

    def save_events(self, user_id: int, events: List[Dict[str, Any]]) -> None:
        """Сохраняет события в базу данных"""
        for event in events:
            self.db.events.save_event(user_id, event)
            self.db.notifications.create_notification(event["id"], user_id)

    def check_deleted_events(
        self,
        user_id: int,
        active_events: List[Dict[str, Any]],
        time_min: datetime,
        time_max: datetime,
    ) -> List[Dict[str, Any]]:
        """Проверяет удаленные события"""
        return self.db.events.check_deleted_events(
            user_id, active_events, time_min, time_max
        )

    def check_updated_events(
        self, user_id: int, active_events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Проверяет обновленные события"""
        return self.db.events.check_updated_event(user_id, active_events)


class NotificationService:
    """Сервис для работы с уведомлениями"""

    def __init__(self, db: DatabaseQueries):
        self.db = db

    def has_notification(self, event_id: str, user_id: int) -> bool:
        """Проверяет наличие уведомления для события"""
        notification = self.db.notifications.get_notification(event_id, user_id)
        return notification is not None

    def create_notification(self, event_id: str, user_id: int) -> None:
        """Создает уведомление для события"""
        self.db.notifications.create_notification(event_id, user_id)


class TokenService:
    """Сервис для работы с токенами"""

    def __init__(self, db: DatabaseQueries):
        self.db = db

    def validate_token_json(self, token_json: str) -> TokenValidationResult:
        """Проверяет валидность JSON-данных токена"""
        try:
            token_data = json.loads(token_json)

            # Проверяем наличие необходимых полей
            if "token" not in token_data or "refresh_token" not in token_data:
                return TokenValidationResult(
                    is_valid=False,
                    message="❌ JSON-данные токена должны содержать поля 'token' и 'refresh_token'",
                    token_data=None,
                )

            return TokenValidationResult(
                is_valid=True,
                message="✅ Токен успешно сохранен! Теперь вы можете использовать команды /week и /check.",
                token_data=token_data,
            )
        except json.JSONDecodeError:
            return TokenValidationResult(
                is_valid=False,
                message="❌ Неверный формат JSON. Пожалуйста, проверьте данные и попробуйте снова.",
                token_data=None,
            )
        except Exception as e:
            logging.error(f"Ошибка при валидации токена: {e}")
            return TokenValidationResult(
                is_valid=False,
                message=f"❌ Произошла ошибка: {str(e)}",
                token_data=None,
            )

    def has_token(self, user_id: int) -> bool:
        """Проверяет наличие токена у пользователя"""
        return self.db.tokens.get_token(user_id) is not None


class StatisticsService:
    """Сервис для работы со статистикой"""

    def __init__(self, db: DatabaseQueries):
        self.db = db

    def get_statistics(self, user_id: int, period: str) -> str:
        """Получает статистику по встречам"""
        if not period:
            return "Ошибка: не указан период"

        events = self.db.events.get_statistics(user_id, period)

        # Считаем общее количество событий
        total_events = len(events)

        # Считаем общее время в минутах
        total_minutes = sum(
            (event.end_time - event.start_time).total_seconds() / 60 for event in events
        )

        now = datetime.now(timezone.utc) - timedelta(
            days=datetime.now(timezone.utc).weekday()
        )

        # Словарь для локализации названий месяцев
        month_names = {
            "January": "Январь",
            "February": "Февраль",
            "March": "Март",
            "April": "Апрель",
            "May": "Май",
            "June": "Июнь",
            "July": "Июль",
            "August": "Август",
            "September": "Сентябрь",
            "October": "Октябрь",
            "November": "Ноябрь",
            "December": "Декабрь",
        }

        # Получаем название месяца и локализуем его
        month_name = now.strftime("%B")
        localized_month = month_names.get(month_name, month_name)

        period_text = {
            "week": f"неделю {now.strftime('%d.%m')} - {datetime.now(timezone.utc).strftime('%d.%m')}",
            "month": f"{localized_month} {now.strftime('%Y')} года",
            "year": f"{now.strftime('%Y')} год",
        }.get(period, f"{period}")

        statistics = (
            f"За {period_text}:\n"
            f"Количество встреч: {total_events}\n"
            f"Общее время: {int(total_minutes // 60)} ч {int(total_minutes % 60)} мин"
        )

        return statistics


class MessageFormatter:
    """Класс для форматирования сообщений"""

    @staticmethod
    def format_events_by_day(
        day: str, events: List[Dict[str, Any]], is_new: bool = False
    ) -> str:
        """Форматирует список событий на день"""
        prefix = "Обнаружены новые онлайн-встречи:\n" if is_new else ""
        message = f"{prefix}📆 {hbold(f'Онлайн-встречи на {day}:')}\n"

        for event in events:
            start_time = event["start"].get("dateTime", event["start"].get("date"))
            start_dt = safe_parse_datetime(start_time, event["start"]["timeZone"])
            end_time = event["end"].get("dateTime", event["end"].get("date"))
            end_dt = safe_parse_datetime(end_time, event["end"]["timeZone"])

            message += (
                f"📝 {hbold('Название:')} {event['summary']}\n"
                f"🕒 {hbold('Время:')} {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}\n"
                f"🔗 {hbold('Ссылка:')} {event['hangoutLink']}\n\n"
            )

        return message

    @staticmethod
    def format_deleted_events(deleted_events: List[Dict[str, Any]]) -> str:
        """Форматирует список удаленных событий"""
        if not deleted_events:
            return ""

        # Группируем события по датам
        events_by_date = {}
        for event in deleted_events:
            start_dt = event["start"]
            day_key = start_dt.strftime("%d.%m.%Y")
            if day_key not in events_by_date:
                events_by_date[day_key] = []
            events_by_date[day_key].append(event)

        message = "Встречи были отменены:"

        # Формируем сообщение по датам
        for date in sorted(events_by_date.keys()):
            message += f"\n📅 Онлайн встречи на {date}:\n"
            for event in events_by_date[date]:
                message += (
                    f"🗑️ Название: {event['summary']}\n"
                    f"🕒 Время: {event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}\n"
                )

        return message

    @staticmethod
    def format_updated_events(updated_events: List[Dict[str, Any]]) -> str:
        """Форматирует список обновленных событий"""
        if not updated_events:
            return ""

        # Группируем события по датам
        events_by_date = {}
        for event in updated_events:
            start_dt = event["start"]
            day_key = start_dt.strftime("%d.%m.%Y")
            if day_key not in events_by_date:
                events_by_date[day_key] = []
            events_by_date[day_key].append(event)

        message = ""
        # Формируем сообщение по датам
        for date in sorted(events_by_date.keys()):
            message += f"\n🔄 Встречи обновлена на дату: {date}\n"
            for event in events_by_date[date]:
                message += "Было:\n"
                message += f"📝 Название: {event['old_summary']}\n"

                # Преобразуем строки в datetime
                old_start = (
                    safe_parse_datetime(event["old_start"])
                    if isinstance(event["old_start"], str)
                    else event["old_start"]
                )
                old_end = (
                    safe_parse_datetime(event["old_end"])
                    if isinstance(event["old_end"], str)
                    else event["old_end"]
                )

                message += f"🕒 Время: {old_start.strftime('%H:%M')} - {old_end.strftime('%H:%M')}\n"
                message += "Стало:\n"
                message += f"📝 Название: {event['summary']}\n"
                message += f"🕒 Время: {event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}\n"
                message += f"🔗 Ссылка на встречу: {event['old_meet_link']}\n"

        return message


class BotService:
    """Основной сервис бота, объединяющий все остальные сервисы"""

    def __init__(
        self, db: DatabaseQueries, calendar_client: GoogleCalendarClient, bot: Bot
    ):
        self.db = db
        self.bot = bot
        self.calendar_client = calendar_client

        # Инициализируем вспомогательные сервисы
        self.event_service = EventService(db, calendar_client)
        self.notification_service = NotificationService(db)
        self.token_service = TokenService(db)
        self.statistics_service = StatisticsService(db)
        self.message_formatter = MessageFormatter()

    def validate_token_json(self, token_json: str) -> TokenValidationResult:
        """Проверяет валидность JSON-данных токена"""
        return self.token_service.validate_token_json(token_json)

    def get_statistics(self, user_id: int, period: str) -> str:
        """Получает статистику по встречам"""
        return self.statistics_service.get_statistics(user_id, period)

    async def send_deleted_events(
        self, user_id: int, deleted_events: List[Dict[str, Any]]
    ) -> None:
        """Отправляет сообщение о удаленных событиях"""
        if not deleted_events:
            return

        message = self.message_formatter.format_deleted_events(deleted_events)
        if message:
            await self.bot.send_message(user_id, message)

    async def send_updated_events(
        self, user_id: int, updated_events: List[Dict[str, Any]]
    ) -> None:
        """Отправляет сообщение о обновленных событиях"""
        if not updated_events:
            return

        message = self.message_formatter.format_updated_events(updated_events)
        if message:
            await self.bot.send_message(user_id, message)

    async def get_week_meetings(self, user_id: int) -> WeekMeetingsResult:
        """Получает встречи на неделю и группирует их по дням"""
        try:
            # Проверяем наличие токена в базе данных
            if not self.token_service.has_token(user_id):
                return WeekMeetingsResult(
                    success=False,
                    message="Вы не авторизованы в Google Calendar.\nИспользуйте команду /auth для авторизации.",
                    meetings_by_day={},
                    active_events=[],
                    deleted_events=[],
                    updated_events=[],
                )

            # Получаем текущее время в UTC для фильтрации только будущих встреч
            now = datetime.now(timezone.utc)
            # Определяем день недели (0 = понедельник, 6 = воскресенье)
            weekday = now.weekday()

            # Рассчитываем время окончания в зависимости от дня недели
            if weekday < 5:  # Будни (пн-пт)
                # Находим ближайшую пятницу
                days_until_friday = 4 - weekday  # 4 = пятница
                time_max = (now + timedelta(days=days_until_friday)).replace(
                    hour=23, minute=59, second=59
                )
            else:  # Выходные (сб-вс)
                # Находим пятницу следующей недели
                days_until_next_friday = 5 + (
                    7 - weekday
                )  # 5 дней до пятницы + дни до конца недели
                time_max = (now + timedelta(days=days_until_next_friday)).replace(
                    hour=23, minute=59, second=59
                )

            # Запрашиваем события начиная с текущего момента до рассчитанной даты
            active_events = await self.event_service.get_upcoming_events(
                user_id=user_id,
                time_min=now,
                time_max=time_max,
                limit=50,
            )

            if not active_events:
                return WeekMeetingsResult(
                    success=True,
                    message="У вас нет предстоящих онлайн-встреч на неделю.",
                    meetings_by_day={},
                    active_events=[],
                    deleted_events=[],
                    updated_events=[],
                )

            # Проверяем удаленные и обновленные события только при команде /check
            # Для команды /week этот функционал нужно отключить
            deleted_events = []
            updated_events = []

            # Группируем встречи по дням
            meetings_by_day = self.event_service.group_events_by_day(active_events)
            logger.info(f"deleted_events: {len(deleted_events)}")
            logger.info(f"updated_events: {len(updated_events)}")
            return WeekMeetingsResult(
                success=True,
                message="",
                meetings_by_day=meetings_by_day,
                active_events=active_events,
                deleted_events=deleted_events,
                updated_events=updated_events,
            )

        except Exception as e:
            logging.error(f"Ошибка при получении встреч на неделю: {e}")
            return WeekMeetingsResult(
                success=False,
                message="Произошла ошибка при получении данных о встречах.",
                meetings_by_day={},
                active_events=[],
                deleted_events=[],
                updated_events=[],
            )

    async def get_check_meetings(self, user_id: int) -> WeekMeetingsResult:
        """Проверяет встречи на неделю, включая удаленные и обновленные"""
        result = await self.get_week_meetings(user_id)

        if not result.success:
            return result

        # Получаем текущее время в UTC
        now = datetime.now(timezone.utc)
        # Определяем день недели (0 = понедельник, 6 = воскресенье)
        weekday = now.weekday()

        # Рассчитываем время окончания
        if weekday < 5:  # Будни (пн-пт)
            days_until_friday = 4 - weekday
            time_max = (now + timedelta(days=days_until_friday)).replace(
                hour=23, minute=59, second=59
            )
        else:  # Выходные (сб-вс)
            days_until_next_friday = 5 + (7 - weekday)
            time_max = (now + timedelta(days=days_until_next_friday)).replace(
                hour=23, minute=59, second=59
            )

        # Проверяем удаленные и обновленные события
        deleted_events = self.event_service.check_deleted_events(
            user_id, result.active_events, now, time_max
        )
        updated_events = self.event_service.check_updated_events(
            user_id, result.active_events
        )
        logger.info(f"Deleted events: {len(deleted_events)}")
        logger.info(f"Updated events: {len(updated_events)}")
        return WeekMeetingsResult(
            success=result.success,
            message=result.message,
            meetings_by_day=result.meetings_by_day,
            active_events=result.active_events,
            deleted_events=deleted_events,
            updated_events=updated_events,
        )

    async def send_meetings_check_by_day(
        self,
        user_id: int,
        meetings_by_day: dict,
    ) -> None:
        """Отправляет сообщения о новых встречах, сгруппированных по дням"""
        for day, day_events in sorted(meetings_by_day.items()):
            new_events = []

            for event in day_events:
                # Проверяем, есть ли уже уведомление для этого события
                if not self.notification_service.has_notification(event["id"], user_id):
                    new_events.append(event)
                    # Создаем уведомление для нового события
                    self.notification_service.create_notification(event["id"], user_id)

            # Отправляем сообщение только если есть новые события
            if new_events:
                day_message = self.message_formatter.format_events_by_day(
                    day, new_events, is_new=True
                )
                await self.bot.send_message(user_id, day_message, parse_mode="HTML")

    async def send_meetings_week_by_day(
        self,
        user_id: int,
        meetings_by_day: dict,
    ) -> None:
        """Отправляет сообщения со всеми встречами, сгруппированными по дням"""
        for day, day_events in sorted(meetings_by_day.items()):
            # Сохраняем все события в базу данных
            self.event_service.save_events(user_id, day_events)

            # Форматируем и отправляем сообщение
            day_message = self.message_formatter.format_events_by_day(day, day_events)
            await self.bot.send_message(user_id, day_message, parse_mode="HTML")
