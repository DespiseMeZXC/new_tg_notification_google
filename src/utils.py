import logging
import pytz
from datetime import datetime, timezone

def safe_parse_datetime(date_str: str, target_tz: str = "UTC") -> datetime:
    """
    Безопасно парсит строку даты в объект datetime
    Args:
        date_str: строка с датой
        target_tz: целевой часовой пояс (например 'Europe/Moscow')
    """
    try:
        if date_str.endswith("Z"):
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        elif "+" in date_str or "-" in date_str and "T" in date_str:
            dt = datetime.fromisoformat(date_str)
        else:
            dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

        if target_tz:
            # Конвертируем в целевой часовой пояс если он задан
            target_timezone = pytz.timezone(target_tz)
            return dt.astimezone(target_timezone)
        
        return dt.astimezone(timezone.utc)

    except Exception as e:
        logging.error(f"Ошибка при парсинге даты {date_str}: {e}")
        return datetime.now(timezone.utc) 
