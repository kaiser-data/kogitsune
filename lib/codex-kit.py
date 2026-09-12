#!/usr/bin/env python3
"""Codex skill presets and launcher; keeps the user's real Codex home intact."""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bc = load_module("kogitsune_build", "build-config.py")
rpc = load_module("kogitsune_rpc", "codex-rpc.py")
RETAINED_SCOPES = {"system", "admin", "repo"}
RESERVED = {"ls", "list", "show", "save", "tune", "pick", "help", "__kits"}


def string_list(value, label):
    if not isinstance(value, list) or any(not isinstance(s, str) or not s for s in value):
        raise ValueError(f"{label} must be a list of nonempty strings")
    return value


def codex_config(config):
    section = config.get("codex") or {}
    if not isinstance(section, dict):
        raise ValueError("codex must be a mapping")
    pinned = string_list(section.get("pinned", []), "codex.pinned")
    kits = section.get("kits") or {}
    if not isinstance(kits, dict):
        raise ValueError("codex.kits must be a mapping")
    for name, preset in kits.items():
        if not isinstance(name, str) or not re.fullmatch(r"[\w-]+", name) or name in RESERVED:
            raise ValueError(f"invalid or reserved Codex kit name: {name!r}")
        if not isinstance(preset, dict):
            raise ValueError(f"codex.kits.{name} must be a mapping")
        unknown = set(preset) - {"skills", "extends", "model"}
        if unknown:
            raise ValueError(f"unsupported Codex kit fields in {name}: {', '.join(sorted(unknown))}")
        string_list(preset.get("skills", []), f"codex.kits.{name}.skills")
        for key in ("extends", "model"):
            if key in preset and (not isinstance(preset[key], str) or not preset[key]):
                raise ValueError(f"codex.kits.{name}.{key} must be a nonempty string")
    return {"pinned": pinned, "kits": {"lean": {"skills": []}, **kits}}


def resolve_preset(section, name):
    return bc.resolve_kit(name, section["kits"])


def skill_selectors(skills):
    """Use Codex's qualified name; add plugin ID or path only for collisions."""
    names = collections.Counter(s["name"] for s in skills)
    candidates = [f"{s['pluginId']}/{s['name']}" if s.get("pluginId") else s["path"] for s in skills]
    qualified = collections.Counter(candidates)
    return [s["name"] if names[s["name"]] == 1 else
            candidate if qualified[candidate] == 1 else s["path"]
            for s, candidate in zip(skills, candidates)]


def select_skills(skills, requested, pinned):
    selectors = skill_selectors(skills)
    chosen = set()
    pins = set()
    for target, is_pin in [(s, False) for s in requested] + [(s, True) for s in pinned]:
        matches = [i for i, s in enumerate(skills)
                   if target in {s["name"], s["path"], selectors[i]}]
        if not matches:
            raise ValueError(f"unknown skill {target!r}; use 'kit codex ls' for installed names")
        if len(matches) > 1:
            options = ", ".join(selectors[i] for i in matches)
            raise ValueError(f"ambiguous skill {target!r}; choose one of: {options}")
        chosen.add(matches[0])
        if is_pin:
            pins.add(matches[0])
    selected, excluded = [], []
    for i, s in enumerate(skills):
        retained = s["scope"] in RETAINED_SCOPES and s["enabled"]
        entry = dict(s, selector=selectors[i])
        entry["was_enabled"] = s["enabled"]
        entry["enabled"] = bool(retained or i in chosen)
        entry["reason"] = "pinned" if i in pins else "retained" if retained else "kit" if i in chosen else "excluded"
        (selected if retained or i in chosen else excluded).append(entry)
    return {"selected": selected, "excluded": excluded}


def skill_overrides(skills, selection, existing):
    paths = {s["path"] for s in skills}
    names = {s["name"] for s in skills}
    # Keep entries for skills absent from this inventory, e.g. disabled plugins.
    entries = [dict(e) for e in existing
               if e.get("path") not in paths and e.get("name") not in names]
    enabled = {s["path"] for s in selection["selected"]}
    entries.extend({"path": s["path"], "enabled": s["path"] in enabled} for s in skills)
    return entries


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(toml_value(k) + "=" + toml_value(v)
                              for k, v in value.items() if v is not None) + "}"
    raise ValueError(f"unsupported value in Codex skill settings: {type(value).__name__}")


