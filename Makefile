.PHONY: setup lint test run

setup:
	python -m pip install -U pip
	pip install -r requirements.txt -r requirements-dev.txt

lint:
	ruff format .
	ruff check .

test:
	pytest

run:
	uvicorn app.main:app --host 0.0.0.0 --port 9700

