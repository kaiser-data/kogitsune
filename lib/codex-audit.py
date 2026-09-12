"""Read-only Codex access report. Allowlist metadata; never serialize raw config.

No credential stores or instruction contents are opened. Hook commands, server
URLs, headers, environment values, prompts, and arbitrary API errors are omitted.
"""
from __future__ import annotations

import os
from pathlib import Path
import re


UNKNOWN = "unknown"
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
SECRET_NAME = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|PRIVATE_KEY|ACCESS_KEY|"
    r"AUTH|DATABASE_URL|DB_URL|DSN|CONNECTION_STRING", re.I)


def mapping(value):
    return value if isinstance(value, dict) else {}


def strings(value):
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def text(value, default=UNKNOWN):
    # Prevent terminal escapes in metadata supplied by plugins or config files.
    return "".join(c if c.isprintable() else " " for c in value) if isinstance(value, str) else default


def choice(value, allowed):
    return value if value in allowed else UNKNOWN


def boolean(value):
    return value if isinstance(value, bool) else UNKNOWN


def env_names(value):
    return sorted(n for n in value if isinstance(n, str) and ENV_NAME.fullmatch(n))


def file_info(path):
    try:
        return "present" if path.is_file() else "absent"
    except OSError:
        return UNKNOWN


def instructions(config, cwd, codex_home):
    """List candidates in documented precedence order; don't claim prompt assembly."""
    markers = strings(config.get("project_root_markers")) if isinstance(
        config.get("project_root_markers"), list) else [".git"]
    markers = [m for m in markers if Path(m).name == m and m not in {".", ".."}]
    root = cwd
    for parent in [cwd, *cwd.parents]:
        if any((parent / marker).exists() for marker in markers):
            root = parent
            break
    # Construct the root-to-cwd chain explicitly to handle Git worktree .git files.
    directories = [root]
    if root != cwd:
        relative = cwd.relative_to(root)
        for part in relative.parts:
            directories.append(directories[-1] / part)
    fallback = [n for n in strings(config.get("project_doc_fallback_filenames"))
                if Path(n).name == n and n not in {".", ".."}]
    candidates = []
    for directory, scope, names in [
        (codex_home, "user", ["AGENTS.override.md", "AGENTS.md"]),
        *((p, "project", ["AGENTS.override.md", "AGENTS.md", *fallback]) for p in directories),
    ]:
        if directory is None:
            continue
        for name in names:
            path = directory / name
            try:
                if not path.is_file() or not path.stat().st_size:
                    continue
                candidates.append({"path": str(path), "scope": scope, "status": "candidate"})
                break
            except OSError:
                candidates.append({"path": str(path), "scope": scope, "status": UNKNOWN})
                break
    inline = {key: bool(config.get(key)) for key in ("developer_instructions", "instructions")}
    custom_files = [{"setting": key, "path": text(config[key])} for key in
                    ("model_instructions_file",) if isinstance(config.get(key), str)]
    limit = config.get("project_doc_max_bytes")
    return {"status": "inferred", "global_scan_status": "inspected" if codex_home is not None else UNKNOWN,
            "project_root": str(root), "files": candidates,
            "inline_config_present": inline, "custom_files": custom_files,
            "configured_byte_limit": limit if isinstance(limit, int) else UNKNOWN,
            "note": "Candidates inferred from filenames and nonzero size; contents, whitespace-only files, "
                    "truncation and the actual assembled prompt were not inspected."}


