#!/usr/bin/env python3
"""Regenerate the committed API reference from the FastAPI application.

The schema is produced by importing ``backend.main:app`` and calling
``app.openapi()``. No server is started and no port is bound, so this runs
identically in CI, in the container, and on a developer machine.

    python docs/generate_api_reference.py            # rewrite the two outputs
    python docs/generate_api_reference.py --check    # fail if they are stale

Outputs (both committed, both overwritten wholesale):

* ``docs/api/openapi.json`` — the schema itself, for client generators and for
  anyone who would rather read machine-readable output than prose.
* ``docs/api/README.md``    — a human-readable reference grouped by tag.

``--check`` exists so that a pull request which adds or renames an endpoint
cannot silently leave the reference describing the previous API. It compares
byte-for-byte against what a regeneration would write and exits 1 on a
difference, printing which file drifted.

WebSocket routes are absent from the OpenAPI document by design — the
specification has no way to describe them. They are listed by hand in the
"Streaming endpoints" section of ``docs/api/README.md``'s preamble, which is
generated from :data:`STREAMING_NOTES` below; keep that constant in step with
``backend/routers/ws.py`` and the SSE routes in ``backend/routers/pipeline.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DOCS_DIR = Path(__file__).resolve().parent
REPO_ROOT = DOCS_DIR.parent
API_DIR = DOCS_DIR / "api"
SCHEMA_PATH = API_DIR / "openapi.json"
REFERENCE_PATH = API_DIR / "README.md"

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Routes that carry no OpenAPI operation. Verified against the source files
#: named beside each entry; update both together.
STREAMING_NOTES: tuple[tuple[str, str, str], ...] = (
    (
        "WebSocket",
        "/api/ws/progress",
        "Live job progress. Declared with `@router.websocket` in "
        "`backend/routers/ws.py`, so it cannot appear in the OpenAPI document.",
    ),
    (
        "SSE",
        "POST /api/pipeline/run-stream",
        "Server-sent events for a single-target pipeline run "
        "(`backend/routers/pipeline.py`).",
    ),
    (
        "SSE",
        "POST /api/pipeline/batch-stream",
        "Server-sent events for a batch pipeline run "
        "(`backend/routers/pipeline.py`).",
    ),
)

PREAMBLE = """<!--
  GENERATED FILE — do not edit by hand.
  Regenerate with:  python docs/generate_api_reference.py
  Source of truth:  backend/main.py (FastAPI app.openapi())
-->

# Helix Core HTTP API reference

`{title}` v`{version}`. Generated from the OpenAPI {openapi_version} document
emitted by the application itself, not written by hand.

The machine-readable schema is committed alongside this file at
[`openapi.json`](openapi.json). Point any OpenAPI client generator at it.

While the backend is running, the same schema is served live and rendered
interactively:

| | |
|---|---|
| Swagger UI | <http://127.0.0.1:8299/docs> |
| ReDoc | <http://127.0.0.1:8299/redoc> |
| Raw schema | <http://127.0.0.1:8299/openapi.json> |

Everything is local. The backend binds `127.0.0.1` by default, there is no
authentication layer, and no telemetry is sent anywhere. Endpoints that reach
the network do so to named public services only: RCSB PDB, UniProt, ChEMBL, and
PubChem.

## Conventions

- Every path below is relative to `http://127.0.0.1:8299`.
- Request and response bodies are JSON unless stated otherwise.
- **File paths in requests are paths on the machine running the backend**, not
  uploads. `pdb_path`, `ligands_dir`, `receptor`, `results_dir` and friends are
  read and written directly by the server process.
- Long-running operations (docking, batch generation, conversion, pipeline runs)
  register with the job manager and can be paused, resumed, or terminated
  through `/api/jobs/*` while they run.

## Streaming endpoints

These carry no OpenAPI operation — the specification cannot describe a WebSocket,
and the SSE routes stream `text/event-stream` rather than a JSON body.

| Kind | Endpoint | Purpose |
|---|---|---|
{streaming_rows}

## Contents

{toc}
"""


def build_schema() -> dict[str, Any]:
    """Import the application and return its OpenAPI document."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from backend.main import app  # noqa: PLC0415 - import must follow sys.path setup

    return app.openapi()


def _anchor(text: str) -> str:
    """GitHub-flavoured heading anchor for *text*."""
    keep = [ch for ch in text.lower() if ch.isalnum() or ch in " -_"]
    return "".join(keep).strip().replace(" ", "-")


def _schema_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type_of(schema: dict[str, Any]) -> str:
    """Render a parameter/property type compactly."""
    if "$ref" in schema:
        return f"`{_schema_name(schema['$ref'])}`"
    if "anyOf" in schema:
        parts = [_type_of(sub) for sub in schema["anyOf"] if sub.get("type") != "null"]
        rendered = " \\| ".join(dict.fromkeys(parts)) or "`null`"
        optional = any(sub.get("type") == "null" for sub in schema["anyOf"])
        return f"{rendered}, optional" if optional else rendered
    if schema.get("type") == "array":
        return f"array of {_type_of(schema.get('items', {}))}"
    if "type" in schema:
        return f"`{schema['type']}`"
    return "`object`"


