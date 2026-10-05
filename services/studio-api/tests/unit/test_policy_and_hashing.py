"""Unit tests — pure policy vocabulary and revision hashing (no DB)."""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import (
    ALL_CAPABILITIES,
    APPROVAL_CAPABILITIES,
    CAP_APPROVE_EXPERIMENT,
    CAP_PROPOSE_CANDIDATE,
    CAP_READ_PROJECT,
    Grant,
    capabilities_for_role,
    effective_grants,
    has_capability,
)

from studio.api.security import _host_allowed, _origin_allowed
from studio.config.settings import Settings
from studio.persistence.revisions import canonical_json, content_hash


class TestCapabilityVocabulary:
    def test_vocabulary_matches_spec(self) -> None:
        # §21.1 lists exactly 13 capabilities.
        assert len(ALL_CAPABILITIES) == 13
        assert APPROVAL_CAPABILITIES <= ALL_CAPABILITIES

    def test_agent_role_has_no_approvals(self) -> None:
        assert capabilities_for_role("agent") & APPROVAL_CAPABILITIES == frozenset()

    def test_owner_has_all(self) -> None:
        assert capabilities_for_role("owner") == ALL_CAPABILITIES

    def test_unknown_role_empty(self) -> None:
        assert capabilities_for_role("nonexistent") == frozenset()

    def test_viewer_is_read_only(self) -> None:
        assert capabilities_for_role("viewer") == frozenset({CAP_READ_PROJECT})


class TestGrantChecks:
    def test_workspace_wide_grant_covers_any_scope(self) -> None:
        grants = frozenset({Grant(CAP_PROPOSE_CANDIDATE)})
        assert has_capability(grants, CAP_PROPOSE_CANDIDATE, "task:1")
        assert has_capability(grants, CAP_PROPOSE_CANDIDATE, None)

    def test_scoped_grant_only_covers_that_scope(self) -> None:
        grants = frozenset({Grant(CAP_PROPOSE_CANDIDATE, scope_ref="task:1")})
        assert has_capability(grants, CAP_PROPOSE_CANDIDATE, "task:1")
        assert not has_capability(grants, CAP_PROPOSE_CANDIDATE, "task:2")
        assert not has_capability(grants, CAP_PROPOSE_CANDIDATE, None)

    def test_unknown_capability_never_granted(self) -> None:
        grants = frozenset({Grant("fly_to_moon")})
        assert not has_capability(grants, "fly_to_moon")

    def test_agent_ceiling_strips_direct_approval_grant(self) -> None:
        grants = frozenset({Grant(CAP_APPROVE_EXPERIMENT), Grant(CAP_READ_PROJECT)})
        effective = effective_grants("agent", grants)
        assert {g.capability for g in effective} == {CAP_READ_PROJECT}

    def test_user_grants_unchanged(self) -> None:
        grants = frozenset({Grant(CAP_APPROVE_EXPERIMENT)})
        assert effective_grants("user", grants) == grants


class TestCanonicalHashing:
    def test_key_order_does_not_change_hash(self) -> None:
        a = {"x": 1, "y": [1, 2], "z": {"b": 2, "a": 1}}
        b = {"z": {"a": 1, "b": 2}, "y": [1, 2], "x": 1}
        assert content_hash(a) == content_hash(b)

    def test_hash_is_sha256_hex(self) -> None:
        h = content_hash({"a": 1})
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)

    def test_payload_change_changes_hash(self) -> None:
        assert content_hash({"a": 1}) != content_hash({"a": 2})

    def test_canonical_json_deterministic(self) -> None:
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


class TestLoopbackGuards:
    @pytest.fixture()
    def settings(self) -> Settings:
        return Settings()

    def test_loopback_hosts_allowed(self, settings: Settings) -> None:
        assert _host_allowed("127.0.0.1:8787", settings)
        assert _host_allowed("localhost:8787", settings)
        assert _host_allowed("[::1]:8787", settings)

    def test_foreign_hosts_denied(self, settings: Settings) -> None:
        assert not _host_allowed("studio.evil.example", settings)
        assert not _host_allowed("192.168.1.5:8787", settings)  # LAN off
        assert not _host_allowed(None, settings)
        assert not _host_allowed("", settings)

    def test_origin_rules(self, settings: Settings) -> None:
        assert _origin_allowed(None, settings)  # non-browser client
        assert _origin_allowed("null", settings)  # sandboxed frame
        assert _origin_allowed("http://127.0.0.1:8787", settings)
        assert not _origin_allowed("https://attacker.example", settings)
        # Look-alike origins must not pass.
        assert not _origin_allowed("http://127.0.0.1:8787.evil.example", settings)
        assert not _origin_allowed("http://127.0.0.1:9999", settings)
