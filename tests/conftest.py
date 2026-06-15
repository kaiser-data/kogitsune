"""Shared test helpers: load the hyphenated lib modules + point skills at fixtures."""
import importlib.util
import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, ROOT / "lib" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def buildcfg():
    return _load("buildcfg", "build-config.py")


@pytest.fixture(scope="session")
def ctxest():
    return _load("ctxest", "context-est.py")


@pytest.fixture(autouse=True)
def _skills_root(monkeypatch):
    monkeypatch.setenv("KOGITSUNE_SKILLS_DIR", str(FIXTURES / "skills"))


@pytest.fixture
def config(buildcfg):
    return buildcfg.load_yaml(str(FIXTURES / "kits.yaml"))


@pytest.fixture
def servers(buildcfg):
    import json
    return json.loads((FIXTURES / "mcp-on-demand.json").read_text())["mcpServers"]