def permissions(config, extra, requirements):
    args = extra[:extra.index("--")] if "--" in extra else extra
    requested = {}
    added = []
    for i, arg in enumerate(args):
        if arg in {"--sandbox", "--ask-for-approval"} and i + 1 < len(args):
            requested["sandbox_mode" if arg == "--sandbox" else "approval_policy"] = args[i + 1]
        elif arg == "--add-dir" and i + 1 < len(args):
            added.append(text(args[i + 1]))
    bypass = "--dangerously-bypass-approvals-and-sandbox" in args
    workspace = mapping(config.get("sandbox_workspace_write"))
    policy = config.get("approval_policy")
    approval = "granular" if isinstance(policy, dict) and "granular" in policy else choice(
        policy, ("on-request", "never", "untrusted"))
    features = mapping(config.get("features"))
    proxy = features.get("network_proxy")
    managed = mapping(mapping(requirements).get("requirements"))
    return {
        "status": "configuration_only",
        "sandbox_mode": {"configured": choice(config.get("sandbox_mode"),
                                               ("read-only", "workspace-write", "danger-full-access")),
                         "cli_requested": "danger-full-access" if bypass else requested.get("sandbox_mode")},
        "approval_policy": {"configured": approval,
                            "cli_requested": "never" if bypass else requested.get("approval_policy")},
        "approval_reviewer": {"configured": choice(config.get("approvals_reviewer"), ("user", "auto_review")),
                              "cli_requested": "auto_review" if "--approve-for-me" in args else None},
        "bypass_requested": bypass,
        "permission_profile": text(config.get("default_permissions")),
        "configured_workspace_writable_roots": [text(v) for v in strings(workspace.get("writable_roots"))],
        "additional_cli_directories": added,
        "workspace_network_access": boolean(workspace.get("network_access")),
        "workspace_network_note": "Applies only to workspace-write shell execution; not MCP, apps or web search.",
        "web_search": {"configured": choice(config.get("web_search"), ("disabled", "cached", "indexed", "live")),
                       "cli_requested": "live" if "--search" in args else None},
        "network_proxy_configured": boolean(proxy.get("enabled") if isinstance(proxy, dict) else proxy),
        "configured_network_domain_rules": [
            {"domain": text(domain), "access": access}
            for domain, access in mapping(mapping(proxy).get("domains")).items()
            if isinstance(domain, str) and re.fullmatch(r"[A-Za-z0-9_.*:-]+", domain)
            and access in ("allow", "deny")],
        "managed_requirements": {
            "status": "reported" if requirements is not None else UNKNOWN,
            "present": bool(managed) if requirements is not None else UNKNOWN,
            "allowed_sandbox_modes": [choice(v, ("read-only", "workspace-write", "danger-full-access"))
                                      for v in strings(managed.get("allowedSandboxModes"))],
            "allowed_approval_policies": [choice(v, ("on-request", "never", "untrusted"))
                                         for v in strings(managed.get("allowedApprovalPolicies"))],
            "permission_profile_constraints_present": bool(managed.get("allowedPermissionProfiles")),
            "managed_default_permissions": text(managed.get("defaultPermissions")),
        },
        "enforcement": "unknown: no runtime sandbox, filesystem access or network reachability was tested; "
                       "defaults and managed restrictions may be applied at launch",
    }


def mcp_entry(name, spec, source):
    spec = mapping(spec)
    return {"name": text(name), "source": source,
            "configured_enabled": boolean(spec.get("enabled", True)),
            "transport": "stdio" if spec.get("command") else "http" if spec.get("url") else UNKNOWN,
            "configured_env_names": env_names(mapping(spec.get("env"))),
            "inherited_env_names": env_names(strings(spec.get("env_vars"))),
            "bearer_env_names": env_names([spec.get("bearer_token_env_var")]),
            "header_env_names": env_names(mapping(spec.get("env_http_headers")).values()),
            "inline_headers_present": bool(spec.get("http_headers")),
            "runtime_status": "not connected"}


def integrations(config, snapshot, extra):
    args = extra[:extra.index("--")] if "--" in extra else extra
    mcps = [mcp_entry(n, s, "config/read") for n, s in mapping(config.get("mcp_servers")).items()]
    catalog = snapshot.get("plugins")
    plugins = {}
    for name, spec in mapping(config.get("plugins")).items():
        plugins[name] = {"id": text(name), "configured_enabled": boolean(mapping(spec).get("enabled")),
                         "installed": UNKNOWN, "source": "config/read"}
    for market in mapping(catalog).get("marketplaces", []):
        for plugin in market.get("plugins", []):
            if not plugin.get("installed"):
                continue
            name = plugin["id"]
            plugins[name] = {"id": text(name), "configured_enabled": boolean(plugin.get("enabled")),
                             "installed": True, "source": "local plugin/list"}
            detail = mapping(snapshot.get("plugin_details", {}).get(name))
            plugins[name]["components_status"] = "reported" if detail else UNKNOWN
            for server in strings(detail.get("mcpServers")):
                overrides = mapping(mapping(mapping(config.get("plugins")).get(name)).get("mcp_servers"))
                item = mcp_entry(server, overrides.get(server), text(name))
                # A declared component of a disabled plugin is not active.
                if plugin.get("enabled") is False:
                    item["configured_enabled"] = False
                item["transport"] = UNKNOWN
                mcps.append(item)
    hook_data = snapshot.get("hooks")
    hooks, hook_errors, hook_warnings = [], 0, 0
    for entry in mapping(hook_data).get("data", []):
        hook_errors += len(entry.get("errors", []))
        hook_warnings += len(entry.get("warnings", []))
        for hook in entry.get("hooks", []):
            hooks.append({"event": text(hook.get("eventName")),
                          "kind": choice(hook.get("handlerType"), ("command", "mcpTool", "prompt", "agent")),
                          "configured_enabled": boolean(hook.get("enabled")),
                          "trust": choice(hook.get("trustStatus"), ("managed", "untrusted", "trusted", "modified")),
                          "source": text(hook.get("source")), "path": text(hook.get("sourcePath")),
                          "plugin": text(hook.get("pluginId"), None)})
    apps = mapping(config.get("apps"))
    features = mapping(config.get("features"))
    return {"mcp_servers": mcps,
            "plugins": {"status": "local_catalog_only" if catalog is not None else UNKNOWN,
                        "load_error_count": len(mapping(catalog).get("marketplaceLoadErrors", [])),
                        "items": sorted(plugins.values(), key=lambda p: p["id"])},
            "hooks": {"status": UNKNOWN if hook_data is None else "partial" if hook_errors or hook_warnings else "reported",
                      "feature_configured": boolean(features.get("hooks", features.get("codex_hooks"))),
                      "trust_bypass_requested": "--dangerously-bypass-hook-trust" in args,
                      "error_count": hook_errors, "warning_count": hook_warnings, "items": hooks,
                      "note": "Enabled is a configuration flag; trust and runtime conditions still apply. No hooks executed."},
            "apps": {"feature_configured": boolean(features.get("apps")),
                     "default_configured_enabled": boolean(mapping(apps.get("_default")).get("enabled")),
                     "configured_ids": [{"id": text(n), "enabled": boolean(mapping(s).get("enabled"))}
                                        for n, s in apps.items() if n != "_default"],
                     "runtime_permissions": UNKNOWN}}


