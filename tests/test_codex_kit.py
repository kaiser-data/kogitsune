"""Codex kit selection: real protocol shape, no accounts or model calls required."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def codexkit():
    spec = importlib.util.spec_from_file_location("codexkit", ROOT / "lib/codex-kit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skill(name, scope="user", enabled=True, plugin=None, path=None):
    return dict(name=name, scope=scope, enabled=enabled, pluginId=plugin,
                path=path or f"/skills/{name}/SKILL.md", description=f"Use {name}")


@pytest.fixture
def inventory():
    return [skill("ecc:python", plugin="ecc@ecc"), skill("ecc:react", plugin="ecc@ecc"),
            skill("local"), skill("built-in", "system"), skill("project", "repo"),
            skill("disabled-project", "repo", False)]


def test_select_individual_plugin_skill_and_keep_enabled_scopes(codexkit, inventory):
    result = codexkit.select_skills(inventory, ["ecc:python"], ["local"])
    assert {s["name"] for s in result["selected"]} == {
        "ecc:python", "local", "built-in", "project"}
    assert {s["name"] for s in result["excluded"]} == {"ecc:react", "disabled-project"}


def test_ambiguous_names_require_disambiguation(codexkit):
    skills = [skill("same", plugin="one@market", path="/one/SKILL.md"),
              skill("same", plugin="two@market", path="/two/SKILL.md")]
    with pytest.raises(ValueError, match="ambiguous"):
        codexkit.select_skills(skills, ["same"], [])
    selected = codexkit.select_skills(skills, ["one@market/same"], [])
    assert selected["selected"][0]["path"] == "/one/SKILL.md"


def test_unknown_selector_fails(codexkit, inventory):
    with pytest.raises(ValueError, match="unknown skill"):
        codexkit.select_skills(inventory, ["typo"], [])


def test_resolve_new_plugin_version_and_explicitly_enable(codexkit):
    inv = [skill("ecc:python", enabled=False, plugin="ecc@ecc", path="/cache/v3/python/SKILL.md")]
    result = codexkit.select_skills(inv, ["ecc:python"], [])
    assert result["selected"][0]["enabled"] is True
    assert result["selected"][0]["was_enabled"] is False
    overrides = codexkit.skill_overrides(inv, result, [])
    assert overrides == [{"path": "/cache/v3/python/SKILL.md", "enabled": True}]


def test_overrides_keep_undiscovered_entries_and_replace_known(codexkit, inventory):
    existing = [{"path": "/absent/SKILL.md", "enabled": False},
                {"path": inventory[0]["path"], "enabled": False}]
    selected = codexkit.select_skills(inventory, ["ecc:python"], [])
    entries = codexkit.skill_overrides(inventory, selected, existing)
    assert entries[0] == existing[0]
    assert [x for x in entries if x["path"] == inventory[0]["path"]] == [
        {"path": inventory[0]["path"], "enabled": True}]


def test_codex_config_is_separate_and_inherits(codexkit):
    config = {"kits": {"python": {"model": "opus", "skills": ["claude"]}},
              "codex": {"pinned": ["local"], "kits": {
                  "base": {"skills": ["ecc:python"]},
                  "python": {"extends": "base", "skills": ["-ecc:python", "+ecc:react"]}}}}
    section = codexkit.codex_config(config)
    assert codexkit.resolve_preset(section, "python")["skills"] == ["ecc:react"]
    assert codexkit.resolve_preset(section, "python")["model"] is None
    assert "lean" in section["kits"]


def test_toml_preserves_quotes_unicode_and_shell_characters(codexkit):
    import tomllib
    entries = [{"path": '/tmp/🦊 " $HOME `touch evil`/SKILL.md', "enabled": False}]
    assert tomllib.loads("skills.config=" + codexkit.toml_value(entries))["skills"]["config"] == entries


def test_launch_context_cd_overrides_and_prompt(codexkit, tmp_path):
    cwd, overrides, args = codexkit.launch_context(
        ["-C", str(tmp_path), "-c", 'plugins."ecc@ecc".enabled=true', "-m", "chosen", "hello $x"], None)
    assert cwd == str(tmp_path.resolve())
    assert 'plugins."ecc@ecc".enabled=true' in overrides
    assert args[-2:] == ["--", "hello $x"]
    assert "--cd" not in args and "-C" not in args


@pytest.mark.parametrize("args", [["--remote", "unix://foo"], ["--worktree"],
                                     ["exec", "hello"], ["-c", "skills.config=[]"],
                                     ["--profile", "work"], ["-c", 'profile="work"']])
def test_reject_contexts_that_escape_selection(codexkit, args):
    with pytest.raises((ValueError, SystemExit)):
        codexkit.launch_context(args, None)


def test_save_preserves_claude_content(codexkit, tmp_path):
    path = tmp_path / "kits.yaml"
    prefix = '# keep this comment\nkits:\n  db: {model: opus, skills: [postgres]}\n'
    path.write_text(prefix)
    codexkit.save_preset(path, "python", ["ecc:python"], None)
    codexkit.save_preset(path, "other", ["ecc:react"], "model-id")
    assert path.read_text().startswith(prefix)
    config = yaml.safe_load(path.read_text())
    assert config["codex"]["kits"]["python"]["skills"] == ["ecc:python"]
    assert config["codex"]["kits"]["other"]["model"] == "model-id"


@pytest.fixture
def fake_cli(tmp_path, inventory):
    executable = tmp_path / "codex"
    data = tmp_path / "inventory.json"
    data.write_text(json.dumps(inventory))
    log = tmp_path / "calls.jsonl"
    executable.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys, tomllib
args = sys.argv[1:]
with open(os.environ['FAKE_CODEX_LOG'], 'a') as f:
    f.write(json.dumps({'args': args, 'cwd': os.getcwd()}) + '\\n')
if not args or args[0] != 'app-server':
    sys.exit(int(os.environ.get('FAKE_EXIT', '0')))
skills = json.loads(pathlib.Path(os.environ['FAKE_INVENTORY']).read_text())
config = {}
for i, arg in enumerate(args):
    if arg == '-c':
        config.update(tomllib.loads(args[i + 1]))
for s in skills:
    for entry in config.get('skills', {}).get('config', []):
        if entry.get('path') == s['path'] and not os.environ.get('FAKE_IGNORE_OVERRIDES'):
            s['enabled'] = entry['enabled']
for line in sys.stdin:
    msg = json.loads(line)
    if 'id' not in msg: continue
    method = msg['method']
    if method == 'initialize': result = {'userAgent': 'fake/0.154.0'}
    elif method == 'config/read': result = {'config': config}
    elif method == 'skills/list':
        result = {'data': [{'cwd': msg['params']['cwds'][0], 'skills': skills, 'errors': []}]}
    else:
        print(json.dumps({'id': msg['id'], 'error': {'message': 'unexpected method'}}), flush=True)
        continue
    print(json.dumps({'method': 'notification', 'params': {}}), flush=True)
    print(json.dumps({'id': msg['id'], 'result': result}), flush=True)
''')
    executable.chmod(0o755)
    config = tmp_path / "kits.yaml"
    config.write_text(yaml.safe_dump({"codex": {"kits": {"python": {"skills": ["ecc:python"]}}}}))
    env = dict(os.environ, KOGITSUNE_CODEX=str(executable), KOGITSUNE_CONFIG=str(config),
               KOGITSUNE_PYTHON=sys.executable, FAKE_CODEX_LOG=str(log), FAKE_INVENTORY=str(data))
    return env, log, config


def run_kit(fake_cli, *args, **kwargs):
    env, log, config = fake_cli
    return subprocess.run([str(ROOT / "bin/kit"), "codex", *args],
                          cwd=config.parent, env=env, text=True, capture_output=True, **kwargs)


def test_cli_dry_run_verifies_without_launching(fake_cli):
    result = run_kit(fake_cli, "python", "--dry-run")
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["verified"] is True
    assert manifest["selected_count"] == 3
    calls = [json.loads(s) for s in fake_cli[1].read_text().splitlines()]
    assert len(calls) == 2 and all(x["args"][0] == "app-server" for x in calls)


def test_cli_launch_arguments_and_exit_code(fake_cli):
    fake_cli[0]["FAKE_EXIT"] = "7"
    result = run_kit(fake_cli, "python", "--", "--model", "chosen", "fix $(touch nope)")
    assert result.returncode == 7, result.stderr
    calls = [json.loads(s) for s in fake_cli[1].read_text().splitlines()]
    assert calls[-1]["args"][-2:] == ["--", "fix $(touch nope)"]
    assert 'model="chosen"' in calls[-1]["args"]
    assert not (fake_cli[2].parent / "nope").exists()


def test_cli_fails_if_codex_ignores_plugin_filter(fake_cli):
    fake_cli[0]["FAKE_IGNORE_OVERRIDES"] = "1"
    result = run_kit(fake_cli, "python")
    assert result.returncode != 0
    assert "did not apply" in result.stderr
    assert all(json.loads(s)["args"][0] == "app-server" for s in fake_cli[1].read_text().splitlines())


def test_effective_cwd_overlay_is_used(fake_cli, tmp_path):
    fake_cli[0]["KOGITSUNE_CODEX"] = "./codex"
    project = tmp_path / "project space"
    project.mkdir()
    (project / ".kogitsune.yaml").write_text('codex:\n  kits:\n    python:\n      skills: [ecc:react]\n')
    result = run_kit(fake_cli, "python", "--dry-run", "--", "-C", str(project), "-c", 'plugins."ecc@ecc".enabled=true')
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert "ecc:react" in {s["name"] for s in manifest["selected"]}
    assert "ecc:python" not in {s["name"] for s in manifest["selected"]}
    calls = [json.loads(s) for s in fake_cli[1].read_text().splitlines()]
    assert all(c["cwd"] == str(project) and 'plugins."ecc@ecc".enabled=true' in c["args"] for c in calls)


def test_cli_save_and_completion_do_not_change_codex_settings(fake_cli):
    result = run_kit(fake_cli, "save", "mine", "--skills", "ecc:react,local")
    assert result.returncode == 0, result.stderr
    assert yaml.safe_load(fake_cli[2].read_text())["codex"]["kits"]["mine"]["skills"] == ["ecc:react", "local"]
    fake_cli[1].unlink()
    result = run_kit(fake_cli, "__kits")
    assert result.returncode == 0 and "mine" in result.stdout
    assert not fake_cli[1].exists()


def test_dry_run_save_is_rejected_before_mutation(fake_cli):
    before = fake_cli[2].read_bytes()
    result = run_kit(fake_cli, "save", "oops", "--skills", "local", "--dry-run")
    assert result.returncode != 0
    assert fake_cli[2].read_bytes() == before
    assert not fake_cli[1].exists()


def test_cyclic_inheritance_fails(codexkit):
    section = codexkit.codex_config({"codex": {"kits": {
        "a": {"extends": "b"}, "b": {"extends": "a"}}}})
    with pytest.raises(ValueError, match="circular"):
        codexkit.resolve_preset(section, "a")


def test_save_preserves_following_yaml_section(codexkit, tmp_path):
    path = tmp_path / "kits.yaml"
    path.write_text('codex:\n  kits:\n    lean: {skills: []}\nkits:\n  db: {skills: [postgres]}\n')
    codexkit.save_preset(path, "new", ["local"], None)
    assert yaml.safe_load(path.read_text())["kits"] == {"db": {"skills": ["postgres"]}}


@pytest.fixture
def fake_fzf(fake_cli):
    path = fake_cli[2].parent / "fzf"
    path.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
rows = sys.stdin.read()
pathlib.Path(os.environ['FAKE_FZF_LOG']).write_text(json.dumps({'args': sys.argv, 'rows': rows}))
if os.environ.get('FAKE_FZF_CANCEL'): sys.exit(130)
print(os.environ.get('FAKE_FZF_OUTPUT', 'enter\\n0\\tecc:python'), end='\\n')
''')
    path.chmod(0o755)
    fake_cli[0]["KOGITSUNE_FZF"] = str(path)
    fake_cli[0]["FAKE_FZF_LOG"] = str(path.parent / "fzf-log.json")
    return fake_cli


def test_picker_preselects_preset_and_omits_fixed_skills(fake_fzf):
    result = run_kit(fake_fzf, "tune", "python", "--dry-run")
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["selected_count"] == 3
    log = json.loads(Path(fake_fzf[0]["FAKE_FZF_LOG"]).read_text())
    assert "--sync" in log["args"]
    assert "--bind=start:pos(1)+select+first" in log["args"]
    assert "built-in" not in log["rows"] and "\tproject\t" not in log["rows"]


def test_picker_empty_selection_does_not_add_focused_row(fake_fzf):
    fake_fzf[0]["FAKE_FZF_OUTPUT"] = "enter\n__empty__\n0\tecc:python"
    result = run_kit(fake_fzf, "tune", "python", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["selected_count"] == 2


def test_picker_cancel_never_launches(fake_fzf):
    fake_fzf[0]["FAKE_FZF_CANCEL"] = "1"
    result = run_kit(fake_fzf, "tune", "python")
    assert result.returncode == 130
    assert len(fake_fzf[1].read_text().splitlines()) == 1


def test_rpc_times_out_and_cleans_up(codexkit, tmp_path):
    executable = tmp_path / "sleeping-codex"
    executable.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n')
    executable.chmod(0o755)
    client = codexkit.rpc.CodexRPC(str(executable), str(tmp_path), [], timeout=0.05)
    with pytest.raises(codexkit.rpc.CodexError, match="timed out"):
        with client:
            pass
    assert client.process.poll() is not None


def test_rpc_reports_discovery_errors(codexkit, tmp_path):
    executable = tmp_path / "failing-codex"
    executable.write_text('''#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    if 'id' in msg:
        print(json.dumps({'id': msg['id'], 'error': {'message': 'skill inventory unavailable'}}), flush=True)
''')
    executable.chmod(0o755)
    client = codexkit.rpc.CodexRPC(str(executable), str(tmp_path), [])
    with pytest.raises(codexkit.rpc.CodexError, match="inventory unavailable"):
        with client:
            pass
    assert client.process.poll() is not None


def test_picker_save_reads_and_writes_nonseekable_terminal(codexkit, monkeypatch):
    import io
    picker = codexkit.load_module("picker_test", "codex-picker.py")
    monkeypatch.setattr(picker, "fzf", lambda *_: "ctrl-s\n0\tlocal\n")

    class Terminal(io.StringIO):
        def close(self):
            pass

    reader, writer = Terminal("my-kit\n"), Terminal()

    def open_tty(path, mode):
        assert path == "/dev/tty"
        if "+" in mode:
            raise io.UnsupportedOperation("File or stream is not seekable")
        return reader if mode == "r" else writer

    monkeypatch.setattr("builtins.open", open_tty)
    result = picker.pick_skills([skill("local")], {"selected": []}, ["local"])
    assert result == (["local"], "my-kit")
    assert "Save Codex kit as:" in writer.getvalue()
