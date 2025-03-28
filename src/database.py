import logging
import os
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from datetime import datetime, timezone
from typing import Any, TypeVar, Optional, Dict, Union

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем базовый класс для моделей
Base = declarative_base()
BaseType = TypeVar("BaseType", bound=Any)


# Используем Type[BaseType] для аннотаций классов моделей
class User(Base):
    """Модель пользователя системы"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=True)
    full_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_bot = Column(Boolean, default=False)
    language_code = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, full_name='{self.full_name}')>"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """Создает объект пользователя из словаря"""
        if not data:
            raise ValueError("Данные пользователя не могут быть пустыми")
        
        user_id = data.get("id")
        if user_id is None:
            raise ValueError("ID пользователя обязателен")
        
        # Обработка имени пользователя
        full_name = data.get("full_name")
        if not full_name:
            first_name = data.get("first_name", "")
            last_name = data.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
        
        return cls(
            id=int(user_id),
            username=data.get("username", ""),
            full_name=full_name,
            is_bot=bool(data.get("is_bot", False)),
            language_code=data.get("language_code", ""),
        )


class Token(Base):
    """Модель токена авторизации"""

    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_data = Column(String(2048), nullable=False)  # Хранение токена в JSON формате
    status = Column(String(50), nullable=True)  # Статус токена
    redirect_url = Column(String(255), nullable=True)  # URL для перенаправления
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    user = relationship("User", back_populates="tokens")
    auth_message_id = Column(String(255), nullable=True)


class Event(Base):
    """Модель события календаря"""

    __tablename__ = "events"

    id = Column(String(255), primary_key=True)  # Первичный ключ - строка
    event_id = Column(
        String(100), unique=True, nullable=False
    )  # ID события в Google Calendar
    title = Column(String(200), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    meet_link = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    all_data = Column(JSON, nullable=True)

    user = relationship("User", back_populates="events")


class Notification(Base):
    """Модель уведомлений о событиях"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(255), ForeignKey("events.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime, nullable=True)
    is_sent = Column(Boolean, default=True)

    event = relationship("Event")
    user = relationship("User")


class Feedback(Base):
    """Модель обратной связи"""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(String(2048), nullable=True)
    message_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    rating = Column(Integer, nullable=True)


# Определение отношений
User.tokens = relationship("Token", back_populates="user", cascade="all, delete-orphan")
User.events = relationship("Event", back_populates="user", cascade="all, delete-orphan")


class Database:
    """Класс для работы с базой данных"""

    def __init__(self, db_url: Optional[str] = None):
        # Если URL базы данных не передан, пытаемся получить его из переменных окружения
        if db_url is None:
            db_url = os.environ.get("DATABASE_URL")
            
        if not db_url:
            # Если URL не найден в переменных окружения, используем SQLite как запасной вариант
            db_path = "/data/bot.db"
            db_url = f"sqlite:///{db_path}"
            logger.warning(f"URL базы данных не указан, используем SQLite: {db_path}")
        
        # Обработка переменных окружения в строке подключения
        if "${" in db_url:
            db_url = self._process_env_vars(db_url)
            
        # Настройки для PostgreSQL
        if db_url.startswith("postgresql"):
            self.engine = create_engine(
                db_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
            )
        else:
            # Настройки для SQLite
            self.engine = create_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )
            
        self.Session = scoped_session(sessionmaker(bind=self.engine))

        # Создаем таблицы, если они не существуют
        Base.metadata.create_all(self.engine)
        logger.info(f"База данных инициализирована: {db_url}")

    def _process_env_vars(self, url: str) -> str:
        """Обрабатывает переменные окружения в строке подключения"""
        import re
        
        def replace_env_var(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        
        # Заменяем ${VAR_NAME} на значение переменной окружения
        processed_url = re.sub(r'\${([^}]+)}', replace_env_var, url)
        return processed_url

    def get_session(self) -> Any:
        """Возвращает новую сессию базы данных"""
        return self.Session()

    def close_all_sessions(self) -> None:
        """Закрывает все сессии"""
        self.Session.remove()
