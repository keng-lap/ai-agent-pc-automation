"""P5-515 static capability audits for privacy and test-harness boundaries.

These checks inspect repository source only. They do not inspect the host OS,
filesystem contents, registry, running processes, or network state.
"""

import ast
from datetime import UTC, datetime
from pathlib import Path

from agent_backend.audit import AuditEventSink

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_MODULE = REPO_ROOT / "src/backend/agent_backend/audit.py"
FRONTEND_TEST = REPO_ROOT / "src/frontend/src/app/app.spec.ts"

_EXTERNAL_TRANSPORT_ROOTS = {
    "aiohttp",
    "boto3",
    "datadog",
    "google",
    "httpx",
    "httpx2",
    "mixpanel",
    "newrelic",
    "opentelemetry",
    "posthog",
    "requests",
    "sentry_sdk",
    "socket",
    "urllib",
    "urllib3",
}

_HOST_CAPABILITY_ROOTS = {
    "aiohttp",
    "boto3",
    "ctypes",
    "datadog",
    "mixpanel",
    "newrelic",
    "opentelemetry",
    "psutil",
    "pywinauto",
    "requests",
    "sentry_sdk",
    "socket",
    "subprocess",
    "urllib",
    "urllib3",
    "winreg",
    "wmi",
}

_FORBIDDEN_OS_CALLS = {
    "execv",
    "execve",
    "kill",
    "listdir",
    "lstat",
    "makedirs",
    "mkdir",
    "open",
    "popen",
    "remove",
    "removedirs",
    "rename",
    "replace",
    "rmdir",
    "scandir",
    "spawnl",
    "spawnv",
    "startfile",
    "stat",
    "system",
    "unlink",
    "walk",
}


def _module_root(module: str | None) -> str:
    return (module or "").split(".", maxsplit=1)[0]


def _imported_roots(tree: ast.AST) -> set[str]:
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(_module_root(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add(_module_root(node.module))
    return roots


def _attribute_chain(node: ast.AST) -> list[str]:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


def test_audit_sink_has_no_external_telemetry_or_transport_dependency():
    source = AUDIT_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(AUDIT_MODULE))

    assert not (_imported_roots(tree) & _EXTERNAL_TRANSPORT_ROOTS)

    forbidden_calls = {
        "capture_event",
        "capture_exception",
        "capture_message",
        "connect",
        "create_connection",
        "emit",
        "export",
        "flush",
        "request",
        "track",
        "urlopen",
    }
    calls = {
        chain[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (chain := _attribute_chain(node.func))
    }
    assert not (calls & forbidden_calls)

    sink = AuditEventSink()
    sink.record(
        {
            "event_type": "policy.denied",
            "occurred_at": datetime.now(UTC),
            "tool_id": "software.install",
            "outcome": "denied",
            "deny_reason": "permission_denied",
        }
    )
    assert len(sink.snapshot()) == 1


def test_backend_test_sources_do_not_import_host_inspection_capabilities():
    violations = []
    for source_path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        imported = _imported_roots(tree) & _HOST_CAPABILITY_ROOTS
        if imported:
            violations.append(f"{source_path.relative_to(REPO_ROOT)} imports {sorted(imported)}")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            chain = _attribute_chain(node.func)
            if len(chain) == 2 and chain[0] == "os" and chain[1] in _FORBIDDEN_OS_CALLS:
                violations.append(
                    f"{source_path.relative_to(REPO_ROOT)} calls os.{chain[1]}"
                )
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                violations.append(
                    f"{source_path.relative_to(REPO_ROOT)} uses dynamic __import__"
                )

    assert violations == []


def test_frontend_test_source_does_not_import_host_or_network_capabilities():
    source = FRONTEND_TEST.read_text(encoding="utf-8")
    forbidden_imports = (
        "node:child_process",
        "node:cluster",
        "node:dgram",
        "node:fs",
        "node:net",
        "node:os",
        "node:worker_threads",
        "node:vm",
    )
    assert not [module for module in forbidden_imports if module in source]