def credentials(config, mcps, home, codex_home, environment_names, cwd):
    known = {n for n in environment_names if SECRET_NAME.search(n) or n == "SSH_AUTH_SOCK"}
    provider_refs = set()
    for provider in mapping(config.get("model_providers")).values():
        provider_refs.update(env_names([mapping(provider).get("env_key")]))
    known.update(provider_refs)
    referenced = sorted({n for s in mcps for key in
                         ("configured_env_names", "inherited_env_names", "bearer_env_names", "header_env_names")
                         for n in s[key]})
    shell = mapping(config.get("shell_environment_policy"))
    files = [("AWS shared credentials", home / ".aws/credentials"),
             ("netrc", home / ".netrc"), ("Git credential store", home / ".git-credentials"),
             ("npm configuration", home / ".npmrc"),
             ("Google application credentials", home / ".config/gcloud/application_default_credentials.json"),
             ("Project .env (not automatically inherited)", cwd / ".env")]
    if codex_home is not None:
        files.insert(0, ("Codex file authentication", codex_home / "auth.json"))
    return {"launcher_environment_candidates": env_names(known & set(environment_names)),
            "configured_environment_references": referenced,
            "model_provider_environment_references": sorted(provider_refs),
            "shell_policy": {"inherit": choice(shell.get("inherit"), ("all", "core", "none")),
                             "set_variable_names": env_names(mapping(shell.get("set"))),
                             "filter_rules_present": any(shell.get(k) for k in ("filters", "exclude", "include_only")),
                             "tool_shell_visibility": UNKNOWN},
            "codex_auth_store": choice(config.get("cli_auth_credentials_store"), ("file", "keyring", "auto", "ephemeral")),
            "mcp_auth_store": choice(config.get("mcp_oauth_credentials_store"), ("file", "keyring", "auto", "ephemeral")),
            "known_file_locations": [{"source": name, "path": str(path), "status": file_info(path)} for name, path in files],
            "note": "Environment names are a heuristic. File presence does not prove valid credentials or runtime access. "
                    "Values, keychains, file contents, shell startup files and workload identity were not inspected."}


def build_report(manifest, snapshot, extra=(), *, home=None, environment_names=None):
    config_result = mapping(snapshot.get("configuration"))
    config = mapping(config_result.get("config"))
    cwd = Path(manifest["cwd"])
    home = Path(home) if home is not None else Path.home()
    value = snapshot.get("codex_home")
    codex_home = Path(value) if isinstance(value, str) and Path(value).is_absolute() else None
    integration = integrations(config, snapshot, extra)
    layers = []
    for layer in config_result.get("layers") or []:
        source = mapping(layer.get("name"))
        layers.append({"type": text(source.get("type")),
                       "path": text(source.get("file", source.get("dotCodexFolder")), None),
                       "disabled": bool(layer.get("disabledReason"))})
    return {
        "schema_version": 1, "kit": text(manifest["kit"]), "cwd": str(cwd), "read_only": True,
        "skills": {"verified": bool(manifest.get("verified")), "selected_count": manifest["selected_count"],
                   "excluded_count": manifest["excluded_count"],
                   "selected": [{"name": text(s["name"]), "path": text(s["path"]), "scope": text(s["scope"]),
                                 "plugin": text(s.get("pluginId"), None), "reason": text(s["reason"])}
                                for s in manifest["selected"]]},
        "instructions": instructions(config, cwd, codex_home), "configuration_layers": layers,
        "permissions": permissions(config, extra, snapshot.get("requirements")),
        "integrations": integration,
        "credentials": credentials(config, integration["mcp_servers"], home, codex_home,
                                   set(os.environ) if environment_names is None else set(environment_names), cwd),
        "limits": ["Configuration visibility is not a security certification or enforcement test.",
                   "Remote and workspace-managed plugin catalogs were not queried; plugin coverage may be incomplete.",
                   "Runtime sandbox restrictions, external service permissions and credential readability remain unknown.",
                   "Codex's inventory process may update its ordinary caches/state; no model turn or integration connection was requested."],
    }


