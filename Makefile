.PHONY: help venv install reinstall run compile clean build freeze dev lint format test uninstall

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.DEFAULT_GOAL := help

help: ## показать список команд
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(VENV)/bin/python:
	python3 -m venv $(VENV)

venv: $(VENV)/bin/python ## создать .venv

install: venv ## поставить пакет (editable)
	$(PIP) install -e .

reinstall: venv ## переустановить с нуля (после переезда папок)
	$(PIP) install -e . --force-reinstall

uninstall: ## удалить пакет из venv
	$(PIP) uninstall -y parking-motion

run: ## запустить GUI
	$(PY) -m parking_motion

compile: ## проверить синтаксис всех модулей
	$(PY) -m compileall -q parking_motion

build: venv ## собрать sdist + wheel в dist/
	$(PIP) install --upgrade build
	$(PY) -m build

freeze: ## зафиксировать версии зависимостей в requirements.lock
	$(PIP) freeze > requirements.lock

clean: ## удалить кеши и артефакты сборки
	rm -rf build dist parking_motion.egg-info
	find parking_motion -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .ruff_cache .pytest_cache .mypy_cache

dev: venv ## поставить инструменты разработки (ruff, pytest)
	$(PIP) install -e ".[dev]" ruff

lint: ## ruff check
	$(VENV)/bin/ruff check parking_motion

format: ## ruff format
	$(VENV)/bin/ruff format parking_motion

test: ## запустить pytest
	$(PY) -m pytest
