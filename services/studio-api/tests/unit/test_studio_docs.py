"""Static manuals remain bounded, allowlisted and usable by both agent paths."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session

from studio.application import studio_docs
from studio.application.agent_tools import registry, turn
from studio.application.studio_docs import (
    DOCS_GUIDANCE,
    MAX_RESULT_BYTES,
    StudioDocumentation,
    documentation_bundle_files,
    parse_headings,
)
from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.agent_workspace import runtime, tools
from studio.domain.agent_workspace.workflows import PUBLIC_TOOLS, WorkflowService
from studio.errors import DomainError, ErrorCode


def write_manifest(root: Path, text: str, **changes: Any) -> Path:
    docs = root / "docs/usage"
    docs.mkdir(parents=True, exist_ok=True)
    article = docs / "first.md"
    article.write_text(text)
    manifest = {
        "version": 1,
        "articles": [
            {
                "section": "usage",
                "slug": "first",
                "title": "Using the Studio",
                "summary": "Edit notes and start learning.",
                "source": "docs/usage/first.md",
                "order": 1,
                **changes,
            }
        ],
    }
    (root / "docs/help-manifest.json").write_text(json.dumps(manifest))
    return article


@pytest.fixture
def manual(tmp_path: Path) -> StudioDocumentation:
    write_manifest(
        tmp_path,
        "# Using the Studio\n\n## Edit notes\n\nClick Save after editing.\n"
        "\n## Start learning\n\nFreeze a dataset before training.\n",
    )
    (tmp_path / "docs/usage/private.md").write_text("# NEVER EXPOSE THIS UNREGISTERED FILE\n")
    return StudioDocumentation(tmp_path)


def context() -> ServiceContext:
    return ServiceContext(
        session=Session(),
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        principal_kind="agent",
        grants=frozenset(),
    )


def test_search_read_and_heading_scope_have_stable_help_links(manual: StudioDocumentation) -> None:
    hit = manual.search("Edit notes")["results"][0]
    assert hit["article_id"] == "usage/first"
    assert hit["url"] == "/help/usage/first#edit-notes"
    assert hit["article_url"] == "/help/usage/first"
    assert str(manual.root) not in json.dumps(hit)
    read = manual.read(hit["article_id"], heading=hit["heading"]["id"])
    assert "Click Save" in read["text"]
    assert "Freeze a dataset" not in read["text"]
    assert read["next_offset"] is None
    assert len(read["content_sha256"]) == 64
    assert manual.search("NEVER EXPOSE")["results"] == []


@pytest.mark.parametrize(
    "identifier", ["../private", "/etc/passwd", "usage/../first", "usage/private"]
)
def test_read_cannot_select_unregistered_or_arbitrary_files(manual, identifier) -> None:
    with pytest.raises(DomainError):
        manual.read(identifier)


@pytest.mark.parametrize(
    "source",
    [
        "../secret.md",
        "/etc/passwd",
        "docs/usage/../secret.md",
        "services/studio-api/src/studio/errors.py",
    ],
)
def test_manifest_paths_fail_closed_without_leaking_local_paths(tmp_path, source) -> None:
    write_manifest(tmp_path, "# Public\n", source=source)
    with pytest.raises(DomainError) as caught:
        StudioDocumentation(tmp_path).search("Public")
    assert caught.value.code == ErrorCode.ENGINE_UNAVAILABLE
    assert str(tmp_path) not in caught.value.message


def test_symlinked_article_and_manifest_are_rejected(tmp_path: Path) -> None:
    article = write_manifest(tmp_path, "# Public\n")
    secret = tmp_path / "private.md"
    secret.write_text("# PRIVATE SECRET\n")
    article.unlink()
    article.symlink_to(secret)
    with pytest.raises(DomainError):
        StudioDocumentation(tmp_path).read("usage/first")
    article.unlink()
    article.write_text("# Public\n")
    path = tmp_path / "docs/help-manifest.json"
    target = tmp_path / "manifest.json"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(DomainError):
        StudioDocumentation(tmp_path).read("usage/first")


def test_headings_ignore_fenced_examples_and_match_collision_rules() -> None:
    markdown = """# Public