def render(report):
    """Compact default display; --json exposes the same allowlisted metadata."""
    lines = [f"Codex audit · {report['kit']}", f"Working directory: {report['cwd']}", ""]
    skills = report["skills"]
    lines.append(f"Skills: {skills['selected_count']} selected, {skills['excluded_count']} excluded (verified)")
    for s in skills["selected"]:
        lines.extend([f"  {s['name']} · {s['scope']} · {s['reason']}", f"    {s['path']}"])
    lines.append("\nInstruction files (inferred):")
    lines.extend(f"  {s['scope']}: {s['path']}" for s in report["instructions"]["files"])
    if not report["instructions"]["files"]:
        lines.append("  No nonempty candidates found.")
    for key, present in report["instructions"]["inline_config_present"].items():
        if present:
            lines.append(f"  {key}: configured inline (contents omitted)")
    for item in report["instructions"]["custom_files"]:
        lines.append(f"  {item['setting']}: {item['path']}")
    lines.append("  " + report["instructions"]["note"])
    lines.append("\nPermissions (configuration only):")
    policy = report["permissions"]
    for title, key in [("Sandbox", "sandbox_mode"), ("Approval", "approval_policy"), ("Web search", "web_search")]:
        item = policy[key]
        lines.append(f"  {title}: {item['configured']} configured" +
                     (f"; {item['cli_requested']} requested by CLI" if item["cli_requested"] else ""))
    lines.append(f"  Workspace shell network: {policy['workspace_network_access']}")
    lines.append(f"  Permission profile: {policy['permission_profile']}")
    lines.append(f"  Managed requirements: {policy['managed_requirements']['status']}; present={policy['managed_requirements']['present']}")
    for rule in policy["configured_network_domain_rules"]:
        lines.append(f"  Network rule (configured): {rule['access']} {rule['domain']}")
    for path in policy["configured_workspace_writable_roots"] + policy["additional_cli_directories"]:
        lines.append(f"  Additional write directory (configured/requested): {path}")
    lines.append("  Enforcement: " + policy["enforcement"])
    lines.append("\nMCP servers (configuration only; not connected):")
    for s in report["integrations"]["mcp_servers"]:
        lines.append(f"  {s['name']} · {s['source']} · enabled={s['configured_enabled']}")
    if not report["integrations"]["mcp_servers"]:
        lines.append("  None reported; plugin coverage may be incomplete.")
    plugins = report["integrations"]["plugins"]
    lines.append(f"\nPlugins: {plugins['status']}")
    for plugin in plugins["items"]:
        lines.append(f"  {plugin['id']} · enabled={plugin['configured_enabled']} · installed={plugin['installed']}")
    apps = report["integrations"]["apps"]
    lines.append(f"Apps: feature={apps['feature_configured']}; runtime permissions unknown")
    for app in apps["configured_ids"]:
        lines.append(f"  {app['id']} · configured enabled={app['enabled']}")
    hooks = report["integrations"]["hooks"]
    lines.append(f"\nHooks: {hooks['status']}; feature={hooks['feature_configured']}")
    lines.append(f"  Hook trust bypass requested: {hooks['trust_bypass_requested']}")
    for h in hooks["items"]:
        lines.extend([f"  {h['event']} · {h['plugin'] or h['source']} · enabled={h['configured_enabled']} · trust={h['trust']}",
                      f"    {h['path']}"])
    lines.append("  " + hooks["note"])
    creds = report["credentials"]
    lines.append("\nCredential sources (names and locations only):")
    lines.append("  Launcher environment: " + (", ".join(creds["launcher_environment_candidates"]) or "no heuristic matches"))
    lines.append("  Configured MCP environment references: " + (", ".join(creds["configured_environment_references"]) or "none"))
    lines.append("  Model-provider environment references: " + (", ".join(creds["model_provider_environment_references"]) or "none"))
    lines.append("  Shell-set variable names: " + (", ".join(creds["shell_policy"]["set_variable_names"]) or "none"))
    lines.append(f"  Codex auth store: {creds['codex_auth_store']}; MCP auth store: {creds['mcp_auth_store']}")
    for f in creds["known_file_locations"]:
        lines.append(f"  {f['source']}: {f['status']} · {f['path']}")
    lines.append("  " + creds["note"])
    lines.append("\nLimits:")
    lines.extend("  " + item for item in report["limits"])
    return "\n".join(lines)
