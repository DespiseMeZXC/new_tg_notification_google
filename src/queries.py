import abc
import logging
import json
import pytz
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Union
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import Database, User, Token, Event, Notification, Feedback, UserTokenLink
from utils import safe_parse_datetime

logger = logging.getLogger(__name__)


class Queries(abc.ABC):
    def __init__(self, db: Database):
        self.db = db


class FeedbackQueries(Queries):

    def set_rating(self, user_id: int, rating: int, message_id: int) -> None:
        """Устанавливает рейтинг"""
        session = self.db.get_session()
        try:
            feedback = (
                session.query(Feedback)
                .filter(Feedback.user_id == user_id, Feedback.message_id == message_id)
                .first()
            )
            feedback.rating = rating
            logger.info(f"Rating: {feedback.rating} от юзера: {user_id}")
            session.commit()
        except Exception as e:
            logger.error(f"Ошибка при установке рейтинга: {e}")
            session.rollback()
        finally:
            session.close()

    def get_feedback_message_id(self, user_id: int) -> int | None:
        """Получает ID сообщения обратной связи"""
        session = self.db.get_session()
        try:
            feedback = (
                session.query(Feedback)
                .filter(Feedback.user_id == user_id)
                .order_by(Feedback.created_at.desc())
                .first()
            )
            logger.info(f"Message ID: {feedback.message_id} для юзера: {user_id}")
            return feedback.message_id if feedback else None
        except Exception as e:
            logger.error(f"Ошибка при получении ID сообщения обратной связи: {e}")
            return None
        finally:
            session.close()

    def create_feedback_message_id(self, user_id: int, message_id: int) -> None:
        """Устанавливает ID сообщения обратной связи"""
        session = self.db.get_session()
        try:
            feedback = Feedback(user_id=user_id, message_id=message_id)
            session.add(feedback)
            session.commit()
            logger.info(f"ID сообщения {message_id} установлен для юзера: {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при создании обратной связи: {e}")
            session.rollback()
        finally:
            session.close()

    def set_content_feedback(self, user_id: int, message_id: int, content: str) -> None:
        """Сохраняет обратную связь"""
        session = self.db.get_session()
        try:
            feedback = (
                session.query(Feedback)
                .filter(Feedback.user_id == user_id, Feedback.message_id == message_id)
                .first()
            )
            logger.info(f"Обратная связь найденная: {feedback}")
            logger.info(f"Обратная связь: {content}")
            feedback.content = content
            session.commit()
            logger.info(f"Обратная связь установлена для юзера: {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при создании обратной связи: {e}")
            session.rollback()
        finally:
            session.close()