def _body_ref(operation: dict[str, Any]) -> str | None:
    content = operation.get("requestBody", {}).get("content", {})
    schema = content.get("application/json", {}).get("schema", {})
    if "$ref" in schema:
        return _schema_name(schema["$ref"])
    return None


def _render_model(name: str, schemas: dict[str, Any]) -> list[str]:
    """Render one component schema as a property table."""
    model = schemas.get(name)
    if not model or "properties" not in model:
        return []
    required = set(model.get("required", []))
    lines = [
        "",
        f"<details><summary>Request body — <code>{name}</code></summary>",
        "",
        "| Field | Type | Required | Default | Notes |",
        "|---|---|---|---|---|",
    ]
    for field, spec in model["properties"].items():
        default = spec.get("default")
        default_cell = "—" if default is None else f"`{json.dumps(default)}`"
        note = (spec.get("description") or "").replace("|", "\\|")
        lines.append(
            f"| `{field}` | {_type_of(spec)} | "
            f"{'yes' if field in required else 'no'} | {default_cell} | {note} |"
        )
    lines.extend(["", "</details>"])
    return lines


def render_reference(schema: dict[str, Any]) -> str:
    """Render the whole Markdown reference for *schema*."""
    info = schema.get("info", {})
    components = schema.get("components", {}).get("schemas", {})

    groups: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            tags = operation.get("tags") or ["General"]
            groups.setdefault(tags[0], []).append((path, method.upper(), operation))

    ordered_tags = sorted(groups, key=lambda tag: (tag == "General", tag.lower()))
    operation_count = sum(len(items) for items in groups.values())

    toc = "\n".join(
        f"- [{tag}](#{_anchor(tag)}) — {len(groups[tag])} "
        f"{'operation' if len(groups[tag]) == 1 else 'operations'}"
        for tag in ordered_tags
    )
    streaming_rows = "\n".join(
        f"| {kind} | `{endpoint}` | {purpose} |"
        for kind, endpoint, purpose in STREAMING_NOTES
    )

    out: list[str] = [
        PREAMBLE.format(
            title=info.get("title", "Helix Core Backend"),
            version=info.get("version", "unknown"),
            openapi_version=schema.get("openapi", "3.1.0"),
            toc=toc,
            streaming_rows=streaming_rows,
        ).rstrip(),
        "",
        f"{operation_count} HTTP operations in {len(ordered_tags)} groups, plus "
        f"{len(STREAMING_NOTES)} streaming endpoints.",
        "",
    ]

    for tag in ordered_tags:
        out.extend(["---", "", f"## {tag}", ""])
        for path, method, operation in sorted(groups[tag], key=lambda item: item[0]):
            summary = operation.get("summary") or ""
            out.append(f"### `{method} {path}`")
            if summary:
                out.extend(["", f"**{summary}**"])
            description = (operation.get("description") or "").strip()
            if description:
                out.extend(["", description])

            params = operation.get("parameters") or []
            if params:
                out.extend(
                    [
                        "",
                        "| Parameter | In | Type | Required | Notes |",
                        "|---|---|---|---|---|",
                    ]
                )
                for param in params:
                    note = (param.get("description") or "").replace("|", "\\|")
                    out.append(
                        f"| `{param['name']}` | {param.get('in', '')} | "
                        f"{_type_of(param.get('schema', {}))} | "
                        f"{'yes' if param.get('required') else 'no'} | {note} |"
                    )

            body = _body_ref(operation)
            if body:
                out.extend(_render_model(body, components))

            codes = ", ".join(f"`{code}`" for code in sorted(operation.get("responses", {})))
            if codes:
                out.extend(["", f"Responses: {codes}"])
            out.append("")

    out.extend(
        [
            "---",
            "",
            "## Schemas",
            "",
            f"The OpenAPI document defines {len(components)} component schemas. "
            "They are not reproduced here — read them in "
            "[`openapi.json`](openapi.json), or browse them with the type-aware "
            "rendering at <http://127.0.0.1:8299/redoc> while the backend runs.",
            "",
        ]
    )
    return "\n".join(out)


def _write(path: Path, content: str, *, check: bool) -> bool:
    """Write *content* to *path*, or in check mode report whether it differs."""
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current == content:
        return False
    if check:
        print(f"stale: {path.relative_to(REPO_ROOT).as_posix()}", file=sys.stderr)
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote: {path.relative_to(REPO_ROOT).as_posix()}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the committed reference is out of date",
    )
    args = parser.parse_args(argv)

    schema = build_schema()
    schema_text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    reference_text = render_reference(schema)

    drifted = _write(SCHEMA_PATH, schema_text, check=args.check)
    drifted |= _write(REFERENCE_PATH, reference_text, check=args.check)

    if args.check and drifted:
        print(
            "The committed API reference does not match the application. "
            "Run: python docs/generate_api_reference.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
