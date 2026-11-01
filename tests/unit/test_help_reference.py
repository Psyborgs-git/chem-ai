"""The Help exporter must cover assembly drift without running application code."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "help_reference_exporter", ROOT / "infra/ci/export_help_reference.py"
)
assert SPEC and SPEC.loader
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def write(root: Path, path: str, text: str) -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)


@pytest.fixture
def route_repo(tmp_path: Path) -> Path:
    write(
        tmp_path,
        f"{exporter.API}/app.py",
        """
from studio.api.example import router as examples
from studio.api.graphql.schema import graphql_app
from studio.api.desktop import mount_desktop_web
def create_app(settings):
    raise RuntimeError("MUST NEVER EXECUTE")
    @app.get("/healthz")
    def healthz(): return {"status": "ok"}
    @app.get("/readyz")
    def readyz(): return {"status": "ready"}
    app.include_router(examples, prefix="/api")
    app.include_router(graphql_app(settings), prefix="/graphql")
    mount_desktop_web(app, settings)
""",
    )
    write(
        tmp_path,
        f"{exporter.API}/example.py",
        """
router = APIRouter(prefix="/example")
@router.post("/{identifier}", status_code=201)
async def save(
    identifier: str, payload: dict[str, object], file: Annotated[UploadFile, File()],
    metadata: str = Form("{}")
) -> dict:
    return {"id": identifier}
""",
    )
    write(
        tmp_path,
        f"{exporter.API}/desktop.py",
        """
def mount_desktop_web(app, settings):
    if not settings.desktop_frontend_dir: return
    @app.get("/api/desktop/runtime", include_in_schema=False)
    def desktop_runtime(): return {"desktop": True}
    app.mount("/", DesktopWeb(root), name="desktop-web")
""",
    )
    return tmp_path


def test_static_assembly_covers_nested_probes_and_multipart(route_repo: Path) -> None:
    routes = {row["id"]: row for row in exporter.rest_inventory(route_repo)}
    assert set(routes) == {
        "GET /healthz",
        "GET /readyz",
        "GET /api/desktop/runtime",
        "POST /api/example/{identifier}",
    }
    assert routes["GET /api/desktop/runtime"]["condition"] == "desktop frontend enabled"
    saved = routes["POST /api/example/{identifier}"]
    assert saved["status"] == 201
    assert [p["in"] for p in saved["parameters"]] == ["path", "JSON body", "multipart", "multipart"]


def test_unresolved_registration_fails_instead_of_omitting(route_repo: Path) -> None:
    path = route_repo / exporter.API / "app.py"
    path.write_text(path.read_text() + "\napp.include_router(build_unknown_router())\n")
    with pytest.raises(ValueError, match="Unresolved router registration"):
        exporter.rest_inventory(route_repo)


def test_unregistered_router_and_new_decorator_fail(route_repo: Path) -> None:
    source = route_repo / exporter.API / "example.py"
    original = source.read_text()
    source.write_text(original + '\nother = APIRouter(prefix="/lost")\n')
    with pytest.raises(ValueError, match="not registered"):
        exporter.rest_inventory(route_repo)
    source.write_text(original.replace("@router.post(", "@router.api_route("))
    with pytest.raises(ValueError, match="Unclassified route decorator"):
        exporter.rest_inventory(route_repo)


def test_imperative_registration_requires_explicit_exporter_support(route_repo: Path) -> None:
    source = route_repo / exporter.API / "example.py"
    source.write_text(source.read_text() + '\nrouter.add_api_route("/hidden", endpoint)\n')
    with pytest.raises(ValueError, match="Unclassified imperative registration"):
        exporter.rest_inventory(route_repo)


def test_graphql_recurses_all_namespace_levels(tmp_path: Path) -> None:
    write(
        tmp_path,
        "packages/contracts/schema.graphql",
        """
