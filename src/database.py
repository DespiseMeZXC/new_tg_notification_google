import logging
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from datetime import datetime
from typing import Any, TypeVar

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем базовый класс для моделей
Base = declarative_base()
BaseType = TypeVar("BaseType", bound=Any)


# Используем Type[BaseType] для аннотаций классов моделей
class User(Base):  # type: ignore
    """Модель пользователя системы"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=True)
    full_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, full_name='{self.full_name}')>"


class Token(Base):  # type: ignore
    """Модель токена авторизации"""

    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_data = Column(String(2048), nullable=False)  # Хранение токена в JSON формате
    status = Column(String(50), nullable=True)  # Статус токена
    redirect_url = Column(String(255), nullable=True)  # URL для перенаправления
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="tokens")  # type: ignore


class Event(Base):  # type: ignore
    """Модель события календаря"""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    event_id = Column(
        String(100), unique=True, nullable=False
    )  # ID события в Google Calendar
    title = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    location = Column(String(200), nullable=True)
    meet_link = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="events")  # type: ignore


class Notification(Base):  # type: ignore
    """Модель уведомлений о событиях"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime, nullable=True)
    is_sent = Column(Boolean, default=False)

    event = relationship("Event")  # type: ignore
    user = relationship("User")  # type: ignore


# Определение отношений
User.tokens = relationship("Token", back_populates="user", cascade="all, delete-orphan")
User.events = relationship("Event", back_populates="user", cascade="all, delete-orphan")


class Database:
    """Класс для работы с базой данных"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self.Session = scoped_session(sessionmaker(bind=self.engine))

        # Создаем таблицы, если они не существуют
        Base.metadata.create_all(self.engine)
        logger.info(f"База данных инициализирована: {db_path}")

    def get_session(self) -> Any:
        """Возвращает новую сессию базы данных"""
        return self.Session()

    def close_all_sessions(self) -> None:
        """Закрывает все сессии"""
        self.Session.remove()  # type: ignore
