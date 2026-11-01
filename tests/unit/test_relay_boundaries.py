"""Reviewed local UI persistence must not open a server-cache/transport escape."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "relay_boundaries", ROOT / "infra/ci/check_relay_boundaries.py"
)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

ACTIVE_KEY = 'const activeKey = (scope: string) => `studio.agent.activeThread:${scope}`;'
DRAFT_KEYS = '''
const PREFIX = "chemistry-studio:private-notebook-draft:";
const key = (ownerKey: string, pageId: string) =>
  `${PREFIX}${encodeURIComponent(ownerKey)}:${pageId}`;
'''


def write(src: Path, name: str, text: str) -> None:
    path = src / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_selected_thread_id_expressions_pass_without_exempting_the_sidebar(tmp_path):
    write(tmp_path, str(checker.AGENT_SIDEBAR), ACTIVE_KEY + '''
const saved = localStorage.getItem(activeKey(ownerScope));
localStorage.setItem(activeKey(ownerScope), threadId);
localStorage.removeItem(activeKey(ownerScope));
''')
    assert checker.check(tmp_path) == []
    with (tmp_path / checker.AGENT_SIDEBAR).open("a") as file:
        file.write('localStorage.setItem(activeKey(ownerScope), JSON.stringify(messages));\n')
    findings = checker.check(tmp_path)
    assert len(findings) == 1 and "browser-storage" in findings[0]


@pytest.mark.parametrize(
    "storage",
    [
        'localStorage.setItem("server-cache", JSON.stringify(records));',
        'localStorage.getItem("unscoped-thread");',
        "localStorage.removeItem(otherKey);",
        "window.localStorage.getItem(activeKey(ownerScope));",
        "sessionStorage.setItem(activeKey(ownerScope), threadId);",
        "indexedDB.open('server-records');",
    ],
)
def test_even_a_line_with_an_allowed_sidebar_call_still_rejects_other_storage(tmp_path, storage):
    write(
        tmp_path,
        str(checker.AGENT_SIDEBAR),
        ACTIVE_KEY + "\nlocalStorage.getItem(activeKey(ownerScope)); " + storage,
    )
    assert any("browser-storage" in finding for finding in checker.check(tmp_path))


def test_sidebar_allowance_depends_on_the_owner_scoped_key_helper_and_exact_module(tmp_path):
    code = ACTIVE_KEY + "\nlocalStorage.setItem(activeKey(ownerScope), threadId);"
    write(tmp_path, "features/other/AgentSidebar.tsx", code)
    assert checker.check(tmp_path)
    (tmp_path / "features/other/AgentSidebar.tsx").unlink()
    write(
        tmp_path,
        str(checker.AGENT_SIDEBAR),
        code.replace("studio.agent.activeThread:${scope}", "studio.agent.activeThread:global"),
    )
    assert checker.check(tmp_path)


def test_owner_page_drafts_and_prefix_filtered_cleanup_are_the_only_draft_storage(tmp_path):
    write(tmp_path, str(checker.NOTEBOOK_DRAFTS), DRAFT_KEYS + '''
const draft = sessionStorage.getItem(key(ownerKey, pageId));
sessionStorage.setItem(key(ownerKey, pageId), JSON.stringify(value));
sessionStorage.removeItem(key(ownerKey, pageId));
for (let index = sessionStorage.length - 1; index >= 0; index--) {
  const name = sessionStorage.key(index);
  if (name?.startsWith(PREFIX)) sessionStorage.removeItem(name);
}
''')
    assert checker.check(tmp_path) == []
    with (tmp_path / checker.NOTEBOOK_DRAFTS).open("a") as file:
        file.write('sessionStorage.setItem("server-cache", JSON.stringify(serverResponse));\n')
    assert any("browser-storage" in finding for finding in checker.check(tmp_path))


@pytest.mark.parametrize(
    "change",
    [
        ('${encodeURIComponent(ownerKey)}:${pageId}', '${pageId}'),
        ('name?.startsWith(PREFIX)', 'name'),
        ('sessionStorage.setItem', 'localStorage.setItem'),
    ],
)
def test_draft_owner_key_or_cleanup_boundary_changes_require_review(tmp_path, change):
    code = DRAFT_KEYS + '''
sessionStorage.setItem(key(ownerKey, pageId), JSON.stringify(value));
for (let index = sessionStorage.length - 1; index >= 0; index--) {
  const name = sessionStorage.key(index);
  if (name?.startsWith(PREFIX)) sessionStorage.removeItem(name);
}
'''
    write(tmp_path, str(checker.NOTEBOOK_DRAFTS), code.replace(*change))
    assert checker.check(tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "features/Example.test.tsx",
        "features/Example.spec.ts",
        "features/__tests__/storage.ts",
        "features/__fixtures__/storage.ts",
        "features/__mocks__/storage.ts",
        "__generated__/query.graphql.ts",
    ],
)
def test_tests_fixtures_and_generated_artifacts_do_not_count_as_production(tmp_path, name):
    write(tmp_path, name, 'localStorage.clear(); fetch("/graphql"); new Environment();')
    assert checker.source_files(tmp_path) == []
    assert checker.check(tmp_path) == []


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ('fetch("/graphql");', "GraphQL transport"),
        ("new Environment({});", "Relay Environment"),
        ('import {useQuery} from "@tanstack/react-query";', "second server-state cache"),
    ],
)
@pytest.mark.parametrize(
    "module", ["features/agent/AgentSidebar.tsx", "features/notebooks/drafts.ts"]
)
def test_persistence_modules_still_obey_every_other_boundary(tmp_path, code, message, module):
    write(tmp_path, module, ACTIVE_KEY + DRAFT_KEYS + code)
    assert any(message in finding for finding in checker.check(tmp_path))


def test_transport_and_environment_exemptions_are_scoped_to_exact_files_and_rules(tmp_path):
    write(tmp_path, "relay/network.ts", 'fetch("/graphql");')
    write(tmp_path, "relay/environment.ts", "new Environment({});")
    assert checker.check(tmp_path) == []
    write(
        tmp_path, "relay/network.ts", 'fetch("/graphql"); localStorage.setItem("cache", records);'
    )
    write(tmp_path, "features/elsewhere/network.ts", 'fetch("/graphql");')
    findings = checker.check(tmp_path)
    assert any("browser-storage" in finding for finding in findings)
    assert any("GraphQL transport" in finding for finding in findings)


def test_actual_production_tree_keeps_the_reviewed_boundaries():
    assert checker.check(ROOT / "apps/studio-web/src") == []
