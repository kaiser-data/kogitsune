# kogitsune 🦊 — dev tasks
SHELL := bash
SCRIPTS := bin/kit lib/session-env.sh install.sh lib/install-superpowers.sh lib/install-ponytail.sh lib/weight-sweep.sh tests/test_launcher.sh completions/kit.bash skills/lib/decider.sh tests/test_decider.sh

.PHONY: check test pytest launcher decider lint help superpowers superpowers-plugin superpowers-skills ponytail
help:
	@echo "make check              — lint + all tests"
	@echo "make test               — pytest + launcher + decider integration tests"
	@echo "make lint               — shellcheck the shell scripts"
	@echo "make superpowers        — install obra/superpowers (plugin + skills)"
	@echo "make superpowers-plugin — Mode A only: marketplace + plugin (with SessionStart hook)"
	@echo "make superpowers-skills — Mode B only: clone to vendor dir (à la carte, no hook)"
	@echo "make ponytail           — install DietrichGebert/ponytail, kit-only (off globally)"

superpowers:
	bash lib/install-superpowers.sh all
superpowers-plugin:
	bash lib/install-superpowers.sh plugin
superpowers-skills:
	bash lib/install-superpowers.sh skills

ponytail:
	bash lib/install-ponytail.sh all

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