```markdown
# Hidden heading
```
~~~
## Also hidden
~~~
## **Edit** `notes` and [links](./first.md)
## Edit notes and links
## Edit-notes-and-links-1
## Edit notes and links
## Café  数据
## LibraryService._record
"""
    headings = parse_headings(markdown)
    assert [heading.id for heading in headings] == [
        "public",
        "edit-notes-and-links",
        "edit-notes-and-links-1",
        "edit-notes-and-links-1-1",
        "edit-notes-and-links-2",
        "café--数据",
        "libraryservice_record",
    ]
    assert headings[1].text == "Edit notes and links"


def test_cache_refreshes_after_a_canonical_article_changes(manual) -> None:
    assert manual.search("Freshly updated")["results"] == []
    path = manual.root / "docs/usage/first.md"
    path.write_text("# Using the Studio\n\n## Freshly updated\n\nUpdated steps.\n")
    assert manual.search("Freshly updated")["results"][0]["url"].endswith("#freshly-updated")


def test_unicode_read_windows_and_heading_pages_fit_both_dispatchers(tmp_path: Path) -> None:
    text = "# 文档\n" + "\n".join(f"## 段落{number}\n" + "数" * 6000 for number in range(30))
    write_manifest(tmp_path, text)
    service = StudioDocumentation(tmp_path)
    first = service.read("usage/first", max_chars=6000)
    assert len(json.dumps(first).encode()) <= MAX_RESULT_BYTES + 100
    assert first["truncated"] is True and first["next_offset"] > 0
    second = service.read(
        "usage/first",
        offset=first["next_offset"],
        max_chars=6000,
        heading_offset=first["next_heading_offset"],
    )
    assert first["text"] + second["text"] == text[: first["next_offset"] + len(second["text"])]
    assert first["headings"][-1]["id"] != second["headings"][0]["id"]
    assert first["heading_count"] == 31


def test_supplementary_unicode_metadata_and_overlong_anchors_are_bounded(tmp_path: Path) -> None:
    character = "\U00010400"
    write_manifest(
        tmp_path,
        f"# Public\n\n## Section\n{character * 6000}\n",
        title=character * 300,
        summary=character * 1000,
    )
    service = StudioDocumentation(tmp_path)
    result = service.read("usage/first", heading="section", max_chars=6000)
    assert len(json.dumps(result).encode()) <= MAX_RESULT_BYTES
    assert len(json.dumps(service.search("Section")).encode()) <= MAX_RESULT_BYTES
    write_manifest(tmp_path, f"# Public\n\n## {character * 1024}\nExample\n")
    with pytest.raises(DomainError) as caught:
        service.read("usage/first", max_chars=1)
    assert caught.value.code == ErrorCode.ENGINE_UNAVAILABLE


def test_direct_search_does_not_accept_unbounded_surrounding_whitespace(manual) -> None:
    with pytest.raises(DomainError):
        manual.search(" " * 1000 + "notes")


def test_text_cursor_progress_does_not_depend_on_advancing_the_heading_cursor(
    tmp_path: Path,
) -> None:
    character = "\U00010400"
    text = "# Public\n" + "".join(
        f"\n## {character * 95}{number}\nSmall body.\n" for number in range(12)
    )
    write_manifest(tmp_path, text, title=character * 300, summary=character * 876 + "a")
    service = StudioDocumentation(tmp_path)
    offset, reconstructed = 0, ""
    while offset < len(text):
        page = service.read("usage/first", offset=offset, max_chars=6000)
        assert page["text"]
        assert len(json.dumps(page).encode()) <= MAX_RESULT_BYTES
        reconstructed += page["text"]
        if not page["truncated"]:
            assert page["next_offset"] is None
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert reconstructed == text


@pytest.mark.parametrize(
    "method,arguments",
    [
        ("search", {"query": " "}),
        ("search", {"query": "x", "limit": 100}),
        ("search", {"query": "x", "limit": True}),
        ("read", {"article_id": "usage/first", "offset": -1}),
        ("read", {"article_id": "usage/first", "max_chars": 100000}),
        ("read", {"article_id": "usage/first", "heading": "missing"}),
    ],
)
def test_bounds_and_missing_heading_are_typed_failures(manual, method, arguments) -> None:
    with pytest.raises(DomainError):
        getattr(manual, method)(**arguments)


def test_missing_docs_are_a_safe_unavailable_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_studio_documentation", lambda: StudioDocumentation(tmp_path))
    ctx = context()
    result = registry.ToolDispatcher(ctx.session, ctx).call("search_studio_docs", {"query": "help"})
    assert result["error"]["code"] == "ENGINE_UNAVAILABLE"
    assert str(tmp_path) not in json.dumps(result)


def test_same_tools_execute_in_task_global_and_workflow_catalogs(manual, monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_studio_documentation", lambda: manual)
    ctx = context()
    task_result = registry.ToolDispatcher(ctx.session, ctx, task_id=uuid.uuid4()).call(
        "search_studio_docs", {"query": "Edit notes"}
    )
    assert task_result["ok"] is True and task_result["untrusted"] is True
    hit = task_result["data"]["results"][0]
    private_result = tools.execute(
        ctx.session,
        ctx,
        Settings(),
        "read_studio_doc",
        {"article_id": hit["article_id"], "heading": hit["heading"]["id"]},
    )
    assert private_result["ok"] is True
    assert private_result["data"]["url"] == hit["url"]
    descriptor = {tool["name"] for tool in tools.catalog()}
    assert {"search_studio_docs", "read_studio_doc"} <= descriptor & PUBLIC_TOOLS
    workflow = WorkflowService(ctx.session, ctx)
    assert workflow.authorize_tool(None, "search_studio_docs", {"query": "help"}) == {
        "query": "help"
    }
    invalid = registry.ToolDispatcher(ctx.session, ctx).call(
        "read_studio_doc", {"article_id": "usage/first", "path": "/private/file"}
    )
    assert invalid["error"]["code"] == "INVALID_INPUT"


def test_both_prompts_teach_docs_first_and_separate_live_state(monkeypatch) -> None:
    ctx = context()
    task = SimpleNamespace(id=uuid.uuid4(), title="Synthetic task", mode="discover")
    monkeypatch.setattr(turn, "TaskMemoryService", lambda *_: SimpleNamespace(_task=lambda _: task))
    runner = turn.AgentTurnRunner(ctx.session, ctx)
    task_prompt = runner._prompt(uuid.uuid4(), task.id, "How do I edit a note?")[0]["content"]
    assert DOCS_GUIDANCE in task_prompt
    monkeypatch.setattr(
        runtime,
        "AgentWorkspaceService",
        lambda *_: SimpleNamespace(
            _owned=lambda *_: SimpleNamespace(task_id=None, notebook_id=None)
        ),
    )
    from studio.domain.library import service as library

    monkeypatch.setattr(
        library,
        "LibraryService",
        lambda *_args, **_kwargs: SimpleNamespace(
            active_memory=lambda: [], search=lambda *_args, **_kwargs: []
        ),
    )
    monkeypatch.setattr(runtime, "workflow_for_run", lambda *_: None)
    run = SimpleNamespace(
        role="planner",
        prompt="How do I edit a note?",
        provider_id=None,
        checkpoint={"localModelId": "synthetic-model"},
        thread_id=uuid.uuid4(),
        workspace_id=ctx.workspace_id,
        owner_id=ctx.principal_id,
        id=uuid.uuid4(),
    )
    db = SimpleNamespace(scalars=lambda *_: [])
    private_prompt = runtime._prompt(db, run, ctx, Settings(), [])[0]["content"]
    assert DOCS_GUIDANCE in private_prompt


def test_wheel_mapping_is_exact_allowlist_and_packaged_lookup_works(
    manual, tmp_path, monkeypatch
) -> None:
    mapping = documentation_bundle_files(manual.root)
    assert set(mapping.values()) == {
        "studio/_bundled_help/docs/help-manifest.json",
        "studio/_bundled_help/docs/usage/first.md",
    }
    target = tmp_path / "installed/site-packages"
    for source, destination in mapping.items():
        path = target / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Path(source).read_bytes())
    monkeypatch.setattr(studio_docs, "__file__", str(target / "studio/application/studio_docs.py"))
    packaged = studio_docs.get_studio_documentation()
    assert packaged.read("usage/first")["article_url"] == "/help/usage/first"


def test_current_canonical_corpus_is_available_without_workspace_data() -> None:
    service = studio_docs.get_studio_documentation()
    result = service.search("STUDIO_VAULT_ROOT", section="reference")
    assert any(hit["article_id"] == "reference/configuration" for hit in result["results"])
    article = service.read("usage/learning-and-models", max_chars=100)
    assert article["url"] == "/help/usage/learning-and-models"
