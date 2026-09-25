PY ?= python
export PYTHONPATH := backend/src

setup:
	$(PY) -m pip install -e "./backend[dev]"
	cd frontend && npm install

init-db:
	$(PY) -m htpp.cli init-db

seed:
	$(PY) -m htpp.cli seed

backfill:
	$(PY) -m htpp.cli backfill

ingest:
	$(PY) -m htpp.cli ingest

excel:
	$(PY) -m htpp.cli excel

reparse:
	$(PY) -m htpp.cli reparse

build:
	$(PY) -m htpp.cli build

fit:
	$(PY) -m htpp.cli fit

coverage:
	$(PY) -m htpp.cli coverage

reproduce:
	$(PY) -m htpp.cli reproduce

api:
	$(PY) -m htpp.cli api

web:
	cd frontend && npm run dev

dev:
	$(PY) -m htpp.cli api

test:
	cd backend && $(PY) -m pytest -q

.PHONY: setup init-db seed backfill ingest excel reparse build fit coverage reproduce api web dev test
