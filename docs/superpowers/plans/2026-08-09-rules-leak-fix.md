# Rules Leak Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ecc-rules-common` a genuine kit toggle by moving the ECC rules packs off the harness's ancestor-scan path, and prove it with a measurement.

**Architecture:** Rules packs currently live in `~/.claude/rules/`. The harness walks up from the working directory and auto-loads any `<ancestor>/.claude/rules/**`, so they reach every session regardless of the mirror. Moving them to `~/.claude-rules/` (verified not scanned) removes them from that path. kogitsune learns where they went via a new `rules_root:` key in `kits.yaml`, and `kit doctor` detects the un-migrated state and prints the exact fix.

**Tech Stack:** Python 3 (stdlib only, no new deps), bash 3.2-compatible shell, pytest, shellcheck.

## Global Constraints

- **No new runtime dependencies.** stdlib Python and POSIX shell only.
- **bash 3.2 compatible** — no `mapfile`, no associative arrays; CI runs bash 3.2 on macOS.
- **Pure resolver.** `build-config.py` transforms input to a manifest; its only side effect is writing the mcp-config file. Do not read the environment from inside `resolve_item()`.
- **Precedence is exactly** `config > env > default`, default `~/.claude/rules`.
- **Destination is `~/.claude-rules`** — verified unscanned. Any replacement must not be named `.claude` nor be nested inside one.
- **This fix is partial.** ~719 tokens still leak (`guardrails.md` ~380, the two `CLAUDE.md` files ~339). No doc or output may imply the leak is closed.
- **`make check` must stay green:** 102 pytest + 92 launcher + 26 decider, shellcheck clean.
- Spec: `docs/superpowers/specs/2026-08-09-rules-leak-fix-design.md`

---

### Task 1: `rules_root:` config key

Teaches the resolver where rules packs live, with config beating env so a committed `kits.yaml` is portable.

**Files:**
- Modify: `lib/build-config.py:41-43` (`rules_root`), `:159` (`resolve_item` signature), `:207` (rules branch), `:259,265,269` (call sites in `build`)
- Create: `tests/test_rules_root.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `DEFAULT_RULES_ROOT: str = "~/.claude/rules"`
  - `rules_root(config: dict | None = None) -> str`
  - `resolve_item(name: str, spec: dict, mcp_servers: dict, warnings: list[str], rules_base: str | None = None) -> dict`
  - `build(...)` manifest gains no new key in this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rules_root.py`:

```python
"""Tests for rules_root precedence — config > env > default.

Config must beat env so a committed kits.yaml resolves the same paths on a
teammate's machine without them setting anything in their shell.
"""
import os


def test_default_when_nothing_is_set(buildcfg, monkeypatch):
    monkeypatch.delenv("KOGITSUNE_RULES_DIR", raising=False)
    assert buildcfg.rules_root() == buildcfg.expand(buildcfg.DEFAULT_RULES_ROOT)


def test_env_overrides_the_default(buildcfg, monkeypatch):
    monkeypatch.setenv("KOGITSUNE_RULES_DIR", "/env/rules")
    assert buildcfg.rules_root() == "/env/rules"


def test_config_beats_env(buildcfg, monkeypatch):
    monkeypatch.setenv("KOGITSUNE_RULES_DIR", "/env/rules")
    assert buildcfg.rules_root({"rules_root": "/cfg/rules"}) == "/cfg/rules"


def test_config_value_is_expanded(buildcfg, monkeypatch):
    monkeypatch.delenv("KOGITSUNE_RULES_DIR", raising=False)
    assert buildcfg.rules_root({"rules_root": "~/x"}) == os.path.expanduser("~/x")


def test_empty_config_value_falls_through_to_env(buildcfg, monkeypatch):
    monkeypatch.setenv("KOGITSUNE_RULES_DIR", "/env/rules")
    assert buildcfg.rules_root({"rules_root": ""}) == "/env/rules"


def test_build_resolves_a_rules_pack_from_the_configured_root(
        buildcfg, config, servers, tmp_path, monkeypatch):
    # env points somewhere real (conftest sets it); config must win anyway
    pack = tmp_path / "ecc-common"
    pack.mkdir()
    (pack / "a.md").write_text("# a")
    cfg = dict(config)
    cfg["rules_root"] = str(tmp_path)
    m = buildcfg.build(cfg, servers, kit=None, mcp_sel=[], skills_sel=["ecc-rules"])
    assert str(pack / "a.md") in m["imports"]
    assert m["warnings"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_rules_root.py -q`
