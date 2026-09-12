"""fzf views for Codex presets and individual skills. No shell interpolation."""
import os
import shutil
import subprocess
import sys


def clean(text):
    return "".join(c if c.isprintable() else " " for c in str(text))


def fzf(rows, options):
    executable = shutil.which(os.environ.get("KOGITSUNE_FZF", "fzf"))
    if not executable:
        raise ValueError("missing dependency: fzf; use 'kit codex <name>' for a named kit")
    env = dict(os.environ, FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE="")
    result = subprocess.run(
        [executable, "--delimiter=\t", "--with-nth=2..", "--layout=reverse", "--sync", *options],
        input="\n".join(rows) + "\n", text=True, capture_output=True, env=env,
    )
    if result.returncode in (1, 130):
        return None
    if result.returncode:
        raise ValueError(f"Codex picker failed: {result.stderr.strip()}")
    return result.stdout


def pick_preset(kits):
    names = sorted(kits)
    rows = [f"{i}\t{name}" for i, name in enumerate(names)]
    result = fzf(rows, ["--prompt=codex kit › ", "--header=Choose a preset, then tune its skills"])
    if result is None:
        return None
    try:
        return names[int(result.split("\t")[0])]
    except (ValueError, IndexError) as exc:
        raise ValueError("invalid preset returned by fzf") from exc


def pick_skills(skills, selection, selectors):
    fixed = {s["path"] for s in selection["selected"] if s["reason"] in {"pinned", "retained"}}
    selected = {s["path"] for s in selection["selected"]}
    indexes = [i for i, s in enumerate(skills) if s["path"] not in fixed]
    rows = [f"{i}\t{clean(selectors[i])}\t{clean(skills[i].get('description', ''))}" for i in indexes]
    preselect = []
    for position, i in enumerate(indexes, 1):
        if skills[i]["path"] in selected:
            preselect.extend([f"pos({position})", "select"])
    bindings = ["--bind=tab:toggle+down,shift-tab:toggle+up,ctrl-a:select-all,ctrl-d:deselect-all"]
    # fzf normally accepts the focused item when the multi-selection is empty.
    # Mark that case explicitly so clearing a preset really produces an empty kit.
    for key in ("enter", "ctrl-s"):
        bindings.append(
            f'--bind={key}:transform:if [ "$FZF_SELECT_COUNT" -eq 0 ]; then '
            f"echo 'print({key})+print(__empty__)+accept'; else "
            f"echo 'print({key})+accept'; fi")
    if preselect:
        bindings.append("--bind=start:" + "+".join(preselect + ["first"]))
    header = (f"{len(fixed)} pinned/system/admin/project skills stay on · "
              "tab toggle · type to search · enter launch · ctrl-s save · esc cancel")
    if not rows:
        print(f"All {len(fixed)} skills are retained; no optional skills to select.", file=sys.stderr)
        return [], None
    result = fzf(rows, ["--multi", "--prompt=codex skills › ",
                        "--header=" + header, *bindings])
    if result is None:
        return None
    lines = result.splitlines()
    if not lines or lines[0] not in {"enter", "ctrl-s"}:
        raise ValueError("invalid selection returned by fzf")
    chosen = []
    for line in ([] if len(lines) > 1 and lines[1] == "__empty__" else lines[1:]):
        try:
            i = int(line.split("\t")[0])
        except ValueError as exc:
            raise ValueError("invalid skill returned by fzf") from exc
        if i not in indexes:
            raise ValueError("fzf returned a skill outside the catalog")
        chosen.append(selectors[i])
    name = None
    if lines[0] == "ctrl-s":
        try:
            # TTYs are not seekable; Python's buffered r+ mode rejects them.
            with open("/dev/tty", "w") as output, open("/dev/tty", "r") as terminal:
                output.write("Save Codex kit as: ")
                output.flush()
                name = terminal.readline().strip()
        except OSError as exc:
            raise ValueError("saving from the picker requires a terminal; use 'kit codex save'") from exc
        if not name:
            return None
    return chosen, name