class UserQueries(Queries):

    def add_user(self, user_data: dict | int) -> User | None:
        """Добавляет нового пользователя в базу данных"""
        session = self.db.get_session()
        try:
            # Проверяем, является ли user_data целым числом (ID пользователя)
            if isinstance(user_data, int):
                # Проверяем существует ли пользователь
                existing_user = session.query(User).filter(User.id == user_data).first()
                if existing_user:
                    logger.info(f"Пользователь с ID {user_data} уже существует")
                    return existing_user
                else:
                    logger.error(f"Пользователь с ID {user_data} не найден и нет данных для создания")
                    return None
            
            # Проверяем существует ли пользователь
            existing_user = session.query(User).filter(User.id == user_data["id"]).first()
            if existing_user:
                # Обновляем существующего пользователя
                existing_user.username = user_data.get("username", existing_user.username)
                existing_user.full_name = user_data.get("full_name", existing_user.full_name)
                existing_user.is_bot = user_data.get("is_bot", existing_user.is_bot)
                existing_user.language_code = user_data.get("language_code", existing_user.language_code)
                session.commit()
                logger.info(f"Обновлен пользователь: {existing_user}")
                return session.merge(existing_user)

            # Создаем нового пользователя
            user = User.from_dict(user_data)
            session.add(user)
            session.commit()
            # Возвращаем объект, привязанный к сессии
            logger.info(f"Успешно добавлен пользователь: {user}")
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

    def save_token(self, user_id: int, token_data: dict) -> bool:
        """Сохраняет токен для пользователя"""
        session = self.db.get_session()
        try:
            # Проверяем, существует ли уже токен для этого пользователя
            logger.info(f"token_data: {token_data}")
            ready_token = session.query(Token).join(UserTokenLink).filter(UserTokenLink.user_id == user_id, Token.email == token_data.get('email'), Token.status == "ready").first()
            auth_token = session.query(Token).join(UserTokenLink).filter(UserTokenLink.user_id == user_id, Token.status == "auth").first()
            if ready_token:
                # Обновляем существующий токен
                session.delete(session.query(UserTokenLink).filter(UserTokenLink.user_id == user_id, UserTokenLink.token_id == auth_token.id).first())
                session.delete(auth_token)
                session.commit()
                return False, "❌ Данный email уже используется"
            else:
                if auth_token:
                    # Обновляем существующий токен
                    auth_token.token_data = json.dumps(token_data)
                    auth_token.email = token_data.get('email')
                    auth_token.status = "ready"
                    session.commit()
                    logger.info(f"Токен сохранен для пользователя: {user_id}")
                    return True, "Токен сохранен"
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сохранении токена: {e}")
            return False, f"Ошибка при сохранении токена: {e}"
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
    
    def get_all_tokens_by_user_id(self, user_id: int) -> Any:
        """Получает все токены для пользователя"""
        session = self.db.get_session()
        try:
            tokens = session.query(Token).join(UserTokenLink).filter(UserTokenLink.user_id == user_id).all()
            return tokens
        except Exception as e:
            logger.error(f"Ошибка при получении всех токенов для пользователя: {e}")
            return []
        finally:
            session.close()
            

    def get_auth_state(self, user_id: int) -> tuple[dict | None, str | None]:
        """Получение состояния авторизации"""
        session = self.db.get_session()
        try:
            token = session.query(Token).join(UserTokenLink).filter(
                UserTokenLink.user_id == user_id, 
                Token.status == "auth"
            ).first()
            
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

    def delete_token_by_email(self, user_id: int, email: str) -> bool:
        """Удаляет токен для пользователя"""
        session = self.db.get_session()
        try:
            token = session.query(Token).join(UserTokenLink).filter(Token.email == email, UserTokenLink.user_id == user_id).first()
            if token:
                session.delete(session.query(UserTokenLink).filter(UserTokenLink.token_id == token.id).first())
                session.delete(token)
                session.commit()
                logger.info(f"Токен удален для пользователя: {email} и {user_id}")
                return True
            else:
                logger.info(f"Токен не найден для пользователя: {email} и {user_id}")
                return False
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при удалении токена: {e}")
            return False
        finally:
            session.close()

    def save_auth_state(
        self, user_id: int, flow_state: dict, redirect_uri: str, status_auth: str
    ) -> bool:
        """Сохранение состояния авторизации"""
        session = self.db.get_session()
        try:
            # Проверяем, существует ли уже токен для этого пользователя
            tokens = session.query(UserTokenLink).filter(UserTokenLink.user_id == user_id).all()
            not_auth_tokens = session.query(Token).filter(Token.status == status_auth).all()
            logger.info(f"\nnot_auth_tokens: {not_auth_tokens}")
            for token in not_auth_tokens:
                # Находим связку для текущего токена
                token_link = session.query(UserTokenLink).filter(
                    UserTokenLink.token_id == token.id
                ).first()
                
                # Если связка существует, удаляем её
                if token_link:
                    session.delete(token_link)
                
                # Удаляем сам токен
                session.delete(token)
                session.commit()
            if len(tokens) >= 5:
                # Обновляем существующий токен с данными состояния авторизации
                return False
            else:
                # Создаем новый токен с данными состояния авторизации
                token = Token(
                    token_data=json.dumps(flow_state),
                    redirect_url=redirect_uri,
                    status=status_auth
                )
                session.add(token)
            filter_user_token_link = session.query(UserTokenLink).filter(UserTokenLink.user_id == user_id, UserTokenLink.token_id == token.id).first()
            if not filter_user_token_link:
                user_token_link = UserTokenLink(user_id=user_id, token_id=token.id)
                session.add(user_token_link)
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
            token = session.query(Token).join(UserTokenLink).filter(
                UserTokenLink.user_id == user_id, 
                Token.status == "auth"
            ).first()
            if token:
                token.auth_message_id = str(auth_message_id)
            else:
                logger.warning(f"Токен не найден для пользователя {user_id}")
                return False
            session.commit()
            logger.info(
                f"ID сообщения авторизации установлен для пользователя: {user_id}"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при установке ID сообщения авторизации: {e}")
            return False
        finally:
            session.close()

    def get_auth_message_id(self, user_id: int) -> int | None:
        """Получает ID сообщения авторизации"""
        session = self.db.get_session()
        try:
            token = session.query(Token).join(UserTokenLink).filter(UserTokenLink.user_id == user_id, Token.status == "auth").first()
            if not token:
                logger.info(f"Токены не найдены для пользователя: {user_id}")
                return None
            logger.info(f"Успешно получен токен: {token}")
            return token.auth_message_id
        except Exception as e:
            logger.error(f"Ошибка при получении ID сообщения авторизации: {e}")
            return None
        finally:
            session.close()


class EventQueries(Queries):
    

    def reset_processed_events(self, user_id: int) -> None:
        """Сбрасывает все данные в базе"""
        session = self.db.get_session()
        try:
            session.query(Event).filter(Event.user_id == user_id).delete()
            session.commit()
        except Exception as e:
            logger.error(f"Ошибка при сбросе данных: {e}")
        finally:
            session.close()

    def get_statistics(self, user_id: int, period: str) -> str:
        """Получает статистику по встречам"""
        session = self.db.get_session()
        try:
            # Получаем текущую дату
            now = datetime.now(timezone.utc)

            # Устанавливаем начало и конец периода в зависимости от выбранного периода
            if period == "week":
                # Получаем начало текущей недели (понедельник)
                start_date = now - timedelta(days=now.weekday())
                start_date = start_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                end_date = now
            elif period == "month":
                # Получаем первый день текущего месяца
                start_date = now.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                end_date = now
            else:  # year
                # Получаем первый день текущего года
                start_date = now.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                )
                end_date = now

            end_date = end_date.replace(hour=23, minute=59, second=59)

            # Получаем все события за выбранный период
            events = (
                session.query(Event)
                .filter(
                    Event.user_id == user_id,
                    Event.start_time >= start_date,
                    Event.start_time <= end_date,
                )
                .all()
            )
            return events
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return []
        finally:
            session.close()

    def check_deleted_events(
        self,
        user_id: int,
        active_events: list[dict],
        time_min: datetime,
        time_max: datetime,
    ) -> None:
        """Проверяет, было ли удалено какое либо событие из календаря за указанный период"""
        session = self.db.get_session()
        deleted_events = []
        try:
            # Получаем все события из БД за указанный период
            all_events_db = (
                session.query(Event)
                .filter(
                    Event.user_id == user_id,
                    Event.start_time >= time_min,
                    Event.start_time <= time_max,
                )
                .all()
            )
            time_zones = [event["start"]["timeZone"] for event in active_events]
            logger.info(f"time_zones: {time_zones}")
            current_time_now = datetime.now()
            current_time_timezone = current_time_now.astimezone(
                pytz.timezone(time_zones[0])
            )
            logger.info(f"current_time_now: {current_time_now}")
            logger.info(f"current_time_timezone: {current_time_timezone}")
            for event in all_events_db:
                # Пропускаем уже завершившиеся события
                # Добавляем часовой пояс к event.end_time, если его нет
                event_end_time = event.end_time
                logger.info(f"event_end_time before: {event_end_time}")
                if event_end_time.tzinfo is None:
                    event_end_time = event_end_time.replace(tzinfo=timezone.utc)
                logger.info(f"event_end_time after: {event_end_time}")
                # Всегда сравниваем в UTC
                if event_end_time <= current_time_timezone:
                    logger.info(f"Событие {event.event_id} завершено")
                    continue
                logger.info(f"event_end_time: {event_end_time} <= {current_time_timezone}")
                # Проверяем было ли событие удалено из активных
                if event.event_id not in [event["id"] for event in active_events]:
                    deleted_events.append(
                        {
                            "id": event.event_id,
                            "summary": event.title,
                            "start": event.start_time,
                            "end": event.end_time,
                        }
                    )
                    session.query(Notification).filter(
                        Notification.event_id == event.event_id
                    ).delete()
                    session.delete(event)
            session.commit()
            return deleted_events
        except Exception as e:
            logger.error(f"Ошибка при проверке удаленных событий: {e}")
            return []
        finally:
            session.close()

    def check_updated_event(self, user_id: int, active_events: list[dict]) -> list:
        """Получает обновленные события"""
        session = self.db.get_session()
        try:
            updated_events = []

            for event in active_events:
                event_db = session.query(Event).filter_by(event_id=event["id"]).first()

                # Проверяем, что event_db не None
                if not event_db:
                    logger.info(
                        f"Событие {event['id']} не найдено в базе данных, пропускаем"
                    )
                    continue
                logger.info(f"event: {event['summary']}")
                logger.info(f"event_db: {event_db.title}")

                # Получаем строки дат из события
                start_time = datetime.fromisoformat(
                    event.get("start", {}).get(
                        "dateTime", event.get("start", {}).get("date")
                    )
                )
                end_time = datetime.fromisoformat(
                    event.get("end", {}).get(
                        "dateTime", event.get("end", {}).get("date")
                    )
                )

                # Добавляем часовой пояс к event_db.start_time и event_db.end_time, если его нет
                db_start_time = safe_parse_datetime(
                    event_db.all_data.get("start", {}).get(
                        "dateTime", event_db.all_data.get("start", {}).get("date")
                    ),
                    event_db.all_data.get("start", {}).get("timeZone"),
                )
                db_end_time = safe_parse_datetime(
                    event_db.all_data.get("end", {}).get(
                        "dateTime", event_db.all_data.get("end", {}).get("date")
                    ),
                    event_db.all_data.get("end", {}).get("timeZone"),
                )
                logger.info(f"event_db: {event_db.title}")
                logger.info(f"db_start_time: {db_start_time}")
                logger.info(f"db_end_time: {db_end_time}")
                logger.info(f"start_time: {start_time}")
                logger.info(f"end_time: {end_time}")

                # Проверяем, изменились ли данные
                if (
                    event_db.title != event["summary"]
                    or event_db.meet_link != event.get("hangoutLink", "")
                    or abs((db_start_time - start_time).total_seconds()) > 60
                    or abs((db_end_time - end_time).total_seconds()) > 60
                ):

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
                    updated_events.append(
                        {
                            "id": event_db.event_id,
                            "summary": event_db.title,
                            "old_summary": old_title,
                            "start": start_time,
                            "old_start": old_start,
                            "end": end_time,
                            "old_end": old_end,
                            "old_meet_link": old_meet_link,
                        }
                    )

            session.commit()
            logger.info(f"Обновленные события: {len(updated_events)}")
            return updated_events
        except Exception as e:
            logger.error(f"Ошибка при получении обновленных событий: {e}")
            session.rollback()
            return []
        finally:
            session.close()

    def save_event(self, user_id: int, event_data: dict) -> bool:
        """Сохраняет событие в базу данных"""
        session = self.db.get_session()
        try:
            # Проверяем существует ли событие
            event_id = event_data.get("id")
            if not event_id:
                logger.error(f"Отсутствует ID события в данных: {event_data}")
                return False
            
            existing_event = session.query(Event).filter(Event.id == event_id).first()
            
            if existing_event:
                # Обновляем существующее событие
                existing_event.title = event_data.get("summary", "Без названия")
                existing_event.start_time = safe_parse_datetime(
                    event_data["start"].get("dateTime"), event_data["start"].get("timeZone")
                )
                existing_event.end_time = safe_parse_datetime(
                    event_data["end"].get("dateTime"), event_data["end"].get("timeZone")
                )
                existing_event.meet_link = event_data.get("hangoutLink")
                existing_event.all_data = event_data
                existing_event.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.info(f"Обновлено событие: {existing_event.title}")
                return True
            
            # Создаем новое событие
            event = Event(
                id=event_id,  # Устанавливаем id равным event_id из Google Calendar
                event_id=event_id,
                title=event_data.get("summary", "Без названия"),
                start_time=safe_parse_datetime(
                    event_data["start"].get("dateTime"), event_data["start"].get("timeZone")
                ),
                end_time=safe_parse_datetime(
                    event_data["end"].get("dateTime"), event_data["end"].get("timeZone")
                ),
                meet_link=event_data.get("hangoutLink"),
                user_id=user_id,
                all_data=event_data,
            )
            session.add(event)
            session.commit()
            logger.info(f"Сохранено новое событие: {event.title}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сохранении события: {e}")
            return False
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
            logger.info(f"Успешно получены события: {events}")
            return events
        except Exception as e:
            logger.error(f"Ошибка при получении событий: {e}")
            return []
        finally:
            session.close()


class NotificationQueries(Queries):
    def reset_notifications(self, user_id: int) -> None:
        """Сбрасывает все данные в базе"""
        session = self.db.get_session()
        try:
            session.query(Notification).filter(Notification.user_id == user_id).delete()
            session.commit()
        except Exception as e:
            logger.error(f"Ошибка при сбросе данных: {e}")
        finally:
            session.close()

    # Методы для работы с уведомлениями
    def create_notification(self, event_id: str, user_id: int) -> Notification | None:
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
                return existing

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

    def get_notification(self, event_id: str, user_id: int) -> Notification | None:
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
        finally:
            session.close()

    def check_all_notifications_sent(self, event_ids: tuple[str], user_id: int) -> bool:
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
        self.feedback = FeedbackQueries(self.db)