Expected: FAIL — `AttributeError: module 'buildcfg' has no attribute 'DEFAULT_RULES_ROOT'`

- [ ] **Step 3: Add the constant and widen `rules_root`**

In `lib/build-config.py`, replace lines 41-43:

```python
DEFAULT_RULES_ROOT = "~/.claude/rules"


def rules_root(config: dict | None = None) -> str:
    """User-rules directory. Precedence: config `rules_root:` > env > default.

    Config beats env so a committed kits.yaml is portable: a teammate who clones it
    resolves the same paths without setting anything in their shell. The env var
    remains for tests and CI, which need to redirect the root per-process.
    """
    configured = (config or {}).get("rules_root")
    if configured:
        return expand(str(configured))
    return expand(os.environ.get("KOGITSUNE_RULES_DIR", DEFAULT_RULES_ROOT))
```

- [ ] **Step 4: Thread the root into `resolve_item`**

In `lib/build-config.py`, change the signature at line 159:

```python
def resolve_item(name: str, spec: dict, mcp_servers: dict, warnings: list[str],
                 rules_base: str | None = None) -> dict:
```

and in the `rules` branch replace the `base = ...` line (line 207):

```python
        base = (expand(pat) if pat.startswith(("/", "~", "$"))
                else os.path.join(rules_base or rules_root(), pat))
```

- [ ] **Step 5: Pass the root from `build`**

In `lib/build-config.py`, inside `build()`, add immediately after `pinned = config.get("pinned", {}) or {}`:

```python
    rules_base = rules_root(config)
```

Then add `rules_base` to all three `resolve_item` calls (lines ~259, ~265, ~269):

```python
        e = resolve_item(name, spec, mcp_servers, warnings, rules_base)
```
```python
        e = resolve_item(n, {"mcp": n, **(cat_mcp.get(n) or {})}, mcp_servers,
                         warnings, rules_base)
```
```python
        e = resolve_item(n, cat_skills.get(n) or {}, mcp_servers, warnings, rules_base)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_rules_root.py -q`
Expected: PASS, 6 passed

- [ ] **Step 7: Run the full suite for regressions**

Run: `make check`
Expected: `108 passed` (102 + 6), launcher 92 passed, decider 26 passed, shellcheck silent

- [ ] **Step 8: Commit**

```bash
git add lib/build-config.py tests/test_rules_root.py
git commit -m "feat: rules_root config key so rules packs can live off the ancestor path

Precedence config > env > default. Config beats env so a committed
kits.yaml resolves identically on another machine."
```

---

### Task 2: Migration detection in `kit doctor`

Detects rules packs still sitting inside a `.claude` directory and prints the exact fix. Generalised: the condition is "path contains a `.claude` component", not "named ecc".

**Files:**
- Modify: `lib/leak-scan.py` (add two functions + a CLI flag), `lib/build-config.py` (emit `rules_root` in `--list`), `bin/kit` (doctor block)
- Modify: `tests/test_leak_scan.py` (append), `tests/test_launcher.sh` (append)

**Interfaces:**
- Consumes: `rules_root(config)` from Task 1.
- Produces:
  - `leak_scan.leaks_by_location(path: str) -> bool`
  - `leak_scan.migration_hint(rules_path: str, suggested: str = SUGGESTED_ROOT) -> str` — returns `""` when already clear
  - `leak_scan.SUGGESTED_ROOT: str = "~/.claude-rules"`
  - `leak-scan.py --rules-root PATH` CLI flag
  - `build-config.py --list` JSON gains top-level `"rules_root"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leak_scan.py`:

```python
# ---- migration detection ----------------------------------------------------

def test_leaks_by_location_true_inside_a_dot_claude_dir(leakscan):
    assert leakscan.leaks_by_location("/Users/x/.claude/rules")


def test_leaks_by_location_true_when_nested_deeper(leakscan):
    assert leakscan.leaks_by_location("/Users/x/.claude/rules/ecc/common")


def test_leaks_by_location_false_for_a_sibling_dir(leakscan):
    # verified empirically 2026-08-09: a dir not named .claude is not scanned
    assert not leakscan.leaks_by_location("/Users/x/.claude-rules")


def test_leaks_by_location_false_for_an_unrelated_path(leakscan):
    assert not leakscan.leaks_by_location("/opt/rules")


def test_migration_hint_names_the_source_and_destination(leakscan):
    out = leakscan.migration_hint("/Users/x/.claude/rules")
    assert "/Users/x/.claude/rules" in out
    assert leakscan.SUGGESTED_ROOT in out
    assert "rules_root:" in out


def test_migration_hint_is_empty_when_already_migrated(leakscan):
    assert leakscan.migration_hint("/Users/x/.claude-rules") == ""


def test_migration_hint_keeps_guardrails_in_place(leakscan):
    # moving guardrails.md too would break @rules/guardrails.md in the global
    # CLAUDE.md and silently drop guardrails from every non-kit session
    assert "guardrails.md" in leakscan.migration_hint("/Users/x/.claude/rules")


def test_residual_is_still_reported_after_migration(leakscan, tmp_path):
    # the post-migration state: packs moved out, but an ancestor CLAUDE.md and a
    # guardrails-only rules dir remain. The scan must NOT report zero — claiming
    # victory here would hide ~719 tok that this fix cannot remove.
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "guardrails.md").write_text("g" * 1500)
    (tmp_path / ".claude" / "CLAUDE.md").write_text("c" * 700)
    proj = tmp_path / "proj"
    proj.mkdir()
    hits = leakscan.scan(str(proj), stop=str(tmp_path))
    assert leakscan.total_tokens(hits) > 0
    assert leakscan.render(hits) != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_leak_scan.py -q`
Expected: FAIL — `AttributeError: module 'leakscan' has no attribute 'leaks_by_location'`

- [ ] **Step 3: Implement in `lib/leak-scan.py`**

Add after the `RULES_DIR` constant:

```python
# Where rules packs should live instead: a sibling of ~/.claude, verified 2026-08-09
# not to be picked up by the ancestor walk (positive control in the same run: a
# .claude/rules canary leaked, a .claude-rules canary did not).
SUGGESTED_ROOT = "~/.claude-rules"
```

Add before `_parse_args`:

