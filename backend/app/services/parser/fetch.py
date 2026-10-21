import asyncio
import time
from urllib import robotparser

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Fetcher:
    """Вежливый клиент: пауза между запросами, повторы с нарастающей задержкой."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.PARSER_USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"},
            timeout=settings.PARSER_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        self._last_request = 0.0

    async def __aenter__(self) -> "Fetcher":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def get(self, url: str) -> str | None:
        """Текст страницы. None для 404 и 410 или когда кончились попытки."""
        for attempt in range(1, settings.PARSER_RETRIES + 1):
            wait = settings.PARSER_DELAY_SECONDS - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self._client.get(url)
                self._last_request = time.monotonic()
                if response.status_code == 200:
                    return response.content.decode("utf-8", errors="replace")
                if response.status_code in (404, 410):
                    return None
                logger.warning("Сайт ответил ошибкой", extra={"url": url, "status": response.status_code, "attempt": attempt})
            except httpx.HTTPError as exc:
                self._last_request = time.monotonic()
                logger.warning("Сетевая ошибка", extra={"url": url, "error": type(exc).__name__, "attempt": attempt})
            await asyncio.sleep(3 * attempt)
        return None

    async def robots(self) -> robotparser.RobotFileParser:
        """Не удалось прочитать robots.txt, значит ограничений нет."""
        parser = robotparser.RobotFileParser()
        try:
            response = await self._client.get(settings.PARSER_BASE_URL + "/robots.txt", timeout=15)
            parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            parser.parse([])
        return parser
