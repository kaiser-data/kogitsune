# kogitsune 🦊 — dev tasks
SHELL := bash
SCRIPTS := bin/kit lib/session-env.sh install.sh lib/install-superpowers.sh tests/test_launcher.sh completions/kit.bash skills/lib/decider.sh tests/test_decider.sh

.PHONY: check test pytest launcher decider lint help superpowers superpowers-plugin superpowers-skills
help:
	@echo "make check              — lint + all tests"
	@echo "make test               — pytest + launcher + decider integration tests"
	@echo "make lint               — shellcheck the shell scripts"
	@echo "make superpowers        — install obra/superpowers (plugin + skills)"
	@echo "make superpowers-plugin — Mode A only: marketplace + plugin (with SessionStart hook)"
	@echo "make superpowers-skills — Mode B only: clone to vendor dir (à la carte, no hook)"

superpowers:
	bash lib/install-superpowers.sh all
superpowers-plugin:
	bash lib/install-superpowers.sh plugin
superpowers-skills:
	bash lib/install-superpowers.sh skills

check: lint test

test: pytest launcher decider

pytest:
	python3 -m pytest tests/ -q

launcher:
	bash tests/test_launcher.sh

decider:
	bash tests/test_decider.sh

lint:
	shellcheck -x --severity=warning $(SCRIPTS)