```python
def leaks_by_location(path: str) -> bool:
    """True when `path` sits inside a directory named `.claude`. Pure.

    That is the whole condition: the harness auto-loads `<ancestor>/.claude/rules/**`
    from the working directory's ancestors, so a rules root anywhere inside a `.claude`
    dir reaches every session no matter what the mirror excludes.
    """
    return DOT_CLAUDE in os.path.abspath(expanduser(path)).split(os.sep)


def migration_hint(rules_path: str, suggested: str = SUGGESTED_ROOT) -> str:
    """Instruction to move rules packs off the ancestor path, or "" if already clear.

    Deliberately moves only the pack subdirectories, not `guardrails.md`: the global
    CLAUDE.md refers to it as `@rules/guardrails.md`, so moving it would silently drop
    guardrails from every non-kit session — a worse failure than the leak.
    """
    if not leaks_by_location(rules_path):
        return ""
    src = os.path.abspath(expanduser(rules_path))
    return "\n".join([
        f"rules packs under {src} are auto-loaded from cwd's ancestors —",
        "no kit can gate them. Move the packs (leave guardrails.md where it is):",
        f"    mkdir -p {suggested}",
        f"    mv {os.path.join(src, 'ecc')} {suggested}/",
        f"then add to kits.yaml:    rules_root: \"{suggested}\"",
        "then verify:              kit measure --proxy lean",
    ])
```

Add the import at the top of the file, next to `import os`:

```python
from os.path import expanduser
```

- [ ] **Step 4: Add the CLI flag**

In `_parse_args`, add before the `--json` argument:

```python
    p.add_argument("--rules-root", help="configured rules root; checked for migration")
```

In `main`, replace the body after `hits = scan(ns.cwd, ns.stop)`:

```python
    hint = migration_hint(ns.rules_root) if ns.rules_root else ""
    if ns.json:
        print(json.dumps({"total_tokens": total_tokens(hits), "hits": hits,
                          "migration": hint}))
    else:
        print(render(hits) or "✓ nothing bypasses the mirror from here")
        if hint:
            print()
            print(hint)
    return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_leak_scan.py -q`
Expected: PASS, 19 passed

- [ ] **Step 6: Emit `rules_root` from `--list`**

In `lib/build-config.py`, find the `--list` branch in `main()` (it builds a dict with `kits`, `mcp`, `pinned`, `skills`, `kit_info`). Add one key to that dict:

```python
                "rules_root": rules_root(config),
```

- [ ] **Step 7: Wire doctor to pass it**

In `bin/kit`, replace the mirror-bypass block in `cmd_doctor`:

```bash
  echo "  mirror bypass (context loaded from cwd's ancestors):"
  if [[ -n "$PY" ]]; then
    local rr leak
    rr="$(bc --list 2>/dev/null | jq -r '.rules_root // empty' 2>/dev/null || true)"
    leak="$("$PY" "$LIB/leak-scan.py" ${rr:+--rules-root "$rr"} 2>/dev/null || true)"
    if [[ -z "$leak" ]]; then echo "    • could not scan"
    else printf '%s\n' "$leak" | sed 's/^/    /'; fi
  else echo "    • needs python3"; fi
```

- [ ] **Step 8: Add a launcher test**

Append to `tests/test_launcher.sh`, immediately before the `== completion helpers ==` section:

```bash
echo "== doctor: rules migration hint =="
# fixture rules live under a plain dir, so no hint; a .claude path must produce one
out="$("$ROOT/bin/kit" doctor 2>/dev/null)"
echo "$out" | grep -q "mirror bypass" && ok "doctor still reports mirror bypass" || no "bypass gone: $out"
hint="$("$PY_BIN" "$ROOT/lib/leak-scan.py" --rules-root "$HC/.claude/rules" 2>/dev/null)"
echo "$hint" | grep -q "rules_root:" && ok "migration hint printed for a .claude rules root" || no "no hint: $hint"
hint="$("$PY_BIN" "$ROOT/lib/leak-scan.py" --rules-root "$HC/plain-rules" 2>/dev/null)"
echo "$hint" | grep -q "rules_root:" && no "spurious hint for a clean root" || ok "no hint for a non-.claude rules root"
clean_tmp
```

Add near the other exports at the top of `tests/test_launcher.sh` (after `export TMPDIR="$TMP"`):

```bash
PY_BIN="$(command -v python3)"
```

- [ ] **Step 9: Run the full suite**

Run: `make check`
Expected: `116 passed` (108 + 8), launcher `95 passed`, decider 26 passed, shellcheck silent

- [ ] **Step 10: Commit**

```bash
git add lib/leak-scan.py lib/build-config.py bin/kit tests/test_leak_scan.py tests/test_launcher.sh
git commit -m "feat: kit doctor detects un-migrated rules packs and prints the fix

Condition is 'path contains a .claude component', not a hardcoded pack name.
Hint deliberately leaves guardrails.md in place."
```

---

### Task 3: Documentation and the shipped example

**Files:**
- Modify: `examples/kits.example.yaml`, `README.md`, `docs/FINDINGS-2026-08-09-payload-attribution.md`

**Interfaces:**
- Consumes: `rules_root:` key from Task 1; migration hint wording from Task 2.
- Produces: no code.

- [ ] **Step 1: Document `rules_root:` in the example config**

In `examples/kits.example.yaml`, add immediately above the `pinned:` block:

```yaml
# Where rules packs live. Set this to a directory that is NOT inside any `.claude`
# dir: the harness auto-loads `<ancestor>/.claude/rules/**` from the working
# directory's ancestors, so packs kept under ~/.claude/rules reach every session and
# no kit can gate them. `kit doctor` detects this and prints the move.
# Precedence: this key > $KOGITSUNE_RULES_DIR > ~/.claude/rules
rules_root: "~/.claude-rules"
```

- [ ] **Step 2: Document it in the README**

In `README.md`, in the `## Defining a kit` section, replace the `rules` bullet under "Two gating features close context leaks…" with:

```markdown
- **`rules` packs** — the harness auto-loads `<config>/rules/**` into every session, so the
  mirror excludes `rules/` and selected packs ride in as explicit session-CLAUDE.md imports.
  It *also* walks up from the working directory and loads `<ancestor>/.claude/rules/**`,
  which no mirror can reach — so keep packs outside any `.claude` dir and point
  **`rules_root:`** at them. `kit doctor` detects the un-migrated case and prints the move.
```

- [ ] **Step 3: Mark the findings section partially fixed**

In `docs/FINDINGS-2026-08-09-payload-attribution.md`, change the `## Open, in priority order` item 1 to:

```markdown
1. ~~**Fix the cwd leak**~~ (§2) — **partially fixed.** Moving the ECC packs to a
   `rules_root:` outside `.claude` removes ~4,093 tok. **~719 tok still leak** and are not
   fixable this way: `guardrails.md` (~380, wanted anyway, but double-loaded in kit
   sessions) and the two `CLAUDE.md` files (~339, only removable by moving projects off
   `$HOME`). `kit doctor` keeps reporting the residual.
```

- [ ] **Step 4: Verify no doc claims a full fix**

Run: `grep -rn "leak" README.md docs/FINDINGS-2026-08-09-payload-attribution.md examples/kits.example.yaml | grep -iv "residual\|partial\|still\|no kit can gate\|reach every session"`
Expected: no line asserting the leak is closed. Fix any that do.

- [ ] **Step 5: Commit**

```bash
git add examples/kits.example.yaml README.md docs/FINDINGS-2026-08-09-payload-attribution.md
git commit -m "docs: rules_root and the ancestor leak, stated as a partial fix"
```

---

### Task 4: Perform the migration and prove it with a measurement

The acceptance test is a number, not a green suite. This task moves user-owned files; do each step and check the output before the next.

**Files:**
- Modify: `kits.yaml` (gitignored — the live config)
- Move: `~/.claude/rules/ecc/` → `~/.claude-rules/ecc/`

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: no code.

- [ ] **Step 1: Record the before number**

Run: `./bin/kit measure --proxy lean 2>&1 | sed -n '3p'`
Expected: a line reading roughly `41 tools · … total ~22,091 tok` (tool count and total will differ if the harness axis changed). **Write the total down** — Step 6 compares against it.

- [ ] **Step 2: Confirm doctor asks for the migration**

Run: `./bin/kit doctor 2>&1 | tail -15`
Expected: the mirror-bypass block, followed by the migration hint naming `~/.claude/rules/ecc` and `~/.claude-rules`.

- [ ] **Step 3: Move the packs**

```bash
mkdir -p ~/.claude-rules
mv ~/.claude/rules/ecc ~/.claude-rules/
ls ~/.claude/rules ~/.claude-rules
```

Expected: `~/.claude/rules` now contains only `guardrails.md`; `~/.claude-rules` contains `ecc`.

- [ ] **Step 4: Point the live config at the new root**

Add to the top of `kits.yaml` (above `pinned:`):

```yaml
rules_root: "~/.claude-rules"
```

- [ ] **Step 5: Verify the packs still resolve**

Run: `./bin/kit show ecc 2>&1 | head -20`
Expected: resolves with **no** `rules pack ... -> no *.md files` warning. If it warns, `rules_root:` is wrong — fix before continuing.

- [ ] **Step 6: Measure the after number — the acceptance test**

Run: `./bin/kit measure --proxy lean 2>&1 | sed -n '3p'`
Expected: total drops by ≈4,093 from Step 1 (≈22,091 → ≈18,000, ± a few hundred of probe noise).
**If the total did not move, the fix did not work** — stop and diagnose; do not proceed.

- [ ] **Step 7: Confirm the residual is reported, not hidden**

Run: `./bin/kit doctor 2>&1 | tail -12`
Expected: the migration hint is **gone**; the bypass block still reports ~719 tok (`guardrails.md` plus the two `CLAUDE.md` files). It must not report zero.

- [ ] **Step 8: Full suite**

Run: `make check`
Expected: 116 pytest, 95 launcher, 26 decider, shellcheck silent.

- [ ] **Step 9: Commit the tracked changes**

`kits.yaml` is gitignored, so only docs/code are committed here.

```bash
git status --short
git add -A docs/ lib/ bin/ tests/ examples/ README.md
git commit -m "fix: close the ancestor rules leak for ECC packs

Measured on lean: ~22.1K -> ~18.0K tokens per session. Partial by design:
~719 tok still reach every session (guardrails.md, the two CLAUDE.md files)."
```

---

## Rollback

If Step 6 shows no change, or anything downstream breaks:

```bash
mv ~/.claude-rules/ecc ~/.claude/rules/
# remove the `rules_root:` line from kits.yaml
./bin/kit show ecc     # confirm packs resolve again
```

The code changes are inert without the move: `rules_root` defaults to `~/.claude/rules`, and the migration hint is advisory only.
