"""
Модуль профессионального логирования (`app/core/logging.py`).
Настраивает единый формат логов с поддержкой контекста запроса (request_id),
выводом в консоль и ротацией лог-файлов (`RotatingFileHandler`).
"""

import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import settings

# Контекстная переменная для хранения уникального ID HTTP-запроса (Request ID).
# Позволяет отслеживать все логи одного конкретного запроса клиента от начала до конца.
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="system")


class RequestIdFilter(logging.Filter):
    """
    Фильтр логгера, который автоматически добавляет поле `request_id`
    в каждую запись лога (`LogRecord`).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx_var.get()
        return True


def setup_logging() -> logging.Logger:
    """
    Инициализирует глобальную систему логирования приложения.
    Создает папку для логов, настраивает форматирование с временными метками,
    именем модуля, номером строки и идентификатором запроса.
    """
    log_path = Path(settings.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Строгий и читаемый формат логов для продакшена и отладки
    log_format = (
        "%(asctime)s | %(levelname)-8s | [req:%(request_id)s] | "
        "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    # Корневой логгер приложения
    root_logger = logging.getLogger("ubcashmere")
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    root_logger.handlers.clear()
    root_logger.propagate = False

    request_filter = RequestIdFilter()

    # 1. Обработчик вывода в консоль (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_filter)
    root_logger.addHandler(console_handler)

    # 2. Обработчик записи в файл с ротацией (до 10 МБ на файл, храним 5 архивов)
    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_filter)
    root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает дочерний логгер для конкретного модуля или роутера.
    Пример использования:
        logger = get_logger(__name__)
        logger.info("Запрос каталога товаров")
    """
    return logging.getLogger(f"ubcashmere.{name}")
