import argparse
import asyncio
import json
import sys

from app.core.logging import setup_logging
from app.services.parser import jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Парсер ubcashmere.ru, пишет в основную БД")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="найти ссылки на товары и положить в crawl_queue")
    scrape = sub.add_parser("scrape", help="разобрать карточки из очереди")
    scrape.add_argument("--limit", type=int)
    scrape.add_argument("--retry-errors", action="store_true")
    debug = sub.add_parser("debug", help="разобрать одну страницу, в БД не писать")
    debug.add_argument("url")
    sub.add_parser("export", help="выгрузить CSV")
    sub.add_parser("stats", help="статистика по БД")
    args = parser.parse_args()

    setup_logging()
    if args.cmd == "discover":
        result = asyncio.run(jobs.run_named("discover", {}))
    elif args.cmd == "scrape":
        result = asyncio.run(jobs.run_named("scrape", {"limit": args.limit, "retry_errors": args.retry_errors}))
    elif args.cmd == "debug":
        result = asyncio.run(jobs.preview_product(args.url, save_html=True))
        if result is None:
            sys.exit("страница не скачалась")
    elif args.cmd == "export":
        result = asyncio.run(jobs.run_export())
    else:
        result = asyncio.run(jobs.get_stats())
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
