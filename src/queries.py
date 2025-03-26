import abc
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Any

from database import Database, User, Token, Event, Notification

logger = logging.getLogger(__name__)


class Queries(abc.ABC):
    def __init__(self, db: Database):
        self.db = db


class UserQueries(Queries):

    def add_user(self, user_data: dict) -> User | None:  # type: ignore
        """Добавляет нового пользователя в базу данных"""
        session = self.db.get_session()
        try:
            # Проверяем существует ли пользователь
            existing_user = (
                session.query(User).filter(User.id == user_data["id"]).first()
            )
            if existing_user:
                # Обновляем существующего пользователя
                existing_user.username = user_data["username"]
                existing_user.full_name = user_data["full_name"]
                existing_user.is_bot = user_data["is_bot"]
                existing_user.language_code = user_data["language_code"]
                session.commit()
                return session.merge(existing_user)  # type: ignore

            # Создаем нового пользователя
            user = User(
                id=user_data["id"],
                username=user_data["username"],
                full_name=user_data["full_name"],
                is_bot=user_data["is_bot"],
                language_code=user_data["language_code"],
            )
            session.add(user)
            session.commit()
            # Возвращаем объект, привязанный к сессии
            logger.info(f"Успешно добавлен пользователь: {user}")
            return session.merge(user)  # type: ignore
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при добавлении пользователя: {e}")
            return None
        finally:
            session.close()

    def get_user(self, user_id: int) -> Any:
        """Получает пользователя по ID"""
        session = self.db.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            logger.error(f"Успешно получен пользователь: {user}")
            return user
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя: {e}")
            return None
        finally:
            session.close()