scalar JSON
type Query { viewer: Viewer! }
type Viewer { id: ID! }
type Mutation { lab: LabMutation! direct(input: String = "x"): JSON }
type LabMutation { measurements: MeasurementMutation! }
type MeasurementMutation { record(input: Input!): Viewer! }
input Input { name: String! }
""",
    )
    operations, types = exporter.graphql_inventory(tmp_path)
    assert {row["id"] for row in operations} == {
        "query viewer",
        "mutation direct",
        "mutation lab.measurements.record",
    }
    direct = next(row for row in operations if row["path"] == "direct")
    assert '= "x"' in direct["signature"]
    assert {row["name"] for row in types} >= {"JSON", "Input", "MeasurementMutation"}


def test_environment_inventory_never_resolves_values_and_prunes(
    tmp_path: Path, monkeypatch
) -> None:
    write(tmp_path, "services/config.py", 'value = os.getenv("STUDIO_EXAMPLE")\n')
    write(tmp_path, "apps/studio-web/vite.config.ts", "process.env.VITE_EXAMPLE")
    write(tmp_path, "infra/local/dev.sh", "${UV_CACHE_DIR:-/tmp/cache}\n")
    write(tmp_path, "tests/e2e/serve.sh", "export STUDIO_TEST_EXAMPLE=1\n")
    write(tmp_path, "apps/studio-web/node_modules/secret.py", "STUDIO_SHOULD_NOT_APPEAR")
    write(tmp_path, "apps/studio-web/src-tauri/target/secret.py", "STUDIO_SHOULD_NOT_APPEAR")
    write(tmp_path, "Makefile", "UV ?= uv\n")
    monkeypatch.setenv("STUDIO_EXAMPLE", "sensitive-value-never-export")
    inventory = exporter.environment_inventory(tmp_path)
    assert {row["id"] for row in inventory} == {
        "STUDIO_EXAMPLE",
        "STUDIO_TEST_EXAMPLE",
        "VITE_EXAMPLE",
        "UV_CACHE_DIR",
        "UV",
    }
    assert "sensitive-value-never-export" not in json.dumps(inventory)


def test_missing_stale_or_unfinished_metadata_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"missing=.*new"):
        exporter.require_coverage([{"id": "new"}], {}, "test")
    with pytest.raises(ValueError, match=r"stale=.*old"):
        exporter.require_coverage([], {"old": {"summary": "Old"}}, "test")
    with pytest.raises(ValueError, match="Unfinished"):
        exporter.require_coverage([{"id": "new"}], {"new": {"summary": "TODO"}}, "test")


def test_query_metadata_uses_wire_alias_and_actual_required_default() -> None:
    module = exporter.ast.parse("""
def endpoint(
    ident: str,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
    q: str = Query(default="", max_length=200),
    optional: int | None = None,
): pass
""")
    parameters = exporter.route_parameters(module.body[0], "/api/pages/{ident}")
    by_name = {parameter["name"]: parameter for parameter in parameters}
    assert by_name["expectedRevision"]["required"] is True
    assert by_name["expectedRevision"]["python_name"] == "expected_revision"
    assert by_name["q"]["required"] is False
    assert by_name["optional"]["required"] is False


def test_reviewed_examples_require_correct_wire_queries() -> None:
    route = {
        "id": "DELETE /api/pages/{ident}",
        "method": "DELETE",
        "path": "/api/pages/{ident}",
        "parameters": [{"name": "expectedRevision", "in": "query", "required": True}],
    }
    example = {
        "requestExample": "DELETE /api/pages/example HTTP/1.1",
        "successExample": 'HTTP/1.1 200 OK\n\n{"deleted":true}',
        "failureExample": 'HTTP/1.1 409 Conflict\n\n{"errors":[]}',
        "failureWhen": "An outdated revision was supplied.",
    }
    with pytest.raises(ValueError, match="missing required query expectedRevision"):
        exporter.validate_rest_examples([route], {route["id"]: example})
    example["requestExample"] = "DELETE /api/pages/example?expectedRevision=1 HTTP/1.1"
    exporter.validate_rest_examples([route], {route["id"]: example})


def test_reviewed_examples_file_is_mandatory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        exporter.load_rest_examples(tmp_path, [{"id": "GET /required"}])
    write(tmp_path, "docs/reference-source/rest-examples.json", "{}")
    with pytest.raises(ValueError, match="coverage differs"):
        exporter.load_rest_examples(tmp_path, [{"id": "GET /required"}])


def test_contract_anchors_match_help_heading_slugs() -> None:
    assert exporter.anchor("LibraryService._record") == "libraryservice_record"
    assert exporter.anchor("Mutation contracts") == "mutation-contracts"


def test_check_detects_drift_without_writing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(exporter, "render", lambda root: {"one.md": "# One\n"})
    assert exporter.export(tmp_path, check=True) == ["one.md"]
    assert not (tmp_path / exporter.OUTPUT).exists()
    assert exporter.export(tmp_path) == ["one.md"]
    assert exporter.export(tmp_path, check=True) == []
    target = tmp_path / exporter.OUTPUT / "one.md"
    target.write_text("drift\n")
    assert exporter.export(tmp_path, check=True) == ["one.md"]
    assert target.read_text() == "drift\n"


def test_generated_reference_is_current_and_complete() -> None:
    assert exporter.export(ROOT, check=True) == []
    inventory = json.loads((ROOT / exporter.OUTPUT / "inventory.json").read_text())
    ids = {row["id"] for row in inventory["rest"]}
    assert {"GET /healthz", "GET /readyz", "GET /api/desktop/runtime"} <= ids
    assert len(inventory["rest"]) >= 92
    assert any(row["path"] == "lab.measurements.measurementRecord" for row in inventory["graphql"])
    assert any(row["id"] == "STUDIO_VAULT_ROOT" for row in inventory["environment"])
