import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional

from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram import Bot

from google_calendar_client import GoogleCalendarClient
from queries import DatabaseQueries

# Добавляем инициализацию логгера
logger = logging.getLogger(__name__)

class BotService:
    def __init__(
        self, db: DatabaseQueries, calendar_client: GoogleCalendarClient, bot: Bot
    ):
        self.db = db
        self.bot = bot
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

    def get_statistics(self, user_id: int, period: str) -> str:
        """Получает статистику по встречам"""
        if not period:
            return "Ошибка: не указан период"
        
        events = self.db.events.get_statistics(user_id, period)
        # Считаем общее количество событий
        total_events = len(events)

        # Считаем общее время в минутах
        total_minutes = sum(
            (event.end_time - event.start_time).total_seconds() / 60
            for event in events
        )

        now = datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())
        period_text = {
            "week": f"неделю {now.strftime('%d.%m')} - {datetime.now(timezone.utc).strftime('%d.%m')}",
            "month": f"{now.strftime('%B').replace('March', 'Март').replace('April', 'Апрель').replace('May', 'Май').replace('June', 'Июнь').replace('July', 'Июль').replace('August', 'Август').replace('September', 'Сентябрь').replace('October', 'Октябрь').replace('November', 'Ноябрь').replace('December', 'Декабрь').replace('January', 'Январь').replace('February', 'Февраль')} {now.strftime('%Y')} года",
            "year": f"{now.strftime('%Y')} год"
        }.get(period, f"{period}")

        statistics = f"За {period_text}:\n" \
                    f"Количество встреч: {total_events}\n" \
                    f"Общее время: {int(total_minutes // 60)} ч {int(total_minutes % 60)} мин"
        return statistics
    
    async def send_deleted_events(
        self, user_id: int, deleted_events: List[Dict[str, Any]]
    ) -> None:
        """Отправляет сообщение о удаленных событиях"""
        # Группируем события по датам
        events_by_date = {}
        for event in deleted_events:
            start_dt = event['start']
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

        await self.bot.send_message(user_id, message)

    async def send_updated_events(
        self, user_id: int, updated_events: List[Dict[str, Any]]
    ) -> None:
        """Отправляет сообщение о обновленных событиях"""
        logger.info(f"Обновленные события: {updated_events}")
        # Группируем события по датам
        events_by_date = {}
        for event in updated_events:
            start_dt = event['start']
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
                old_start = self.safe_parse_datetime(event['old_start']) if isinstance(event['old_start'], str) else event['old_start']
                old_end = self.safe_parse_datetime(event['old_end']) if isinstance(event['old_end'], str) else event['old_end']
                
                message += f"🕒 Время: {old_start.strftime('%H:%M')} - {old_end.strftime('%H:%M')}\n"
                message += "Стало:\n" 
                message += f"📝 Название: {event['summary']}\n"
                message += f"🕒 Время: {event['start'].strftime('%H:%M')} - {event['end'].strftime('%H:%M')}\n"
                message += f"🔗 Ссылка на встречу: {event['old_meet_link']}\n"

        await self.bot.send_message(user_id, message)
    
    async def get_week_meetings(
        self, user_id: int
    ) -> Tuple[bool, str, Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Получает встречи на неделю и группирует их по дням"""
        try:
            # Проверяем наличие токена в базе данных
            if not self.db.tokens.get_token(user_id):
                return (
                    False,
                    "Вы не авторизованы в Google Calendar.\nИспользуйте команду /auth для авторизации.",
                    {},
                    [],
                    [],
                    [],
                )

            # Получаем текущее время в UTC для фильтрации только будущих встреч
            now = datetime.now(timezone.utc)
            
            # Определяем день недели (0 = понедельник, 6 = воскресенье)
            weekday = now.weekday()
            
            # Рассчитываем время окончания в зависимости от дня недели
            if weekday < 5:  # Будни (пн-пт)
                # Находим ближайшую пятницу
                days_until_friday = 4 - weekday  # 4 = пятница
                time_max = now + timedelta(days=days_until_friday)
            else:  # Выходные (сб-вс)
                # Находим пятницу следующей недели
                days_until_next_friday = 5 + (7 - weekday)  # 5 дней до пятницы + дни до конца недели
                time_max = now + timedelta(days=days_until_next_friday)
            
            # Запрашиваем события начиная с текущего момента до рассчитанной даты
            events = await self.calendar_client.get_upcoming_events(
                user_id=user_id,
                time_min=now,
                time_max=time_max,
                limit=50,
            )

            # Фильтруем события
            active_events = []
            for event in events:
                # Пропускаем события без ссылки на подключение
                if "hangoutLink" not in event:
                    continue
                logger.info(f"event: {event.get('start')}")
                logger.info(f"event: {event.get('end')}")
                end_time = event["end"].get("dateTime", event["end"].get("date"))
                end_dt = self.safe_parse_datetime(end_time)
                if end_dt > now:
                    active_events.append(event)

            if not active_events:
                return True, "У вас нет предстоящих онлайн-встреч на неделю.", {}, [], [], []
            deleted_events = self.db.events.check_deleted_events(user_id, active_events, now, time_max)
            updated_events = self.db.events.check_updated_event(user_id, active_events)
            print(f"updated_events: {updated_events}")
            # Группируем встречи по дням
            meetings_by_day: Dict[str, List[Dict[str, Any]]] = {}
            for event in active_events:
                start_time = event["start"].get("dateTime", event["start"].get("date"))
                start_dt = self.safe_parse_datetime(start_time)
                day_key = start_dt.strftime("%d.%m.%Y")

                if day_key not in meetings_by_day:
                    meetings_by_day[day_key] = []

                meetings_by_day[day_key].append(event)

            return True, "", meetings_by_day, active_events, deleted_events, updated_events

        except Exception as e:
            logging.error(f"Ошибка при получении встреч на неделю: {e}")
            return False, "Произошла ошибка при получении данных о встречах.", {}, [], [], []

    @staticmethod
    def safe_parse_datetime(date_str: str) -> datetime:
        """Безопасно парсит строку даты в объект datetime"""
        try:
            if date_str.endswith("Z"):
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            elif "+" in date_str or "-" in date_str and "T" in date_str:
                # Преобразуем к UTC
                dt = datetime.fromisoformat(date_str)
                return dt.astimezone(timezone.utc)
            else:
                # Если дата без часового пояса, добавляем UTC
                return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        except Exception as e:
            logging.error(f"Ошибка при парсинге даты {date_str}: {e}")
            return datetime.now(timezone.utc)

    async def send_meetings_check_by_day(
        self,
        user_id: int,
        meetings_by_day: dict,
    ) -> None:
        logging.info(f"Обрабатываем встречи: {meetings_by_day}")
        for day, day_events in sorted(meetings_by_day.items()):
            day_message = "Обнаружены новые онлайн-встречи:\n"
            logging.info(f"Обрабатываем день: {day}")
            day_message += f"📆 {hbold(f'Онлайн-встречи на {day}:')}\n"

            has_new_events = False
            for event in day_events:
                notification = self.db.notifications.get_notification(
                    event["id"], user_id  # type: ignore
                )
                if notification:
                    logging.info(
                        f"Уведомление для события {event['id']} уже существует"
                    )
                    continue

                has_new_events = True
                start_time = event["start"].get("dateTime", event["start"].get("date"))
                start_dt = self.safe_parse_datetime(start_time)
                end_time = event["end"].get("dateTime", event["end"].get("date"))
                end_dt = self.safe_parse_datetime(end_time)
                day_message += (
                    f"📝 {hbold('Название:')} {event['summary']}\n"
                    f"🕒 {hbold('Время:')} {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}\n"
                    f"🔗 {hbold('Ссылка:')} {event['hangoutLink']}\n\n"
                )
                self.db.notifications.create_notification(
                    event["id"], user_id  # type: ignore
                )

            if has_new_events:
                await self.bot.send_message(user_id, day_message, parse_mode="HTML")

    async def send_meetings_week_by_day(
        self,
        user_id: int,
        meetings_by_day: dict,
    ) -> None:
        """Отправляет сообщения со встречами, сгруппированными по дням"""
        for day, day_events in sorted(meetings_by_day.items()):
            day_message = f"📆 {hbold(f'Онлайн-встречи на {day}:')}\n"

            for event in day_events:
                start_time = event["start"].get("dateTime", event["start"].get("date"))
                start_dt = self.safe_parse_datetime(start_time)
                end_time = event["end"].get("dateTime", event["end"].get("date"))
                end_dt = self.safe_parse_datetime(end_time)
                day_message += (
                    f"📝 {hbold('Название:')} {event['summary']}\n"
                    f"🕒 {hbold('Время:')} {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}\n"
                    f"🔗 {hbold('Ссылка:')} {event['hangoutLink']}\n\n"
                )
                self.db.events.save_event(user_id, event)
                self.db.notifications.create_notification(
                    event["id"], user_id  # type: ignore
                )

            # Отправляем сообщение если есть встречи
            await self.bot.send_message(user_id, day_message, parse_mode="HTML")