class TokenQueries(Queries):

    def get_all_users(self) -> Any:
        """Получает всех пользователей"""
        session = self.db.get_session()
        try:
            users = session.query(User).all()
            list_users = [user.id for user in users]
            return list_users
        except Exception as e:
            logger.error(f"Ошибка при получении всех пользователей: {e}")
            return []
        finally:
            session.close()

    def save_token(self, user_id: int, token_data: dict) -> bool:  # type: ignore
        """Сохраняет токен для пользователя"""
        session = self.db.get_session()
        try:
            # Проверяем, существует ли уже токен для этого пользователя
            token = session.query(Token).filter(Token.user_id == user_id).first()

            if token:
                # Обновляем существующий токен
                token.token_data = json.dumps(token_data)
                token.updated_at = datetime.utcnow()
            else:
                # Создаем новый токен
                token = Token(user_id=user_id, token_data=json.dumps(token_data))
                session.add(token)

            session.commit()
            logger.info(f"Токен сохранен для пользователя: {user_id}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сохранении токена: {e}")
            return False
        finally:
            session.close()

    def get_token(self, user_id: int) -> Any:
        """Получает токен пользователя"""
        session = self.db.get_session()
        try:
            token = session.query(Token).filter(Token.user_id == user_id).first()
            if token:
                logger.info(f"Успешно получен токен: {token}")
                return json.loads(token.token_data)
            logger.info(f"Токен не найден для пользователя: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении токена: {e}")
            return None
        finally:
            session.close()

    def get_auth_state(self, user_id: int) -> tuple[dict | None, str | None]:  # type: ignore
        """Получение состояния авторизации"""
        session = self.db.get_session()
        try:
            token = session.query(Token).filter(Token.user_id == user_id).first()
            if token:
                logger.info(f"Успешно получен токен: {token}")
                return json.loads(token.token_data), token.redirect_url
            logger.info(f"Токен не найден для пользователя: {user_id}")
            return None, None
        except Exception as e:
            logger.error(f"Ошибка при получении состояния авторизации: {e}")
            return None, None
        finally:
            session.close()

    def delete_token_by_user_id(self, user_id: int) -> bool:
        """Удаляет токен для пользователя"""
        session = self.db.get_session()
        try:
            token = session.query(Token).filter(Token.user_id == user_id).first()
            session.delete(token)
            session.commit()
            logger.info(f"Токен удален для пользователя: {user_id}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при удалении токена: {e}")
            return False
        finally:
            session.close()

    def save_auth_state(
        self, user_id: int, flow_state: dict, redirect_uri: str  # type: ignore
    ) -> bool:
        """Сохранение состояния авторизации"""
        session = self.db.get_session()
        try:
            # Проверяем, существует ли уже токен для этого пользователя
            token = session.query(Token).filter(Token.user_id == user_id).first()

            if token:
                # Обновляем существующий токен с данными состояния авторизации
                token.token_data = json.dumps(flow_state)
                token.redirect_url = redirect_uri
                token.updated_at = datetime.utcnow()
            else:
                # Создаем новый токен с данными состояния авторизации
                token = Token(
                    user_id=user_id,
                    token_data=json.dumps(flow_state),
                    redirect_url=redirect_uri,
                )
                session.add(token)

            session.commit()
            logger.info(f"Состояние авторизации сохранено для пользователя: {user_id}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сохранении состояния авторизации: {e}")
            return False
        finally:
            session.close()

    def set_auth_message_id(self, user_id: int, auth_message_id: str) -> bool:
        """Устанавливает ID сообщения авторизации"""
        session = self.db.get_session()
        try:
            token = session.query(Token).filter(Token.user_id == user_id).first()
            token.auth_message_id = str(auth_message_id)
            session.commit()
            logger.info(
                f"ID сообщения авторизации установлен для пользователя: {user_id}"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при установке ID сообщения авторизации: {e}")
            return False

    def get_auth_message_id(self, user_id: int) -> int | None:
        """Получает ID сообщения авторизации"""
        session = self.db.get_session()
        try:
            token = session.query(Token).filter(Token.user_id == user_id).first()
            logger.info(f"Успешно получен токен: {token}")
            return token.auth_message_id if token else None
        except Exception as e:
            logger.error(f"Ошибка при получении ID сообщения авторизации: {e}")
            return None
        finally:
            session.close()


class EventQueries(Queries):
    
    def check_deleted_events(self, user_id: int, active_events: list[dict], time_min: datetime, time_max: datetime) -> None:
        """Проверяет, было ли удалено какое либо событие из календаря за указанный период"""
        session = self.db.get_session()
        deleted_events = []
        try:
            # Получаем все события из БД за указанный период
            all_events_db = session.query(Event).filter(
                Event.user_id == user_id,
                Event.start_time >= time_min,
                Event.start_time <= time_max
            ).all()
            current_time = datetime.now(timezone.utc)

            for event in all_events_db:
                # Пропускаем уже завершившиеся события
                # Добавляем часовой пояс к event.end_time, если его нет
                event_end_time = event.end_time
                if event_end_time.tzinfo is None:
                    event_end_time = event_end_time.replace(tzinfo=timezone.utc)
                
                # Всегда сравниваем в UTC
                if event_end_time <= current_time:
                    continue
                    
                # Проверяем было ли событие удалено из активных
                if event.event_id not in [event["id"] for event in active_events]:
                    deleted_events.append({
                        "id": event.event_id,
                        "summary": event.title,
                        "start": event.start_time,
                        "end": event.end_time
                    })
                    session.delete(event)
                    session.query(Notification).filter(Notification.event_id == event.event_id).delete()
            session.commit()
        except Exception as e:
            logger.error(f"Ошибка при проверке удаленных событий: {e}")
        return deleted_events
    
    def check_updated_event(self, user_id: int, active_events: list[dict]) -> list:
        """Получает обновленные события"""
        session = self.db.get_session()
        try:
            updated_events = []
            
            for event in active_events:
                logger.info(f"event: {event['summary']}")
                event_db = session.query(Event).filter_by(event_id=event["id"]).first()
                logger.info(f"event_db: {event_db.title}")
                if event_db:
                    # Получаем строки дат из события
                    start_time_str = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
                    end_time_str = event.get("end", {}).get("dateTime", event.get("end", {}).get("date"))
                    
                    # Преобразуем строки в datetime
                    start_time = self.safe_parse_datetime(start_time_str)
                    end_time = self.safe_parse_datetime(end_time_str)
                    
                    # Добавляем часовой пояс к event_db.start_time и event_db.end_time, если его нет
                    db_start_time = event_db.start_time
                    db_end_time = event_db.end_time
                    
                    if db_start_time.tzinfo is None:
                        db_start_time = db_start_time.replace(tzinfo=timezone.utc)
                    if db_end_time.tzinfo is None:
                        db_end_time = db_end_time.replace(tzinfo=timezone.utc)
                    
                    # Проверяем, изменились ли данные
                    if (event_db.title != event["summary"] or 
                        event_db.meet_link != event.get("hangoutLink", "") or
                        abs((db_start_time - start_time).total_seconds()) > 60 or
                        abs((db_end_time - end_time).total_seconds()) > 60):
                        
                        old_title = event_db.title
                        old_start = db_start_time
                        old_end = db_end_time
                        old_meet_link = event_db.meet_link
                        
                        # Обновляем данные события
                        event_db.title = event["summary"]
                        event_db.start_time = start_time
                        event_db.end_time = end_time
                        event_db.meet_link = event.get("hangoutLink", "")
                        event_db.all_data = event
                        
                        # Добавляем в список обновленных событий
                        updated_events.append({
                            "id": event_db.event_id,
                            "summary": event_db.title,
                            "old_summary": old_title,
                            "start": start_time,
                            "old_start": old_start,
                            "end": end_time,
                            "old_end": old_end,
                            "old_meet_link": old_meet_link
                        })
            
            session.commit()
            logger.info(f"Обновленные события: {updated_events}")
            return updated_events
        except Exception as e:
            logger.error(f"Ошибка при получении обновленных событий: {e}")
            session.rollback()
            return []
        finally:
            session.close()
    
    def safe_parse_datetime(self, date_str: str) -> datetime:
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
            logger.error(f"Ошибка при парсинге даты {date_str}: {e}")
            return datetime.now(timezone.utc)
            
    def save_event(self, user_id: int, event_data: dict) -> str:
        """Сохраняет событие в базу данных"""
        try:
            session = self.db.get_session()

            # Получаем необходимые данные из события
            event_id = event_data.get("id")
            title = event_data.get("summary", "Без названия")

            # Преобразуем строки дат в объекты datetime
            start_time_str = event_data["start"].get(
                "dateTime", event_data["start"].get("date")
            )
            end_time_str = event_data["end"].get(
                "dateTime", event_data["end"].get("date")
            )

            # Используем локальный метод для парсинга дат
            start_time = self.safe_parse_datetime(start_time_str)
            end_time = self.safe_parse_datetime(end_time_str)

            meet_link = event_data.get("hangoutLink", "")

            # Проверяем, существует ли уже такое событие
            existing_event = session.query(Event).filter_by(event_id=event_id).first()

            if existing_event:
                # Обновляем существующее событие
                existing_event.title = title
                existing_event.start_time = start_time
                existing_event.end_time = end_time
                existing_event.meet_link = meet_link
                existing_event.all_data = event_data
                logger.info(f"Событие {event_id} обновлено")
                return "updated"
            else:
                # Создаем новое событие
                new_event = Event(
                    event_id=event_id,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    meet_link=meet_link,
                    user_id=user_id,
                    all_data=event_data,
                )
                logger.info(f"Событие {event_id} создано")
                session.add(new_event)

            session.commit()
            return "created"
        except Exception as e:
            logging.error(f"Ошибка при сохранении события: {e}")
            if session:
                session.rollback()
            return "error"
        finally:
            if session:
                session.close()

    def get_user_events(
        self,
        user_id: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Any:
        """Получает события пользователя с возможностью фильтрации по времени"""
        session = self.db.get_session()
        try:
            query = session.query(Event).filter(Event.user_id == user_id)

            if start_time:
                query = query.filter(Event.end_time >= start_time)
            if end_time:
                query = query.filter(Event.start_time <= end_time)

            events = query.order_by(Event.start_time).all()
            logger.info(f"Успешно получены события: {events}")
            return events
        except Exception as e:
            logger.error(f"Ошибка при получении событий: {e}")
            return []
        finally:
            session.close()


class NotificationQueries(Queries):
    
    # Методы для работы с уведомлениями
    def create_notification(self, event_id: int, user_id: int) -> Notification | None:
        """Создает новое уведомление"""
        session = self.db.get_session()
        try:
            # Проверяем существует ли уже уведомление для этого события
            existing = (
                session.query(Notification)
                .filter(
                    Notification.event_id == event_id, Notification.user_id == user_id
                )
                .first()
            )

            if existing:
                logger.info(f"Уведомление для события {event_id} уже существует")
                return existing  # type: ignore

            notification = Notification(event_id=event_id, user_id=user_id)
            session.add(notification)
            session.commit()
            logger.info(f"Уведомление создано: {notification}")
            return notification
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при создании уведомления: {e}")
            return None
        finally:
            session.close()

    def get_notification(self, event_id: int, user_id: int) -> Any:
        """Получает уведомление по событию и пользователю"""
        session = self.db.get_session()
        try:
            notification = (
                session.query(Notification)
                .filter(
                    Notification.event_id == event_id, Notification.user_id == user_id
                )
                .first()
            )
            logger.info(f"Успешно получено уведомление: {notification}")
            if notification:
                return notification
            else:
                logger.info(f"Уведомление для события {event_id} не найдено")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении уведомления: {e}")
            return None

    def check_all_notifications_sent(self, event_ids: tuple[int], user_id: int) -> bool:
        """Проверяет, отправлены ли все уведомления для события"""
        session = self.db.get_session()
        try:
            # Получаем количество уведомлений для указанных событий
            notifications_count = (
                session.query(Notification)
                .filter(
                    Notification.event_id.in_(event_ids),
                    Notification.user_id == user_id,
                )
                .count()
            )

            # Проверяем что количество уведомлений равно количеству событий
            if notifications_count != len(event_ids):
                logger.info(
                    f"Найдено {notifications_count} уведомлений из {len(event_ids)} событий"
                )
                return False

            logger.info(f"Все уведомления найдены ({notifications_count} шт)")
            return True

        except Exception as e:
            logger.error(f"Ошибка при проверке уведомлений: {e}")
            return False
        finally:
            session.close()

    def get_pending_notifications(self) -> Any:
        """Получает все неотправленные уведомления"""
        session = self.db.get_session()
        try:
            notifications = (
                session.query(Notification).filter(Notification.is_sent == False).all()
            )
            logger.info(f"Успешно получены неотправленные уведомления: {notifications}")
            return notifications
        except Exception as e:
            logger.error(f"Ошибка при получении уведомлений: {e}")
            return []
        finally:
            session.close()


class DatabaseQueries:
    """Общий класс для доступа ко всем запросам к базе данных (ЖУЖУН)"""

    def __init__(self, path: str):
        self.db = Database(path)
        self.users = UserQueries(self.db)
        self.tokens = TokenQueries(self.db)
        self.events = EventQueries(self.db)
        self.notifications = NotificationQueries(self.db)
