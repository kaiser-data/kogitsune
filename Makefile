# kogitsune 🦊 — dev tasks
SHELL := bash
SCRIPTS := bin/kit lib/session-env.sh install.sh tests/test_launcher.sh

.PHONY: check test pytest launcher lint help
help:
	@echo "make check   — lint + all tests"
	@echo "make test    — pytest + launcher integration tests"
	@echo "make lint    — shellcheck the shell scripts"

check: lint test

test: pytest launcher

pytest:
	python3 -m pytest tests/ -q

launcher:
	bash tests/test_launcher.sh

lint:
	shellcheck -x --severity=warning $(SCRIPTS)
