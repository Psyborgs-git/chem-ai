"""Export the offline Help reference from source, SDL, and reviewed metadata.

This module deliberately never imports studio, creates an ASGI app, resolves
environment values, connects to PostgreSQL, or starts a worker. Run from any cwd:
    uv run --no-sync python infra/ci/export_help_reference.py [--check]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from graphql import build_ast_schema, parse, print_ast, validate

ROOT = Path(__file__).resolve().parents[2]
API = "services/studio-api/src/studio/api"
METADATA = "docs/reference-source/metadata.json"
OUTPUT = "docs/reference"
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
SOURCE_ROOTS = ("services", "workers", "packages", "infra", "apps/studio-web", "tests")
SOURCE_SUFFIXES = {".py", ".sh", ".rs", ".ts", ".tsx", ".mjs", ".cjs", ".toml"}
EXCLUDED = {"node_modules", "target", "dist", "__generated__", ".venv", ".runtime"}


def expression(node: ast.AST | None) -> str:
    return ast.unparse(node) if node is not None else ""


def literal(node: ast.AST | None, context: str) -> Any:
    try:
        return ast.literal_eval(node)  # type: ignore[arg-type]
    except (ValueError, TypeError, SyntaxError) as exc:
        raise ValueError(f"Unresolved static value in {context}: {expression(node)}") from exc


def snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


def read_tree(root: Path, path: str) -> ast.Module:
    return ast.parse((root / path).read_text(), filename=path)


def source_files(root: Path) -> list[Path]:
    files = []
    for base in SOURCE_ROOTS:
        for directory, dirs, names in os.walk(root / base):
            dirs[:] = sorted(set(dirs) - EXCLUDED - {".git", "__pycache__"})
            for name in sorted(names):
                path = Path(directory) / name
                if path.suffix in SOURCE_SUFFIXES and not path.is_symlink():
                    files.append(path)
    return sorted(files)


def route_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef, path: str) -> list[dict]:
    args = node.args.posonlyargs + node.args.args
    defaults: list[ast.AST | None] = [None] * (len(args) - len(node.args.defaults))
    pairs = list(zip(args, defaults + list(node.args.defaults), strict=True))
    pairs += list(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True))
    result = []
    for arg, default in pairs:
        annotation = expression(arg.annotation)
        if arg.arg in {"self", "request", "response", "db", "ctx"}:
            continue
        kind = "path" if re.search(r"\{" + re.escape(arg.arg) + r"[:}]", path) else "query"
        if "File(" in annotation or "Form(" in expression(default):
            kind = "multipart"
        elif arg.arg in {"body", "payload", "data"}:
            kind = "JSON body"
        wire_name = arg.arg
        required = default is None
        if isinstance(default, ast.Call) and expression(default.func) in {
            "Query",
            "Form",
            "Body",
            "File",
        }:
            options = {keyword.arg: keyword.value for keyword in default.keywords}
            if "alias" in options:
                wire_name = literal(options["alias"], "parameter alias")
            explicit = options.get("default", default.args[0] if default.args else None)
            required = explicit is None or (
                isinstance(explicit, ast.Constant) and explicit.value is Ellipsis
            )
        result.append(
            {
                "name": wire_name,
                "python_name": arg.arg,
                "in": kind,
                "type": annotation,
                "required": required,
                "default": expression(default) if default is not None else "required",
            }
        )
    return result


def rest_inventory(root: Path) -> list[dict]:
    """Resolve actual router registrations and fail closed on unfamiliar assembly."""
    app = read_tree(root, f"{API}/app.py")
    imports = {}
    for node in ast.walk(app):
        if isinstance(node, ast.ImportFrom) and node.module:
            for name in node.names:
                imports[name.asname or name.name] = (node.module, name.name)
    registered = {}
    graphql_seen = desktop_seen = False
    mounts = []
    for node in ast.walk(app):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "mount_desktop_web":
            desktop_seen = True
        if not isinstance(node.func, ast.Attribute) or expression(node.func.value) != "app":
            continue
        if node.func.attr == "mount":
            mounts.append(expression(node))
        if node.func.attr != "include_router":
            continue
        if not node.args:
            raise ValueError("include_router has no resolvable router")
        arg = node.args[0]
        prefix = next(
            (literal(k.value, "router prefix") for k in node.keywords if k.arg == "prefix"), ""
        )
        if isinstance(arg, ast.Call) and expression(arg.func) == "graphql_app":
            if prefix != "/graphql" or imports.get("graphql_app") != (
                "studio.api.graphql.schema",
                "graphql_app",
            ):
                raise ValueError("GraphQL transport registration changed; review its adapter")
            graphql_seen = True
        elif isinstance(arg, ast.Name) and arg.id in imports:
            module, symbol = imports[arg.id]
            key = ("services/studio-api/src/" + module.replace(".", "/") + ".py", symbol)
            if key in registered:
                raise ValueError(f"Duplicate router registration: {key}")
            registered[key] = prefix
        else:
            raise ValueError(f"Unresolved router registration: {expression(node)}")
    if not graphql_seen or not desktop_seen or mounts:
        raise ValueError("App transport/mount assembly changed; review the offline exporter")

    result = []
    found = set()
    for source in sorted((root / API).rglob("*.py")):
        path = source.relative_to(root).as_posix()
        tree = ast.parse(source.read_text())
        routers = {}
        decorated_routes = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            if expression(node.value.func) != "APIRouter":
                continue
            prefix = next(
                (literal(k.value, path) for k in node.value.keywords if k.arg == "prefix"), ""
            )
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    raise ValueError(f"Unresolved router variable in {path}")
                key = (path, target.id)
                if key not in registered:
                    raise ValueError(f"Router declared but not registered: {key}")
                found.add(key)
                routers[target.id] = registered[key] + prefix
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(
                    decorator.func, ast.Attribute
                ):
                    continue
                receiver, method = expression(decorator.func.value), decorator.func.attr
                if receiver not in routers and receiver != "app":
                    continue
                if receiver == "app" and method in {"exception_handler", "middleware", "on_event"}:
                    continue
                if method not in METHODS:
                    raise ValueError(f"Unclassified route decorator: {expression(decorator)}")
                decorated_routes.add((decorator.lineno, decorator.col_offset))
                if receiver == "app" and path not in {f"{API}/app.py", f"{API}/desktop.py"}:
                    raise ValueError(f"Unclassified inline app route in {path}")
                suffix = literal(decorator.args[0] if decorator.args else None, path)
                full_path = routers.get(receiver, "") + suffix
                status = next(
                    (literal(k.value, path) for k in decorator.keywords if k.arg == "status_code"),
                    200,
                )
                result.append(
                    {
                        "id": f"{method.upper()} {full_path}",
                        "method": method.upper(),
                        "path": full_path,
                        "source": path,
                        "line": node.lineno,
                        "handler": node.name,
                        "parameters": route_parameters(node, full_path),
                        "status": status,
                        "annotation": expression(node.returns),
                        "condition": "desktop frontend enabled"
                        if path.endswith("/desktop.py")
                        else "core",
                        "docstring": ast.get_docstring(node) or "",
                    }
                )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                receiver = expression(node.func.value)
                registration = node.func.attr in METHODS | {
                    "add_api_route",
                    "add_route",
                    "add_websocket_route",
                    "include_router",
                }
                if registration and receiver in {*routers, "app", "app.router"}:
                    known_decorator = (node.lineno, node.col_offset) in decorated_routes
                    known_assembly = (
                        path == f"{API}/app.py"
                        and receiver == "app"
                        and node.func.attr == "include_router"
                    )
                    if not known_decorator and not known_assembly:
                        raise ValueError(f"Unclassified imperative registration in {path}")
                if expression(node.func.value) == "app" and node.func.attr == "mount":
                    if (
                        path != f"{API}/desktop.py"
                        or len(node.args) != 2
                        or not (
                            literal(node.args[0], path) == "/"
                            and isinstance(node.args[1], ast.Call)
                            and expression(node.args[1].func) == "DesktopWeb"
                        )
                    ):
                        raise ValueError(f"Unclassified static mount in {path}")
    if found != set(registered):
        raise ValueError(f"Registered routers missing definitions: {set(registered) - found}")
    ids = [row["id"] for row in result]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate REST method/path")
    return sorted(result, key=lambda row: row["id"])


def graphql_inventory(root: Path) -> tuple[list[dict], list[dict]]:
    document = parse((root / "packages/contracts/schema.graphql").read_text())
    definitions = {d.name.value: d for d in document.definitions if getattr(d, "name", None)}
    operations = []

    def bare(node):
        while hasattr(node, "type"):
            node = node.type
        return node.name.value

    def walk(name, prefix, kind, stack):
        if name in stack:
            raise ValueError(f"Cyclic GraphQL operation namespace: {name}")
        for field in definitions[name].fields:
            path = prefix + field.name.value
            target = bare(field.type)
            if kind == "mutation" and target.endswith("Mutation") and target in definitions:
                walk(target, path + ".", kind, [*stack, name])
            else:
                operations.append(
                    {
                        "id": f"{kind} {path}",
                        "kind": kind,
                        "path": path,
                        "namespace": prefix.rstrip(".") or "root",
                        "signature": print_ast(field),
                        "return_type": target,
                        "input_types": sorted(
                            {
                                bare(arg.type)
                                for arg in (field.arguments or ())
                                if bare(arg.type) in definitions
                            }
                        ),
                        "description": field.description.value if field.description else "",
                    }
                )

    for kind in ("query", "mutation", "subscription"):
        typename = kind.title()
        if typename in definitions:
            walk(typename, "", kind, [])
    types = [
        {"name": name, "kind": node.kind, "declaration": print_ast(node)}
        for name, node in sorted(definitions.items())
        if name not in {"Query", "Mutation"}
    ]
    builtins = {
        "Boolean": "Boolean true or false.",
        "Float": "Finite double-precision number.",
        "ID": "Opaque identifier serialized as a string; use the format required by the operation.",
        "Int": "Signed 32-bit integer.",
        "String": "UTF-8 text string.",
    }
    types += [
        {
            "name": name,
            "kind": "built_in_scalar",
            "declaration": f'"""{description}"""\nscalar {name}',
        }
        for name, description in builtins.items()
        if name not in definitions
    ]
    types.sort(key=lambda item: item["name"])
    return sorted(operations, key=lambda row: row["id"]), types


def environment_inventory(root: Path) -> list[dict]:
    names: dict[str, set[str]] = defaultdict(set)
    # STUDIO names are product-owned even when read through a computed key.
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in {"infra/ci/export_help_reference.py", "tests/unit/test_help_reference.py"}:
            continue
        text = path.read_text()
        values = set(re.findall(r"\bSTUDIO_[A-Z0-9_]+\b", text))
        values.update(re.findall(r"(?:process\.env\.|import\.meta\.env\.)([A-Z][A-Z0-9_]+)", text))
        if path.suffix == ".sh":
            values.update(re.findall(r"\$\{([A-Z][A-Z0-9_]*)(?::[-+?=]|\})", text))
        for name in values:
            names[name].add(relative)
    makefile = root / "Makefile"
    if makefile.exists():
        for name in re.findall(r"^([A-Z][A-Z0-9_]*)\s*\?=", makefile.read_text(), re.M):
            names[name].add("Makefile")
    return [{"id": name, "sources": sorted(paths)} for name, paths in sorted(names.items())]


def load_metadata(root: Path) -> dict:
    return json.loads((root / METADATA).read_text())


def require_coverage(records: list[dict], metadata: dict, label: str) -> None:
    actual = {record["id"] for record in records}
    missing, extra = actual - set(metadata), set(metadata) - actual
    if missing or extra:
        raise ValueError(
            f"{label} metadata coverage: missing={sorted(missing)}; stale={sorted(extra)}"
        )
    for key, value in metadata.items():
        if not isinstance(value, dict) or not value.get("summary"):
            raise ValueError(f"{label} metadata has no summary: {key}")
        if re.search(r"\b(?:TODO|TBD|FIXME)\b", json.dumps(value)):
            raise ValueError(f"Unfinished {label} metadata: {key}")


def validate_rest_examples(rest: list[dict], examples: dict) -> None:
    actual = {route["id"] for route in rest}
    if set(examples) != actual:
        raise ValueError("Reviewed REST example coverage differs from registered routes")
    for route in rest:
        identifier = route["id"]
        example = examples[identifier]
        for field in ("requestExample", "successExample", "failureExample", "failureWhen"):
            if not example.get(field):
                raise ValueError(f"Reviewed REST example missing {field}: {identifier}")
        first_line = example["requestExample"].splitlines()[0]
        match = re.fullmatch(r"([A-Z]+) (\S+) HTTP/\d(?:\.\d)?", first_line)
        if not match or match[1] != route["method"]:
            raise ValueError(f"Invalid example request line: {identifier}")
        url = urlsplit(match[2])
        template = re.escape(route["path"])
        template = re.sub(r"\\\{.*?\\\}", r"[^?]+", template)
        if not re.fullmatch(template, url.path):
            raise ValueError(f"Example path does not match registered route: {identifier}")
        query = parse_qs(url.query)
        for parameter in route["parameters"]:
            if parameter["in"] == "query" and parameter["required"]:
                if parameter["name"] not in query:
                    raise ValueError(
                        f"Example missing required query {parameter['name']}: {identifier}"
                    )


def load_rest_examples(root: Path, rest: list[dict]) -> dict:
    examples = json.loads((root / "docs/reference-source/rest-examples.json").read_text())
    validate_rest_examples(rest, examples)
    return examples


def symbol_code(root: Path, reference: str) -> str:
    path, qualified = reference.split(":", 1)
    text = (root / path).read_text()
    scope: ast.AST = ast.parse(text)
    for name in qualified.split("."):
        found = next(
            (node for node in getattr(scope, "body", []) if getattr(node, "name", None) == name),
            None,
        )
        if found is None and isinstance(scope, ast.Module):
            candidates = [node for node in ast.walk(scope) if getattr(node, "name", None) == name]
            if len(candidates) == 1:
                found = candidates[0]
        if found is None:
            raise ValueError(f"Missing contract source: {reference}")
        scope = found
    lines = text.splitlines()
    start = min([scope.lineno] + [d.lineno for d in getattr(scope, "decorator_list", [])])
    return "\n".join(lines[start - 1 : scope.end_lineno])


def contract_rules(root: Path, references: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Describe literal checks; no inferred permission means a delegated check is absent."""
    policy = read_tree(root, "packages/policy/chem_studio_policy/capabilities.py")
    vocabulary = {}
    for node in policy.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("CAP_"):
                    vocabulary[target.id] = node.value.value
    capabilities = set()
    errors = set()
    for reference in references:
        tree = ast.parse(textwrap.dedent(symbol_code(root, reference)))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "require":
                for arg in node.args:
                    if isinstance(arg, ast.Name) and arg.id in vocabulary:
                        capabilities.add(vocabulary[arg.id])
            if expression(node.func) == "DomainError" and len(node.args) >= 2:
                code, message = node.args[:2]
                if isinstance(message, ast.Constant) and isinstance(message.value, str):
                    errors.add((expression(code).removeprefix("ErrorCode."), message.value))
            elif expression(node.func) in {"forbidden", "not_found", "revision_conflict"}:
                if node.args and isinstance(node.args[0], ast.Constant):
                    code = {
                        "forbidden": "FORBIDDEN",
                        "not_found": "NOT_FOUND",
                        "revision_conflict": "REVISION_CONFLICT",
                    }[expression(node.func)]
                    errors.add((code, str(node.args[0].value)))
    return sorted(capabilities), sorted(errors)


