.PHONY: build up down test lint clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

test:
	docker compose exec orchestrator pytest tests/ evals/ -v

lint:
	docker compose exec orchestrator ruff check orchestrator/ api/

clean:
	docker compose down -v
	rm -rf data/*.db*