def launch_context(arguments, model):
    """Normalize discovery-affecting options and launch in the exact same cwd."""
    parser = argparse.ArgumentParser(prog="kit codex <kit> --", allow_abbrev=False)
    parser.add_argument("-C", "--cd")
    parser.add_argument("-p", "--profile")
    parser.add_argument("-m", "--model")
    parser.add_argument("-c", "--config", action="append", default=[])
    parser.add_argument("--enable", action="append", default=[])
    parser.add_argument("--disable", action="append", default=[])
    parser.add_argument("-s", "--sandbox", choices=["read-only", "workspace-write", "danger-full-access"])
    parser.add_argument("-a", "--ask-for-approval", choices=["on-request", "never"])
    parser.add_argument("--add-dir", action="append", default=[])
    parser.add_argument("-i", "--image", action="append", default=[])
    for flag in ("no-alt-screen", "search", "approve-for-me", "strict-config",
                 "dangerously-bypass-approvals-and-sandbox", "dangerously-bypass-hook-trust"):
        parser.add_argument("--" + flag, action="store_true")
    parser.add_argument("prompt", nargs="?")
    ns = parser.parse_args(arguments)
    if ns.profile:
        raise ValueError("--profile is not supported by Codex's app-server inventory API; "
                         "use a Codex kit and individual -c overrides instead")
    cwd = str(Path(ns.cd or os.getcwd()).expanduser().resolve(strict=True))
    if not Path(cwd).is_dir():
        raise ValueError(f"working directory is not a directory: {cwd}")
    overrides = list(ns.config)
    for value in overrides:
        key, sep, _ = value.partition("=")
        if not sep or not key.strip():
            raise ValueError("Codex --config expects key=value")
        if key.split(".")[0].strip().strip("\"'") == "skills":
            raise ValueError("kit codex manages skills settings; use a kit to select skills")
        if key.strip().strip("\"'") == "profile":
            raise ValueError("profile overrides are not supported by Codex's app-server inventory API")
    if ns.model or model:
        overrides.append("model=" + toml_value(ns.model or model))
    for enabled, features in ((True, ns.enable), (False, ns.disable)):
        for feature in features:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", feature):
                raise ValueError(f"invalid Codex feature name: {feature}")
            overrides.append(f"features.{feature}={str(enabled).lower()}")
    args = []
    for key in ("sandbox", "ask_for_approval"):
        if getattr(ns, key):
            args.extend(["--" + key.replace("_", "-"), getattr(ns, key)])
    for key in ("add_dir", "image"):
        for value in getattr(ns, key):
            args.extend(["--" + key.replace("_", "-"), value])
    for key in ("no_alt_screen", "search", "approve_for_me", "strict_config",
                "dangerously_bypass_approvals_and_sandbox", "dangerously_bypass_hook_trust"):
        if getattr(ns, key):
            args.append("--" + key.replace("_", "-"))
    if ns.prompt is not None:
        args.extend(["--", ns.prompt])
    return cwd, overrides, args


def load_config(path, cwd):
    config = bc.load_yaml(str(path)) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("kits YAML must be a mapping")
    overlay = Path(cwd) / ".kogitsune.yaml"
    if overlay.is_file():
        project = bc.load_yaml(str(overlay))
        if not isinstance(project, dict):
            raise ValueError("project overlay must be a mapping")
        config = bc.deep_merge(config, project)
    return codex_config(config), overlay if overlay.is_file() else path


def save_preset(path, name, skills, model):
    """Rewrite only the Codex section, keeping Claude YAML and its comments intact."""
    text = path.read_text() if path.exists() else ""
    config = yaml.safe_load(text) or {}
    section = dict(config.get("codex") or {})
    kits = dict(section.get("kits") or {})
    kits[name] = {"skills": skills, **({"model": model} if model else {})}
    section["kits"] = kits
    codex_config({"codex": section})
    replacement = yaml.safe_dump({"codex": section}, sort_keys=False, allow_unicode=True)
    tree = yaml.compose(text)
    span = None
    if tree:
        for key, value in tree.value:
            if key.value == "codex":
                span = (key.start_mark.index, value.end_mark.index)
                break
    if span:
        new = text[:span[0]] + replacement + text[span[1]:]
    else:
        new = text + ("\n" if text and not text.endswith("\n") else "") + "\n" + replacement
    # A parse check and atomic replacement prevent partial YAML on interruption.
    yaml.safe_load(new)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".kogitsune-codex-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(new)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_selection(executable, cwd, overrides, selection):
    checked, _ = rpc.discover(executable, cwd, overrides)
    expected = {s["path"]: True for s in selection["selected"]}
    expected.update({s["path"]: False for s in selection["excluded"]})
    actual = {s["path"]: s["enabled"] for s in checked}
    if actual != expected:
        raise ValueError("Codex did not apply the skill selection exactly (or the inventory changed); "
                         "update Codex and retry. Nothing was launched.")


HELP = """kit codex — choose skills before starting a Codex CLI session

  kit codex                         choose a preset, then toggle skills (fzf)
  kit codex <name>                   launch a named kit
  kit codex tune <name>              tune a preset (ctrl-s saves it as a new kit)
  kit codex ls                       list presets and discovered skills
  kit codex show <name>              print a verified selection as JSON
  kit codex <name> --dry-run          print selection and argv; no model turn
  kit codex save <name> --skills a,b  save a kit; optional --model ID
  kit codex <name> -- CODEX_ARGS      forward interactive options and one prompt

Supported Codex options include --cd, --model, --config, --sandbox,
--ask-for-approval, --add-dir, --image (repeat for multiple images), --enable,
--disable, --search, --no-alt-screen and --approve-for-me. Remote sessions,
profiles, managed worktrees and Codex subcommands are not supported by this adapter.
System/admin/repo skills that are enabled stay on. MCP and plugin hooks follow
your normal Codex settings. Requires Codex app-server with skills/list (tested
on 0.154.0). No files in your Codex home are rewritten by Kogitsune.
"""


