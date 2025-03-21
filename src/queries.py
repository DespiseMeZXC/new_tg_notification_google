import abc
import logging
import json
from datetime import datetime
from typing import Any

from database import Database, User, Token, Event, Notification

logger = logging.getLogger(__name__)


class Queries(abc.ABC):
    def __init__(self, db: Database):
        self.db = db


class UserQueries(Queries):

    def add_user(self, user_data: dict) -> User | None:
        """Добавляет нового пользователя в базу данных"""
        session = self.db.get_session()
        try:
            # Проверяем существует ли пользователь
            existing_user = session.query(User).filter(User.id == user_data["id"]).first()
            if existing_user:
                # Обновляем существующего пользователя
                existing_user.username = user_data["username"]
                existing_user.full_name = user_data["full_name"] 
                existing_user.is_bot = user_data["is_bot"]
                existing_user.language_code = user_data["language_code"]
                session.commit()
                return session.merge(existing_user)
            
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
            return session.merge(user)
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
            return user
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя: {e}")
            return None
        finally:
            session.close()


class TokenQueries(Queries):
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
                return json.loads(token.token_data)
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
                return json.loads(token.token_data), token.redirect_url
            return None, None
        except Exception as e:
            logger.error(f"Ошибка при получении состояния авторизации: {e}")
            return None, None
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


class EventQueries(Queries):
    def save_event(self, user_id: int, event_data: dict) -> Any:  # type: ignore
        """Сохраняет событие календаря"""
        session = self.db.get_session()
        try:
            # Проверяем, существует ли уже событие с таким ID
            event = (
                session.query(Event)
                .filter(
                    Event.event_id == event_data["event_id"], Event.user_id == user_id
                )
                .first()
            )

            if event:
                # Обновляем существующее событие
                for key, value in event_data.items():
                    if hasattr(event, key):
                        setattr(event, key, value)
                event.updated_at = datetime.utcnow()
            else:
                # Создаем новое событие
                event = Event(user_id=user_id, **event_data)
                session.add(event)

            session.commit()
            logger.info(f"Событие сохранено: {event_data['event_id']}")
            return event
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сохранении события: {e}")
            return None
        finally:
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
            notification = Notification(event_id=event_id, user_id=user_id)
            session.add(notification)
            session.commit()
            return notification
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при создании уведомления: {e}")
            return None
        finally:
            session.close()

    def mark_notification_sent(self, notification_id: int) -> bool:
        """Отмечает уведомление как отправленное"""
        session = self.db.get_session()
        try:
            notification = session.query(Notification).get(notification_id)
            if notification:
                notification.is_sent = True
                notification.sent_at = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при обновлении уведомления: {e}")
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
            return notifications
        except Exception as e:
            logger.error(f"Ошибка при получении уведомлений: {e}")
            return []
        finally:
            session.close()


class DatabaseQueries:
    """Общий класс для доступа ко всем запросам к базе данных"""

    def __init__(self, path: str):
        self.db = Database(path)
        self.users = UserQueries(self.db)
        self.tokens = TokenQueries(self.db)
        self.events = EventQueries(self.db)
        self.notifications = NotificationQueries(self.db)
