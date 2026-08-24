.PHONY: backend-install backend-test backend-lint backend-run frontend-install frontend-build frontend-test frontend-lint demo-reset demo-start

backend-install:
	python -m pip install -e "backend[dev]"

backend-test:
	python -m pytest backend/tests

backend-lint:
	python -m ruff check backend/forge backend/tests

backend-run:
	python -m uvicorn forge.api.main:app --app-dir backend --host 0.0.0.0 --port 8080

frontend-install:
	cd frontend && npm.cmd install

frontend-build:
	cd frontend && npm.cmd run build

frontend-test:
	cd frontend && npm.cmd run test -- --run

frontend-lint:
	cd frontend && npm.cmd run lint

demo-reset:
	python scripts/seed_demo.py

demo-start:
	python scripts/run_hero_flow.py
