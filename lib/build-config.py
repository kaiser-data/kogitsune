#!/usr/bin/env python3
"""kogitsune — selection resolver / session-config builder.

Pure decision logic. Given a kit name (or explicit mcp/skills lists), it:
  * resolves kits (supporting `extends:` + `+name`/`-name` deltas),
  * validates references against the catalog (with fuzzy "did you mean" hints),
  * emits an --mcp-config JSON containing ONLY the chosen servers
    (pinned + selected, merged from ~/.claude/mcp-on-demand.json or inline `def:`),
  * prints a JSON **manifest** describing everything the launcher must materialize
    into the session mirror (skills to symlink, plugins to enable, imports, env).

The only side effect is writing the mcp-config file (skipped with --dry-run).
Everything else is a pure transform — see tests/test_build_config.py.

Extensibility: a catalog/pinned item is a dict with exactly one "kind" key.
Add a new capability by adding a kind to KINDS + a branch in resolve_item().
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys

# The typed-item registry. Each catalog/pinned entry carries exactly one of these.
KINDS = ("plugin", "skill", "dir", "prefix", "mcp", "import", "rules", "env")


def expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def skills_root() -> str:
    """User-skills directory; overridable via env for tests / alternate roots."""
    return expand(os.environ.get("KOGITSUNE_SKILLS_DIR", "~/.claude/skills"))


def rules_root() -> str:
    """User-rules directory; overridable via env for tests / alternate roots."""
    return expand(os.environ.get("KOGITSUNE_RULES_DIR", "~/.claude/rules"))


def load_yaml(path: str) -> dict:
    import yaml  # deferred so --help works without PyYAML
    with open(expand(path)) as fh:
        return yaml.safe_load(fh) or {}


def deep_merge(base: dict, over: dict) -> dict:
    """Recursively merge `over` onto `base` (project overlay > global config)."""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def kind_of(spec: dict) -> str | None:
    for k in KINDS:
        if k in spec:
            return k
    return None


# --- kit resolution (extends + +/- deltas) ---------------------------------

def _apply_delta(names: list[str], entries: list[str]) -> list[str]:
    """Apply a list that may contain bare names, +adds and -removes, order-preserving."""
    out = list(names)
    for e in entries or []:
        e = str(e)
        if e.startswith("-"):
            tgt = e[1:]
            out = [n for n in out if n != tgt]
        else:
            tgt = e[1:] if e.startswith("+") else e
            if tgt not in out:
                out.append(tgt)
    return out


def resolve_kit(name: str, kits: dict, _seen: tuple = ()) -> dict:
    """Return {'mcp': [...], 'skills': [...], 'model': str|None} for a kit.

    `model` is inherited from `extends` unless the kit sets its own.
    """
    if name not in kits:
        close = difflib.get_close_matches(name, list(kits), n=1)
        hint = f" (did you mean '{close[0]}'?)" if close else ""
        raise KeyError(f"unknown kit '{name}'{hint}. known: {', '.join(sorted(kits))}")
    if name in _seen:
        raise ValueError(f"circular `extends` involving '{name}'")
    spec = kits[name] or {}
    base_mcp: list[str] = []
    base_skills: list[str] = []
    base_model: str | None = None
    if spec.get("extends"):
        base = resolve_kit(spec["extends"], kits, _seen + (name,))
        base_mcp, base_skills, base_model = base["mcp"], base["skills"], base["model"]
    return {
        "mcp": _apply_delta(base_mcp, spec.get("mcp", [])),
        "skills": _apply_delta(base_skills, spec.get("skills", [])),
        "model": spec.get("model", base_model),
    }


# --- selection -> manifest --------------------------------------------------

def _suggest(name: str, options: list[str]) -> str:
    close = difflib.get_close_matches(name, options, n=1)
    return f" (did you mean '{close[0]}'?)" if close else ""


def resolve_item(name: str, spec: dict, mcp_servers: dict, warnings: list[str]) -> dict:
    """Resolve one catalog/pinned item into a manifest entry by its kind."""
    spec = spec or {}
    kind = kind_of(spec)
    entry = {"name": name, "kind": kind,
             "weight": int(spec.get("weight", 0) or 0), "tag": spec.get("tag", "")}
    if kind == "mcp" or (kind is None and name in mcp_servers):
        # mcp servers may be referenced by name (in mcp-on-demand.json) or inline def
        if "def" in spec:
            entry["server"] = spec["def"]
        elif name in mcp_servers:
            entry["server"] = mcp_servers[name]
        else:
            warnings.append(f"mcp '{name}' not in mcp-on-demand.json and no inline def"
                            f"{_suggest(name, list(mcp_servers))}")
            entry["server"] = None
        entry["kind"] = "mcp"
    elif kind == "plugin":
        entry["plugin"] = spec["plugin"]
        # gate_mcp: enable the plugin but keep its bundled MCP servers out of the
        # session (plugin .mcp.json bypasses --strict-mcp-config; the mirror drops it)
        entry["gate_mcp"] = bool(spec.get("gate_mcp"))
    elif kind == "skill":
        src = os.path.join(skills_root(), spec["skill"])
        entry["src"] = src
        if not os.path.isdir(src):
            warnings.append(f"skill '{name}' -> missing dir {src}")
    elif kind == "dir":
        pat = spec["dir"]
        # absolute / ~ / $VAR patterns used as-is; bare patterns resolve under skills root
        pat = expand(pat) if pat.startswith(("/", "~", "$")) else os.path.join(skills_root(), pat)
        matches = sorted(glob.glob(pat))
        entry["srcs"] = [m for m in matches if os.path.isdir(m)]
        if not entry["srcs"]:
            warnings.append(f"skill bundle '{name}' -> no dirs match {spec['dir']}")
    elif kind == "prefix":
        pat = os.path.join(skills_root(), f"{spec['prefix'].rstrip(':')}*")
        entry["srcs"] = sorted(d for d in glob.glob(pat) if os.path.isdir(d))
    elif kind == "import":
        path = expand(spec["import"])
        entry["path"] = path
        if not os.path.isfile(path):
            warnings.append(f"import '{name}' -> missing file {path}")
    elif kind == "rules":
        # a rules pack: a dir of *.md under ~/.claude/rules (or absolute/~/$VAR).
        # The mirror EXCLUDES the auto-loaded rules/ dir, so selected packs ride in
        # as explicit session-CLAUDE.md imports — loaded when chosen, absent otherwise.
        pat = spec["rules"]
        base = expand(pat) if pat.startswith(("/", "~", "$")) else os.path.join(rules_root(), pat)
        entry["paths"] = sorted(glob.glob(os.path.join(base, "*.md")))
        if not entry["paths"]:
            warnings.append(f"rules pack '{name}' -> no *.md files under {base}")
    elif kind == "env":
        entry["env"] = spec["env"]
    else:
        warnings.append(f"item '{name}' has no recognized kind ({', '.join(KINDS)})")
    return entry


def build(config: dict, mcp_servers: dict, *, kit: str | None,
          mcp_sel: list[str] | None, skills_sel: list[str] | None,
          model: str | None = None) -> dict:
    """Resolve a selection into a full manifest. Pure.

    `model` overrides any kit-declared model (used by the picker's live override);
    falls back to the resolved kit's model, then to the config-level default.
    """
    warnings: list[str] = []
    catalog = config.get("catalog", {}) or {}
    cat_mcp = catalog.get("mcp", {}) or {}
    cat_skills = catalog.get("skills", {}) or {}
    kits = config.get("kits", {}) or {}
    pinned = config.get("pinned", {}) or {}

    kit_model: str | None = None
    if kit is not None:
        sel = resolve_kit(kit, kits)
        mcp_sel, skills_sel = sel["mcp"], sel["skills"]
        kit_model = sel["model"]
    mcp_sel = mcp_sel or []
    skills_sel = skills_sel or []
    resolved_model = model or kit_model or config.get("model")

    # validate references
    for n in mcp_sel:
        if n not in cat_mcp:
            warnings.append(f"unknown mcp '{n}'{_suggest(n, list(cat_mcp))}")
    for n in skills_sel:
        if n not in cat_skills:
            warnings.append(f"unknown skill '{n}'{_suggest(n, list(cat_skills))}")

    items, plugins, skill_srcs, imports, env = [], {}, [], [], {}
    plugin_mcp_exclude: list[str] = []

    # pinned items always ride along
    pinned_entries = []
    for name, spec in pinned.items():
        e = resolve_item(name, spec, mcp_servers, warnings)
        pinned_entries.append(e)
        _fold(e, plugins, skill_srcs, imports, env, plugin_mcp_exclude)

    # selected catalog items
    for n in mcp_sel:
        e = resolve_item(n, {"mcp": n, **(cat_mcp.get(n) or {})}, mcp_servers, warnings)
        items.append(e)
        _fold(e, plugins, skill_srcs, imports, env, plugin_mcp_exclude)
    for n in skills_sel:
        e = resolve_item(n, cat_skills.get(n) or {}, mcp_servers, warnings)
        items.append(e)
        _fold(e, plugins, skill_srcs, imports, env, plugin_mcp_exclude)

    # assemble the strict --mcp-config (pinned mcp + selected mcp)
    mcp_config = {"mcpServers": {}}
    for e in pinned_entries + items:
        if e["kind"] == "mcp" and e.get("server"):
            mcp_config["mcpServers"][e["name"]] = e["server"]

    weight = sum(int(e.get("weight", 0) or 0) for e in items)
    return {
        "kit": kit,
        "model": resolved_model,
        "pinned": pinned_entries,
        "items": items,
        "plugins": plugins,
        "skills": skill_srcs,
        "imports": imports,
        "env": env,
        "plugin_mcp_exclude": plugin_mcp_exclude,
        "mcp_config": mcp_config,
        "weight": weight,
        "warnings": warnings,
    }


def _fold(e: dict, plugins: dict, skill_srcs: list, imports: list, env: dict,
          plugin_mcp_exclude: list) -> None:
    """Accumulate a resolved item into the flat manifest buckets."""
    if e["kind"] == "plugin" and e.get("plugin"):
        plugins[e["plugin"]] = True
        if e.get("gate_mcp") and e["plugin"] not in plugin_mcp_exclude:
            plugin_mcp_exclude.append(e["plugin"])
    elif e["kind"] == "skill" and e.get("src"):
        skill_srcs.append(e["src"])
    elif e["kind"] in ("dir", "prefix"):
        skill_srcs.extend(e.get("srcs", []))
    elif e["kind"] == "import" and e.get("path"):
        imports.append(e["path"])
    elif e["kind"] == "rules":
        imports.extend(e.get("paths", []))
    elif e["kind"] == "env":
        env.update(e.get("env", {}))


# --- save a kit (comment-preserving, line-based) ----------------------------

def render_kit_entry(name: str, mcp: list[str], skills: list[str],
                     model: str | None = None) -> str:
    model_part = f"model: {model}, " if model else ""
    return (f"  {name}: {{ {model_part}mcp: [{', '.join(mcp)}], "
            f"skills: [{', '.join(skills)}] }}")


def save_kit_text(text: str, name: str, mcp: list[str], skills: list[str],
                  model: str | None = None) -> str:
    """Insert/replace a kit under the `kits:` block, preserving comments & order."""
    entry = render_kit_entry(name, mcp, skills, model)
    lines = text.splitlines()
    kits_idx = next((i for i, l in enumerate(lines) if re.match(r"^kits:\s*$", l)), None)
    if kits_idx is None:
        tail = lines + ["", "kits:", entry]
        return "\n".join(tail) + "\n"
    # replace an existing same-name entry inside the block
    for j in range(kits_idx + 1, len(lines)):
        l = lines[j]
        if l.strip() and not l.startswith((" ", "\t")):
            break  # dedented out of the block
        if re.match(rf"^\s+{re.escape(name)}:", l):
            lines[j] = entry
            return "\n".join(lines) + "\n"
    lines.insert(kits_idx + 1, entry)
    return "\n".join(lines) + "\n"


def remove_kit_text(text: str, name: str) -> tuple[str, bool]:
    """Remove a kit line from the `kits:` block. Returns (new_text, removed?)."""
    lines = text.splitlines()
    kits_idx = next((i for i, l in enumerate(lines) if re.match(r"^kits:\s*$", l)), None)
    if kits_idx is None:
        return text, False
    for j in range(kits_idx + 1, len(lines)):
        l = lines[j]
        if l.strip() and not l.startswith((" ", "\t")):
            break
        if re.match(rf"^\s+{re.escape(name)}:", l):
            del lines[j]
            return "\n".join(lines) + "\n", True
    return text, False


# --- CLI --------------------------------------------------------------------

def _parse_args(argv):
    p = argparse.ArgumentParser(description="kogitsune session-config builder")
    p.add_argument("kit", nargs="?", help="kit name (omit to use --mcp/--skills)")
    p.add_argument("--config", default="kits.yaml")
    p.add_argument("--overlay", help="optional project overlay yaml merged over --config")
    p.add_argument("--mcp-on-demand", default="~/.claude/mcp-on-demand.json")
    p.add_argument("--mcp", default="", help="comma/space list (when no kit)")
    p.add_argument("--skills", default="", help="comma/space list (when no kit)")
    p.add_argument("--model", default="", help="model override (e.g. opus|sonnet|haiku)")
    p.add_argument("--out-dir", help="dir to write mcp.json into (default: a temp dir)")
    p.add_argument("--dry-run", action="store_true", help="print manifest, write nothing")
    p.add_argument("--list", action="store_true",
                   help="print kits + catalog as JSON (for `kit ls` / the picker) and exit")
    p.add_argument("--save", metavar="NAME",
                   help="save the --mcp/--skills selection as a named kit in --config")
    p.add_argument("--rm", metavar="NAME", help="remove a named kit from --config")
    return p.parse_args(argv)


def _split(s: str) -> list[str]:
    return [x for x in s.replace(",", " ").split() if x]


def main(argv=None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])

    if ns.save:
        path = expand(ns.config)
        text = open(path).read() if os.path.isfile(path) else ""
        new = save_kit_text(text, ns.save, _split(ns.mcp), _split(ns.skills),
                            ns.model or None)
        with open(path, "w") as fh:
            fh.write(new)
        sys.stderr.write(f"saved kit '{ns.save}' to {path}\n")
        return 0

    if ns.rm:
        path = expand(ns.config)
        text = open(path).read() if os.path.isfile(path) else ""
        new, removed = remove_kit_text(text, ns.rm)
        if not removed:
            sys.stderr.write(f"no kit '{ns.rm}' found in {path}\n")
            return 1
        with open(path, "w") as fh:
            fh.write(new)
        sys.stderr.write(f"removed kit '{ns.rm}' from {path}\n")
        return 0

    config = load_yaml(ns.config)
    if ns.overlay and os.path.isfile(expand(ns.overlay)):
        config = deep_merge(config, load_yaml(ns.overlay))
    mcp_servers = {}
    od = expand(ns.mcp_on_demand)
    if os.path.isfile(od):
        with open(od) as fh:
            mcp_servers = (json.load(fh) or {}).get("mcpServers", {})

    if ns.list:
        cat = config.get("catalog", {}) or {}
        # resolve each kit so the picker can show its true weight (extends/+/- applied)
        kit_info = {}
        for kname in (config.get("kits", {}) or {}):
            try:
                m = build(config, mcp_servers, kit=kname, mcp_sel=None, skills_sel=None)
                kit_info[kname] = {
                    "weight": m["weight"],
                    "model": m["model"],
                    "mcp": [i["name"] for i in m["items"] if i["kind"] == "mcp"],
                    "skills": [i["name"] for i in m["items"] if i["kind"] != "mcp"],
                }
            except Exception:
                kit_info[kname] = {"weight": 0, "model": None, "mcp": [], "skills": []}
        json.dump({"kits": config.get("kits", {}) or {},
                   "kit_info": kit_info,
                   "mcp": cat.get("mcp", {}) or {},
                   "skills": cat.get("skills", {}) or {},
                   "pinned": list((config.get("pinned", {}) or {}).keys())},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    manifest = build(config, mcp_servers, kit=ns.kit,
                     mcp_sel=_split(ns.mcp), skills_sel=_split(ns.skills),
                     model=ns.model or None)

    if not ns.dry_run:
        out_dir = expand(ns.out_dir) if ns.out_dir else None
        if out_dir is None:
            import tempfile
            out_dir = tempfile.mkdtemp(prefix="kogitsune.")
        os.makedirs(out_dir, exist_ok=True)
        mcp_path = os.path.join(out_dir, "mcp.json")
        with open(mcp_path, "w") as fh:
            json.dump(manifest["mcp_config"], fh, indent=2)
        manifest["mcp_config_path"] = mcp_path

    json.dump(manifest, sys.stdout, indent=2)
    sys.stdout.write("\n")
    for w in manifest["warnings"]:
        sys.stderr.write(f"warning: {w}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
