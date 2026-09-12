"""Audit guarantees: metadata only, honest unknowns, no credential/file reads."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def audit():
    path = Path(__file__).resolve().parents[1] / "lib/codex-audit.py"
    spec = importlib.util.spec_from_file_location("codex_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def context(tmp_path):
    cwd = tmp_path / "project"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    codex_home = home / ".codex"
    codex_home.mkdir()
    manifest = {"kit": "lean", "cwd": str(cwd), "verified": True, "selected_count": 1,
                "excluded_count": 100, "selected": [
                    {"name": "built-in", "path": "/skills/builtin/SKILL.md", "scope": "system",
                     "pluginId": None, "reason": "retained", "description": "not copied"}],
                "argv": ["codex", "-c", 'secret="ARGUMENT_SECRET_123"']}
    snapshot = {"codex_home": str(codex_home), "configuration": {"config": {}, "layers": []},
                "hooks": None, "plugins": None, "requirements": None}
    return manifest, snapshot, home, codex_home


def report(audit, context, extra=()):
    manifest, snapshot, home, _ = context
    return audit.build_report(manifest, snapshot, extra, home=home,
                              environment_names={"OPENAI_API_KEY", "PATH", "SSH_AUTH_SOCK"})


def test_missing_runtime_apis_are_unknown(audit, context):
    result = report(audit, context)
    assert result["skills"]["verified"] is True
    assert result["permissions"]["sandbox_mode"]["configured"] == "unknown"
    assert result["permissions"]["managed_requirements"]["status"] == "unknown"
    assert result["integrations"]["hooks"]["status"] == "unknown"
    assert result["integrations"]["plugins"]["status"] == "unknown"
    assert "unknown" in result["permissions"]["enforcement"]


def test_values_in_every_sensitive_surface_are_omitted(audit, context):
    _, snapshot, _, _ = context
    secrets = ["ARGUMENT_SECRET_123", "MCP_PASSWORD_123", "HEADER_SECRET_123", "ENV_SECRET_123",
               "HOOK_SECRET_123", "INSTRUCTION_SECRET_123", "PROVIDER_SECRET_123", "ERROR_SECRET_123"]
    snapshot["configuration"]["config"] = {
        "mcp_servers": {"db": {"url": "https://user:MCP_PASSWORD_123@example.com/?key=MCP_PASSWORD_123",
                                 "env": {"DB_PASSWORD": "ENV_SECRET_123"},
                                 "http_headers": {"Authorization": "HEADER_SECRET_123"},
                                 "bearer_token_env_var": "DB_TOKEN",
                                 "command": "bash -c echo MCP_PASSWORD_123"}},
        "developer_instructions": "INSTRUCTION_SECRET_123",
        "shell_environment_policy": {"set": {"API_TOKEN": "ENV_SECRET_123"}},
        "model_providers": {"custom": {"env_key": "CUSTOM_KEY", "experimental_bearer_token": "PROVIDER_SECRET_123"}},
    }
    snapshot["configuration"]["layers"] = [{"name": {"type": "user", "file": "/config.toml"},
                                             "config": {"api_key": "PROVIDER_SECRET_123"},
                                             "disabledReason": "ERROR_SECRET_123"}]
    snapshot["hooks"] = {"data": [{"hooks": [{"eventName": "sessionStart", "handlerType": "command",
        "command": "curl --token HOOK_SECRET_123", "sourcePath": "/hooks.json", "enabled": True,
        "trustStatus": "untrusted", "source": "plugin", "pluginId": "ecc@ecc"}],
        "errors": [{"message": "ERROR_SECRET_123"}], "warnings": ["ERROR_SECRET_123"]}]}
    result = report(audit, context)
    output = json.dumps(result) + audit.render(result)
    for secret in secrets:
        assert secret not in output
    assert "DB_PASSWORD" in output and "DB_TOKEN" in output and "CUSTOM_KEY" in output
    assert result["integrations"]["hooks"]["status"] == "partial"
    assert result["integrations"]["hooks"]["items"][0]["trust"] == "untrusted"


def test_declared_plugin_mcp_is_visible_even_without_plugin_skills(audit, context):
    _, snapshot, _, _ = context
    snapshot["plugins"] = {"marketplaces": [{"plugins": [
        {"id": "ecc@ecc", "installed": True, "enabled": True},
        {"id": "off@local", "installed": True, "enabled": False}]}]}
    snapshot["plugin_details"] = {
        "ecc@ecc": {"mcpServers": ["chrome-devtools"]},
        "off@local": {"mcpServers": ["disabled-server"]}}
    result = report(audit, context)
    servers = result["integrations"]["mcp_servers"]
    assert servers[0]["name"] == "chrome-devtools"
    assert servers[0]["configured_enabled"] is True
    assert servers[0]["runtime_status"] == "not connected"
    assert servers[1]["configured_enabled"] is False


def test_plugin_server_override_can_disable_declared_component(audit, context):
    _, snapshot, _, _ = context
    snapshot["configuration"]["config"]["plugins"] = {
        "ecc@ecc": {"enabled": True, "mcp_servers": {"chrome": {"enabled": False}}}}
    snapshot["plugins"] = {"marketplaces": [{"plugins": [{"id": "ecc@ecc", "installed": True, "enabled": True}]}]}
    snapshot["plugin_details"] = {"ecc@ecc": {"mcpServers": ["chrome"]}}
    assert report(audit, context)["integrations"]["mcp_servers"][0]["configured_enabled"] is False


def test_permissions_distinguish_config_cli_and_enforcement(audit, context):
    _, snapshot, _, _ = context
    snapshot["configuration"]["config"] = {
        "sandbox_mode": "read-only", "approval_policy": "on-request",
        "sandbox_workspace_write": {"network_access": False, "writable_roots": ["/work"]},
        "features": {"network_proxy": {"enabled": True, "domains": {"example.com": "allow"}}},
    }
    snapshot["requirements"] = {"requirements": {"allowedSandboxModes": ["read-only"]}}
    result = report(audit, context, ["--sandbox", "workspace-write", "--ask-for-approval", "never",
                                     "--add-dir", "/extra", "--search"])
    permissions = result["permissions"]
    assert permissions["sandbox_mode"] == {"configured": "read-only", "cli_requested": "workspace-write"}
    assert permissions["approval_policy"]["cli_requested"] == "never"
    assert permissions["additional_cli_directories"] == ["/extra"]
    assert permissions["managed_requirements"]["allowed_sandbox_modes"] == ["read-only"]
    assert permissions["workspace_network_access"] is False
    assert permissions["web_search"]["cli_requested"] == "live"
    assert "example.com" in audit.render(result)


def test_bypass_flags_are_visible_and_prompt_flags_are_not_options(audit, context):
    result = report(audit, context, ["--dangerously-bypass-approvals-and-sandbox",
                                    "--dangerously-bypass-hook-trust"])
    assert result["permissions"]["bypass_requested"] is True
    assert result["integrations"]["hooks"]["trust_bypass_requested"] is True
    result = report(audit, context, ["--", "--dangerously-bypass-approvals-and-sandbox"])
    assert result["permissions"]["bypass_requested"] is False
    result = report(audit, context, ["--", "--dangerously-bypass-hook-trust"])
    assert result["integrations"]["hooks"]["trust_bypass_requested"] is False


def test_instruction_precedence_and_file_presence_without_reading(audit, context, monkeypatch):
    manifest, snapshot, home, codex_home = context
    root = Path(manifest["cwd"])
    (root / ".git").mkdir()
    nested = root / "service"
    nested.mkdir()
    (codex_home / "AGENTS.override.md").write_text("")
    (codex_home / "AGENTS.md").write_text("private global instructions")
    (codex_home / "auth.json").write_text('{"access_token":"NEVER_READ"}')
    (root / "AGENTS.md").write_text("private root instructions")
    (root / "AGENTS.override.md").write_text("private override")
    (nested / "TEAM.md").write_text("private fallback")
    manifest["cwd"] = str(nested)
    snapshot["configuration"]["config"]["project_doc_fallback_filenames"] = ["TEAM.md"]

    def deny_open(*_args, **_kwargs):
        pytest.fail("audit must not open instruction or credential contents")

    monkeypatch.setattr(Path, "open", deny_open)
    result = report(audit, context)
    paths = [p["path"] for p in result["instructions"]["files"]]
    assert paths == [str(codex_home / "AGENTS.md"), str(root / "AGENTS.override.md"), str(nested / "TEAM.md")]
    assert result["credentials"]["known_file_locations"][0]["status"] == "present"
    assert "NEVER_READ" not in json.dumps(result)


def test_credentials_report_names_and_unknown_shell_visibility(audit, context):
    result = report(audit, context)
    assert result["credentials"]["launcher_environment_candidates"] == ["OPENAI_API_KEY", "SSH_AUTH_SOCK"]
    assert result["credentials"]["shell_policy"]["tool_shell_visibility"] == "unknown"


def test_terminal_control_characters_in_metadata_are_removed(audit, context):
    context[0]["selected"][0]["name"] = "skill\x1b[2J\nspoof"
    assert "\x1b" not in audit.render(report(audit, context))