def anchor(text: str) -> str:
    return re.sub(r"\s+", "-", re.sub(r"[^a-z0-9_\s-]", "", text.lower()).strip())


def table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        + ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    )


def fence(value: str, language: str = "") -> str:
    marker = "````" if "```" in value else "```"
    return f"{marker}{language}\n{value}\n{marker}"


def render(root: Path) -> dict[str, str]:
    metadata = load_metadata(root)
    rest = rest_inventory(root)
    operations, types = graphql_inventory(root)
    env = environment_inventory(root)
    for label, records in (("rest", rest), ("graphql", operations), ("environment", env)):
        require_coverage(records, metadata[label], label)
    examples = load_rest_examples(root, rest)
    output = {}
    groups: dict[str, list] = defaultdict(list)
    for route in rest:
        detail = metadata["rest"][route["id"]]
        for required in ("request", "response", "auth", "errors"):
            if not detail.get(required):
                raise ValueError(f"REST contract missing {required}: {route['id']}")
        groups[detail["group"]].append((route, detail))
    for group, entries in sorted(groups.items()):
        info = metadata["groups"][group]
        lines = [
            f"# {info['title']}",
            "",
            info["summary"],
            "",
            "[Shared authentication, errors and transport](rest-overview.md). "
            "Examples use synthetic values; replace resource IDs with records from your workspace.",
            "",
        ]
        contracts = set()
        for route, detail in entries:
            lines += [
                f"## {route['id']}",
                "",
                detail["summary"],
                "",
                f"**Access:** {detail['auth']}",
                "",
                f"**Request:** {detail['request']}",
                "",
            ]
            if route["parameters"]:
                lines += [
                    table(
                        ["Parameter", "Location", "Declared type", "Default / constraints"],
                        [
                            [
                                f"`{p['name']}`"
                                + (" (required)" if p["required"] else " (optional)"),
                                p["in"],
                                f"`{p['type']}`",
                                f"`{p['default']}`",
                            ]
                            for p in route["parameters"]
                        ],
                    ),
                    "",
                ]
            lines += [
                f"**Response:** {detail['response']} Default success status: {route['status']}. "
                f"Availability: {route['condition']}.",
                "",
                f"**Failures:** {detail['errors']}",
                "",
                "**Request example:**",
                "",
            ]
            reviewed = examples[route["id"]]
            lines += [
                fence(reviewed["requestExample"], reviewed.get("requestLanguage", "http")),
                "",
                "**Success response example:** " + reviewed.get("successWhen", ""),
                "",
                fence(reviewed["successExample"], reviewed.get("successLanguage", "http")),
                "",
                "**Failure response example:** " + reviewed["failureWhen"],
                "",
                fence(reviewed["failureExample"], reviewed.get("failureLanguage", "http")),
                "",
            ]
            refs = list(detail.get("contracts", []))
            # Inline request models are source contracts too. Resolve them
            # statically; never import a model to evaluate runtime defaults.
            module = read_tree(root, route["source"])
            body_types = {
                name
                for parameter in route["parameters"]
                if parameter["in"] == "JSON body"
                for name in re.findall(r"\b[A-Z][A-Za-z0-9_]+\b", parameter["type"])
            }
            for node in module.body:
                if isinstance(node, ast.ClassDef) and node.name in body_types:
                    ref = route["source"] + ":" + node.name
                    if ref not in refs:
                        refs.append(ref)
            if refs:
                contracts.update(refs)
                links = [
                    f"[{ref.split(':')[1]}](contracts-{group}.md#{anchor(ref.split(':')[1])})"
                    for ref in refs
                ]
                lines += [
                    "**Exact JSON rules and response serialization:** " + ", ".join(links) + ".",
                    "",
                ]
            lines += [f"Source: `{route['source']}:{route['line']}` (`{route['handler']}`).", ""]
        output[f"rest-{group}.md"] = "\n".join(lines)
        if contracts:
            lines = [
                f"# {info['title']} — JSON contract details",
                "",
                "These excerpts are generated from the implementation without importing it. "
                "They specify accepted fields, conditional validation, defaults and response "
                "construction for flexible JSON interfaces. They complement the endpoint prose; "
                "implementation expressions "
                "refer to the named source service rather than a live execution.",
                "",
            ]
            for ref in sorted(contracts):
                lines += [
                    f"## {ref.split(':')[1]}",
                    "",
                    f"Source: `{ref}`.",
                    "",
                    fence(symbol_code(root, ref), "python"),
                    "",
                ]
            output[f"contracts-{group}.md"] = "\n".join(lines)

    for kind in ("query", "mutation", "subscription"):
        selected = [op for op in operations if op["kind"] == kind]
        if not selected:
            continue
        lines = [
            f"# GraphQL {kind} reference",
            "",
            "[Transport, IDs, pagination and errors](graphql-overview.md). "
            "Declarations below are generated from the committed SDL, "
            "including nested mutation namespaces. "
            "Look up argument and response structures in the [type catalog](graphql-types.md).",
            "",
        ]
        for op in selected:
            detail = metadata["graphql"][op["id"]]
            lines += [
                f"## {op['path']}",
                "",
                detail["summary"],
                "",
                fence(op["signature"], "graphql"),
                "",
                detail["behavior"],
                "",
                f"Return contract: [{op['return_type']}]"
                f"(graphql-types.md#{anchor(op['return_type'])}).",
                "",
            ]
            if op["input_types"]:
                lines += [
                    "Argument contracts: "
                    + ", ".join(
                        f"[{name}](graphql-types.md#{anchor(name)})" for name in op["input_types"]
                    )
                    + ".",
                    "",
                ]
            if detail.get("contracts"):
                lines += [
                    "Additional JSON semantics: "
                    + ", ".join(f"[{name}]({name}.md)" for name in detail["contracts"])
                    + ".",
                    "",
                ]
            if detail.get("source_contracts"):
                capabilities, errors = contract_rules(root, detail["source_contracts"])
                if capabilities:
                    lines += [
                        "**Capability checks declared in these contracts:** "
                        + ", ".join(f"`{capability}`" for capability in capabilities)
                        + ". Ownership and delegated checks also apply.",
                        "",
                    ]
                if errors:
                    lines += [
                        "**Literal rejection reasons declared in these contracts:** "
                        "dynamic messages and delegated failures "
                        "are specified by the full excerpts.",
                        "",
                        table(
                            ["Code", "Rejected condition / record"],
                            [[f"`{code}`", message] for code, message in errors],
                        ),
                        "",
                    ]
                lines += [
                    "Exact state, permission and validation rules: "
                    + ", ".join(
                        f"[{ref.split(':')[1]}](graphql-contracts.md#{anchor(ref.split(':')[1])})"
                        for ref in detail["source_contracts"]
                    )
                    + ".",
                    "",
                ]
            if detail.get("source"):
                lines += [f"Resolver source: `{detail['source']}`.", ""]
        output[f"graphql-{kind}.md"] = "\n".join(lines)
    lines = [
        "# GraphQL type catalog",
        "",
        "Every declared scalar, enum, input and response object from "
        "`packages/contracts/schema.graphql`, plus the standard built-in scalars. "
        "`!` means non-null, `[T]` is a list, and defaults appear after `=`. "
        "JSON scalars use the linked endpoint/contract guides; "
        "they do not imply arbitrary values are accepted.",
        "",
    ]
    for item in types:
        lines += [f"## {item['name']}", "", fence(item["declaration"], "graphql"), ""]
    # Root types are also useful to consumers, without duplicating field docs.
    for name, kind in (("Query", "query"), ("Mutation", "mutation")):
        lines += [f"## {name}", "", f"See the [complete {kind} reference](graphql-{kind}.md).", ""]
    output["graphql-types.md"] = "\n".join(lines)
    graphql_contracts = {
        ref for detail in metadata["graphql"].values() for ref in detail.get("source_contracts", [])
    }
    if graphql_contracts:
        lines = [
            "# GraphQL command state and validation contracts",
            "",
            "These generated source excerpts define exact capability checks, accepted payloads, "
            "state transitions and version/approval rules for the corresponding commands. "
            "They are static documentation; viewing Help never invokes them.",
            "",
        ]
        for ref in sorted(graphql_contracts):
            lines += [
                f"## {ref.split(':')[1]}",
                "",
                f"Source: `{ref}`.",
                "",
                fence(symbol_code(root, ref), "python"),
                "",
            ]
        output["graphql-contracts.md"] = "\n".join(lines)

    lines = [
        "# Environment and build configuration reference",
        "",
        "This inventory lists names found in first-party sources, "
        "including test and build settings. It reads source text only. "
        "No value is read from your environment, Keychain, runtime files or credentials. "
        "Unset/default descriptions below are static code behavior. "
        "Never paste secrets into source or Help.",
        "",
    ]
    scopes = sorted({metadata["environment"][row["id"]]["scope"] for row in env})
    for scope in scopes:
        lines += [f"## {scope}", ""]
        for row in env:
            item = metadata["environment"][row["id"]]
            if item["scope"] != scope:
                continue
            lines += [
                f"### {row['id']}",
                "",
                item["summary"],
                "",
                f"**Default / unset behavior:** {item['default']}",
                "",
                f"**Type and constraints:** {item['constraints']}",
                "",
                "Source: " + ", ".join(f"`{source}`" for source in row["sources"]) + ".",
                "",
            ]
    lines += ["## Worker-controlled environment", "", metadata["worker_environment"], ""]
    output["configuration.md"] = "\n".join(lines)

    for filename in ("rest-overview.md", "graphql-overview.md", "commands.md"):
        output[filename] = (root / "docs/reference-source" / filename).read_text()
    offline_schema = build_ast_schema(
        parse((root / "packages/contracts/schema.graphql").read_text())
    )
    for sample in re.findall(r"```graphql\n(.*?)\n```", output["graphql-overview.md"], re.S):
        failures = validate(offline_schema, parse(sample))
        if failures:
            raise ValueError("GraphQL reference example no longer matches SDL: " + str(failures[0]))
    command_lines = [output["commands.md"].rstrip(), "", "## Make targets", ""]
    targets = re.findall(
        r"^([a-zA-Z][a-zA-Z0-9_-]*):[^\n]*?##\s*(.+)$", (root / "Makefile").read_text(), re.M
    )
    command_lines += [
        table(
            ["Command", "Declared purpose"],
            [[f"`make {name}`", description] for name, description in targets],
        ),
        "",
    ]
    for path in ("package.json", "apps/studio-web/package.json"):
        package = json.loads((root / path).read_text())
        command_lines += [
            f"## Package scripts: {package['name']}",
            "",
            table(
                ["Script", "Exact expansion"],
                [[f"`{name}`", f"`{value}`"] for name, value in package.get("scripts", {}).items()],
            ),
            "",
        ]
    output["commands.md"] = "\n".join(command_lines)
    intro = [
        "# Complete interface reference",
        "",
        "Generated from repository sources and reviewed contract notes. Use these pages alongside "
        "the user, developer and operator guides. This reference contains no live workspace data.",
        "",
        f"Coverage: **{len(rest)} REST method/path definitions**, "
        f"**{sum(op['kind'] == 'query' for op in operations)} GraphQL queries**, "
        f"**{sum(op['kind'] == 'mutation' for op in operations)} callable mutations**, "
        f"**{len(types)} additional GraphQL type declarations**, "
        f"**{len(env)} configuration names**.",
        "",
        "The Strawberry-generated `/graphql` transport is documented separately. "
        "SPA/static assets are not data API operations. The desktop runtime probe is conditional.",
        "",
    ]
    intro += [
        table(
            ["Reference", "Contents"],
            [
                [f"[{name[:-3]}]({name})", text.splitlines()[0].lstrip("# ")]
                for name, text in sorted(output.items())
            ],
        ),
        "",
        "## Keeping this reference current",
        "",
        fence(
            "make docs-generate\nmake docs-check",
            "bash",
        ),
        "",
        "Edit the implementation or schema first, then update reviewed notes in "
        "`docs/reference-source/metadata.json` and the mandatory reviewed examples in "
        "`docs/reference-source/rest-examples.json`, then regenerate. "
        "The check rejects missing/stale metadata, "
        "unresolved router registrations, missing contract symbols and generated drift. "
        "GraphQL SDL must separately pass `infra/ci/export_schema.py --check`. "
        "Generated files in this directory should not be edited by hand.",
        "",
    ]
    output["README.md"] = "\n".join(intro)
    inventory = {
        "rest": rest,
        "graphql": operations,
        "environment": env,
        "types": [{"name": item["name"], "kind": item["kind"]} for item in types],
    }
    output["inventory.json"] = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
    return {name: text.rstrip() + "\n" for name, text in output.items()}


def export(root: Path, check: bool = False) -> list[str]:
    rendered = render(root)
    target = root / OUTPUT
    existing = {p.name for p in target.iterdir() if p.is_file()} if target.exists() else set()
    changes = []
    for name in sorted(existing | set(rendered)):
        path = target / name
        desired = rendered.get(name)
        if desired is None or not path.exists() or path.read_text() != desired:
            changes.append(name)
            if not check:
                target.mkdir(parents=True, exist_ok=True)
                if desired is None:
                    path.unlink()
                else:
                    path.write_text(desired)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        changed = export(ROOT, check=args.check)
    except (ValueError, KeyError, OSError) as exc:
        print(f"Help reference invalid: {exc}", file=sys.stderr)
        return 2
    if args.check and changed:
        print("Help reference drift: " + ", ".join(changed), file=sys.stderr)
        return 1
    print(
        "Help reference is current"
        if args.check
        else f"Generated Help reference ({len(changed)} files updated)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
