.PHONY: install test lint migrate run

install:
	python -m pip install -e '.[dev]'

test:
	pytest -q

lint:
	ruff check src tests

migrate:
	alembic upgrade head

run:
	uvicorn dd_context_engine.api.app:app --host 0.0.0.0 --port 8000
