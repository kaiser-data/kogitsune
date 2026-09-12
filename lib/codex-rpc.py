"""Short-lived Codex inventory client. Never creates threads or model turns."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading


class CodexError(RuntimeError):
    pass


class CodexRPC:
    def __init__(self, executable: str, cwd: str, overrides: list[str], timeout=30):
        self.timeout = timeout
        self.responses = queue.Queue()
        self.next_id = 0
        self.stderr = tempfile.TemporaryFile(mode="w+b")
        command = [executable, "app-server", "--listen", "stdio://"]
        for value in overrides:
            command.extend(["-c", value])
        try:
            self.process = subprocess.Popen(
                command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.stderr, text=True, encoding="utf-8",
            )
        except OSError as exc:
            self.stderr.close()
            raise CodexError(f"cannot start Codex: {exc}") from exc
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.responses.put(line)
        finally:
            self.responses.put(None)

    def _send(self, message):
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexError("Codex app server exited during discovery") from exc

    def request(self, method, params):
        import time

        self.next_id += 1
        self._send({"id": self.next_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                line = self.responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise CodexError(f"Codex timed out during {method}") from exc
            if line is None:
                self.stderr.seek(0)
                detail = self.stderr.read(4000).decode("utf-8", errors="replace").strip()
                raise CodexError(f"Codex app server exited during {method}: {detail}")
            try:
                reply = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CodexError("Codex returned invalid JSON during discovery") from exc
            if reply.get("id") != self.next_id:
                # Notifications are expected; unsolicited server requests are not.
                if "id" in reply and "method" in reply:
                    raise CodexError("Codex requested an interactive action during discovery")
                continue
            if "error" in reply:
                raise CodexError(f"Codex {method}: {reply['error'].get('message', 'RPC error')}")
            if "result" not in reply:
                raise CodexError(f"Codex returned no result for {method}")
            return reply["result"]

    def __enter__(self):
        try:
            self.info = self.request("initialize", {
                "clientInfo": {"name": "kogitsune", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            })
            self._send({"method": "initialized"})
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr.close()

    def __exit__(self, *_args):
        self.close()


def discover(executable: str, cwd: str, overrides: list[str]) -> tuple[list, dict]:
    with CodexRPC(executable, cwd, overrides) as client:
        config = client.request("config/read", {"cwd": cwd, "includeLayers": False})
        result = client.request("skills/list", {"cwds": [cwd], "forceReload": True})
    entries = result.get("data", [])
    if len(entries) != 1 or entries[0].get("cwd") != cwd:
        raise CodexError("Codex returned an unexpected working directory inventory")
    if entries[0].get("errors"):
        errors = entries[0]["errors"]
        raise CodexError("skill discovery failed: " + "; ".join(
            f"{e.get('path')}: {e.get('message')}" for e in errors))
    skills = entries[0].get("skills")
    if not isinstance(skills, list):
        raise CodexError("Codex returned no skill inventory")
    for skill in skills:
        if (not isinstance(skill, dict)
                or not isinstance(skill.get("name"), str)
                or not isinstance(skill.get("path"), str)
                or not Path(skill["path"]).is_absolute()
                or skill.get("scope") not in {"user", "repo", "system", "admin"}
                or not isinstance(skill.get("enabled"), bool)
                or not isinstance(skill.get("description", ""), str)):
            raise CodexError("Codex skill inventory is incompatible; update the Codex CLI")
    if len({s["path"] for s in skills}) != len(skills):
        raise CodexError("Codex returned duplicate skill paths; cannot verify selection unambiguously")
    return skills, config.get("config", {})


def inspect_runtime(executable: str, cwd: str, overrides: list[str]) -> dict:
    """Read metadata only. Never connect MCP servers, run hooks, or open a turn.

    Optional APIs vary by CLI version. Keep their failures as unknown instead of
    printing server errors, which may contain configuration or credential values.
    """
    snapshot = {}
    with CodexRPC(executable, cwd, overrides) as client:
        snapshot["codex_home"] = client.info.get("codexHome")
        snapshot["configuration"] = client.request(
            "config/read", {"cwd": cwd, "includeLayers": True})
        if not isinstance(snapshot["configuration"].get("config"), dict):
            raise CodexError("Codex returned no configuration for audit")
        for key, method, params in (
            ("requirements", "configRequirements/read", {}),
            ("hooks", "hooks/list", {"cwds": [cwd]}),
            ("plugins", "plugin/list", {"cwds": [cwd], "forceRefetch": False,
                                        "marketplaceKinds": ["local"]}),
        ):
            try:
                snapshot[key] = client.request(method, params)
            except CodexError:
                snapshot[key] = None
        hooks = snapshot["hooks"]
        if (not isinstance(hooks, dict) or not isinstance(hooks.get("data"), list)
                or len(hooks["data"]) != 1 or hooks["data"][0].get("cwd") != cwd
                or not isinstance(hooks["data"][0].get("hooks"), list)):
            snapshot["hooks"] = None
        if not isinstance(snapshot["plugins"], dict) or not isinstance(snapshot["plugins"].get("marketplaces"), list):
            snapshot["plugins"] = None
        if not isinstance(snapshot["requirements"], dict) or "requirements" not in snapshot["requirements"]:
            snapshot["requirements"] = None
        snapshot["plugin_details"] = {}
        for marketplace in (snapshot.get("plugins") or {}).get("marketplaces", []):
            if not marketplace.get("path"):
                continue
            for plugin in marketplace.get("plugins", []):
                if not plugin.get("installed"):
                    continue
                try:
                    detail = client.request("plugin/read", {
                        "marketplacePath": marketplace["path"], "pluginName": plugin["name"]})
                    snapshot["plugin_details"][plugin["id"]] = detail.get("plugin")
                except CodexError:
                    snapshot["plugin_details"][plugin["id"]] = None
    return snapshot
