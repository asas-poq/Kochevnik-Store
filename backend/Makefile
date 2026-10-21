up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm worker python -m scripts.seed_from_parser

# make parser ARGS="scrape --limit 20"
parser:
	docker compose run --rm worker python -m app.services.parser $(ARGS)

test:
	pytest -q

lint:
	ruff check . && ruff format --check .

.PHONY: up down migrate seed parser test lint
