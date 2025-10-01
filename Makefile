VENV=.venv
PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

.PHONY: venv run

venv:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e .

run:
	@if [ ! -d $(VENV) ]; then echo "Create venv first: make venv"; exit 1; fi
	# Load env vars if .env exists
	set -a; [ -f .env ] && . ./.env || true; set +a; \
	$(PYTHON) -m alembic upgrade head; \
	$(PYTHON) bot.py
