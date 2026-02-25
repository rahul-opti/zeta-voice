PYTHON_VERSION := 3.12
SHELL := /bin/bash

.ONESHELL:
install:
	curl -LsSf https://astral.sh/uv/install.sh | sh && \
	uv venv --python $(PYTHON_VERSION) && \
	source .venv/bin/activate && \
	uv pip install -e . && \
	uv run python -m ensurepip && \
	if [ "$${RUN_NEUTRALIZE_TEST:-false}" = "true" ]; then \
		uv pip install pytest && \
		uv run pytest tests/unit/test_neutralize_phrases.py -v -s; \
	fi

.ONESHELL:
install-dev: install
	source .venv/bin/activate && \
	uv pip install -e ".[dev]" && \
	npm install && \
 	pre-commit install && \
	uv run python -m ensurepip

run: .venv/bin/activate
	uv run serve

admin: .venv/bin/activate
	uv run admin

lint: .venv/bin/activate
	uv run pre-commit run --all-files
	uv run ./check_licenses.sh

promptfoo: .venv/bin/activate
	@echo "Running unified promptfoo test suite..."
	uv run npx promptfoo@latest eval -c tests/promptfoo/promptfooconfig.yaml --share -o output_promptfoo_results.json || true
	@echo "Promptfoo tests completed. Output file: output_promptfoo_results.json"

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .venv
	rm -rf uv.lock
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -f data/carriage.db
	rm -f carriage.db
	rm -f output_*.json
	rm -rf .promptfoo
	rm -rf node_modules

.PHONY: install install-dev run admin lint promptfoo clean