def main(argv=None):
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config-path", required=True)
    bootstrap.add_argument("arguments", nargs=argparse.REMAINDER)
    parsed = bootstrap.parse_args(argv)
    path = Path(parsed.config_path).expanduser().resolve()
    arguments = parsed.arguments
    if arguments and arguments[0] in {"help", "--help", "-h"}:
        print(HELP)
        return 0
    before, forwarded = arguments, []
    if "--" in arguments:
        index = arguments.index("--")
        before, forwarded = arguments[:index], arguments[index + 1:]
    parser = argparse.ArgumentParser(prog="kit codex", allow_abbrev=False)
    parser.add_argument("command", nargs="?", default="pick")
    parser.add_argument("name", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skills")
    parser.add_argument("--model")
    ns = parser.parse_args(before)
    command = ns.command
    if command not in RESERVED and ns.name:
        raise ValueError("put Codex arguments after -- (see 'kit codex help')")
    if command in {"show", "tune", "save"} and not ns.name:
        raise ValueError(f"kit codex {command} requires a kit name")
    if command in {"ls", "list", "pick", "__kits"} and ns.name:
        raise ValueError(f"kit codex {command} does not take a kit name")
    if command == "save" and (ns.dry_run or forwarded):
        raise ValueError("save does not accept --dry-run or forwarded Codex options")
    if command != "save" and (ns.skills is not None or ns.model is not None):
        raise ValueError("--skills/--model before -- are save options; forward Codex options after --")
    cwd, overrides, extra = launch_context(forwarded, None)
    section, save_path = load_config(path, cwd)
    if command == "__kits":
        print("\n".join(sorted(section["kits"])))
        return 0
    executable = shutil.which(os.environ.get("KOGITSUNE_CODEX", "codex"))
    if not executable:
        raise ValueError("missing dependency: codex (install the Codex CLI first)")
    executable = os.path.abspath(executable)  # keep relative executable paths valid with --cd
    skills, effective = rpc.discover(executable, cwd, overrides)
    if command in {"ls", "list"}:
        print("Codex kits: " + ", ".join(sorted(section["kits"])))
        print(f"{len(skills)} discovered skills ({sum(s['enabled'] for s in skills)} currently enabled)")
        for selector, s in zip(skill_selectors(skills), skills):
            state = "on" if s["enabled"] else "off"
            print(f"{selector}\t{state}\t{s['scope']}\t{s.get('description', '').replace(chr(10), ' ')}")
        return 0
    name = ns.name if command in {"show", "tune", "save"} else command
    if command == "save":
        if ns.skills is None:
            raise ValueError("save requires --skills (use --skills '' for an empty kit)")
        requested = [s.strip() for s in ns.skills.split(",") if s.strip()]
        select_skills(skills, requested, section["pinned"])
        save_preset(save_path, name, requested, ns.model)
        print(f"Saved Codex kit {name!r} to {save_path}")
        return 0
    picker = None
    if command in {"pick", "tune"}:
        picker = load_module("kogitsune_codex_picker", "codex-picker.py")
        if command == "pick":
            name = picker.pick_preset(section["kits"])
            if name is None:
                return 130
    preset = resolve_preset(section, name)
    selection = select_skills(skills, preset["skills"], section["pinned"])
    if picker:
        result = picker.pick_skills(skills, selection, skill_selectors(skills))
        if result is None:
            return 130
        requested, save_name = result
        selection = select_skills(skills, requested, section["pinned"])
        if save_name:
            save_preset(save_path, save_name, requested, preset["model"])
            print(f"Saved Codex kit {save_name!r} to {save_path}", file=sys.stderr)
    # A kit model must not beat either spelling of a forwarded model override.
    model_overridden = any(v.partition("=")[0].strip().strip("\"'") == "model" for v in overrides)
    if preset["model"] and not model_overridden:
        overrides.append("model=" + toml_value(preset["model"]))
    entries = skill_overrides(skills, selection, (effective.get("skills") or {}).get("config") or [])
    overrides.append("skills.config=" + toml_value(entries))
    verify_selection(executable, cwd, overrides, selection)
    argv = [executable]
    for override in overrides:
        argv.extend(["-c", override])
    argv.extend(extra)
    manifest = dict(selection, kit=name, cwd=cwd, verified=True,
                    selected_count=len(selection["selected"]), excluded_count=len(selection["excluded"]),
                    argv=argv)
    if ns.dry_run or command == "show":
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0
    print(f"🦊 Codex kit {name}: {manifest['selected_count']} skills enabled, "
          f"{manifest['excluded_count']} excluded", file=sys.stderr)
    os.chdir(cwd)
    os.execv(executable, argv)


if __name__ == "__main__":
    import signal

    def terminate(_signum, _frame):
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, terminate)
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, yaml.YAMLError, rpc.CodexError) as exc:
        print(f"kit codex: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
