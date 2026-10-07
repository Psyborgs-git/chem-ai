"""PAR-07 — registry search feeds + formulations mutation group.

The operator workflows land on real queries: searchable
identity/grade/reference-product/family feeds and the
formulations.* mutations that wrap FormulationService. Raw uuid
entry is never the normal path — pickers resolve names to
canonical GlobalIDs through these connections.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient
from strawberry import relay

from studio.api.app import create_app
from studio.config.settings import Settings
from studio.persistence.models import Workspace

pytestmark = pytest.mark.integration

HEADERS = {"origin": "http://127.0.0.1:8787", "host": "127.0.0.1:8787"}


def _client(db_url: str) -> TestClient:
    return TestClient(create_app(Settings(database_url=db_url)))


def _setup_owner(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/setup",
        json={
            "login": "owner",
            "display_name": "Owner",
            "password": "correct horse battery staple",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text


def _gql(client: TestClient, query: str, variables: dict[str, Any] | None = None) -> Any:
    resp = client.post(
        "/graphql",
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _gid(type_name: str, row_id: str | uuid.UUID) -> str:
    return str(relay.GlobalID(type_name=type_name, node_id=str(row_id)))


def _fraction(v: str) -> dict[str, object]:
    return {
        "value": v,
        "unit": "mass_fraction",
        "basis": "as_supplied",
        "original_text": v,
    }


def _complete_payload(lines: list[dict[str, object]]) -> dict[str, object]:
    return {
        "completeness": "complete",
        "amountBasis": "as_supplied",
        "declaredTotal": "1",
        "tolerance": "0.001",
        "ingredients": lines,
    }


class TestRegistrySearch:
    """Name-keyed search over identities / grades / products / families."""

    def _identity(self, client: TestClient, name: str, cas: str) -> str:
        key = f"itest-{uuid.uuid4()}"
        out = _gql(
            client,
            """mutation($n: String!, $cas: JSON!, $key: String) { materials {
              identityCreate(input: {kind: "defined_molecule", name: $n,
                identifiers: $cas, idempotencyKey: $key}) {
                identity { id name } errors { message } } } }""",
            {"n": name, "cas": [{"scheme": "cas", "value": cas}], "key": key},
        )
        errs = out["data"]["materials"]["identityCreate"]["errors"]
        assert errs == [], errs
        return out["data"]["materials"]["identityCreate"]["identity"]["id"]

    def test_identity_search_by_name_and_identifier(
        self, db_url: str, session: Session
    ) -> None:
        client = _client(db_url)
        _setup_owner(client)
        self._identity(client, "citric acid", "77-92-9")
        self._identity(client, "sodium bicarbonate", "144-55-8")

        by_name = _gql(
            client,
            'query($s: String) { materialIdentities(search: $s) '
            "{ edges { node { id name structureStatus } } } }",
            {"s": "citric"},
        )
        assert "errors" not in by_name, by_name
        names = [e["node"]["name"] for e in by_name["data"]["materialIdentities"]["edges"]]
        assert names == ["citric acid"]

        by_cas = _gql(
            client,
            'query($s: String) { materialIdentities(search: $s) { edges { node { name } } } }',
            {"s": "144-55"},
        )
        assert "errors" not in by_cas, by_cas
        names = [e["node"]["name"] for e in by_cas["data"]["materialIdentities"]["edges"]]
        assert names == ["sodium bicarbonate"]

    def test_reference_product_search_and_revision_feed(
        self, db_url: str, session: Session
    ) -> None:
        client = _client(db_url)
        _setup_owner(client)
        out = _gql(
            client,
            """mutation($key: String) { materials { referenceProductCreate(input: {
              name: "Acme Cleaner", supplier: "Acme", category: "cleaner",
              idempotencyKey: $key }) { product { id name } errors { message } } } }""",
            {"key": f"rp-{uuid.uuid4()}"},
        )
        assert out["data"]["materials"]["referenceProductCreate"]["errors"] == []
        pid = out["data"]["materials"]["referenceProductCreate"]["product"]["id"]

        found = _gql(
            client,
            'query($s: String) { referenceProducts(search: $s) '
            "{ edges { node { id name compositionKnowledge } } } }",
            {"s": "acme"},
        )
        assert "errors" not in found, found
        prods = found["data"]["referenceProducts"]["edges"]
        assert [e["node"]["name"] for e in prods] == ["Acme Cleaner"]
        assert prods[0]["node"]["compositionKnowledge"] == "unknown"

        # draft + freeze a revision through materials.*; read it back
        draft = _gql(
            client,
            """mutation($p: ID!, $key: String) { materials { referenceRevisionDraft(input: {
              productId: $p, payload: {compositionKnowledge: "unknown",
                composition: null}, idempotencyKey: $key }) {
              revision { id revision status } errors { message } } } }""",
            {"p": pid, "key": f"rrd-{uuid.uuid4()}"},
        )
        assert draft["data"]["materials"]["referenceRevisionDraft"]["errors"] == []
        rid = draft["data"]["materials"]["referenceRevisionDraft"]["revision"]["id"]
        froz = _gql(
            client,
            'mutation($r: ID!) { materials { referenceRevisionFreeze(input: {revisionId: $r}) '
            "{ revision { status } errors { message } } } }",
            {"r": rid},
        )
        assert froz["data"]["materials"]["referenceRevisionFreeze"]["errors"] == []

        feed = _gql(
            client,
            'query($p: ID!) { referenceProductRevisions(productId: $p) '
            "{ edges { node { revision status payload } } } }",
            {"p": pid},
        )
        assert "errors" not in feed, feed
        revs = feed["data"]["referenceProductRevisions"]["edges"]
        assert len(revs) == 1
        assert revs[0]["node"]["status"] == "frozen"
        assert revs[0]["node"]["payload"]["compositionKnowledge"] == "unknown"

    def test_search_is_workspace_scoped(self, db_url: str, session: Session) -> None:
        """A foreign workspace's registry never leaks into results."""
        client = _client(db_url)
        _setup_owner(client)
        self._identity(client, "citric acid", "77-92-9")
        ws_b = Workspace(slug="ws-b", display_name="B")
        session.add(ws_b)
        session.commit()
        out = _gql(client, '{ materialIdentities(search: "citric") { edges { node { name } } } }')
        assert len(out["data"]["materialIdentities"]["edges"]) == 1


class TestFormulationsMutation:
    """formulations.* — the structured editor's write path (PAR-07)."""

    def _family(self, client: TestClient, name: str) -> str:
        key = f"fam-{uuid.uuid4()}"
        out = _gql(
            client,
            'mutation($n: String!, $key: String) { formulations { familyCreate(input: {name: $n, '
            'idempotencyKey: $key}) { family { id name } errors { message } } } }',
            {"n": name, "key": key},
        )
        assert out["data"]["formulations"]["familyCreate"]["errors"] == []
        return out["data"]["formulations"]["familyCreate"]["family"]["id"]

    def test_family_draft_accept_and_process_roundtrip(
        self, db_url: str, session: Session
    ) -> None:
        client = _client(db_url)
        _setup_owner(client)
        fid = self._family(client, "base coating")

        draft = _gql(
            client,
            """mutation($f: ID!, $p: JSON!, $key: String) { formulations { revisionDraft(input: {
              familyId: $f, payload: $p, idempotencyKey: $key }) {
              revision { id revision status payload familyName }
              errors { message fieldPath } } } }""",
            {
                "f": fid,
                "key": f"rd-{uuid.uuid4()}",
                "p": _complete_payload(
                    [
                        {"name": "water", "amount": _fraction("0.6"), "role": "solvent"},
                        {"name": "resin A", "amount": _fraction("0.4"), "role": "binder"},
                    ]
                ),
            },
        )
        assert draft["data"]["formulations"]["revisionDraft"]["errors"] == []
        rev = draft["data"]["formulations"]["revisionDraft"]["revision"]
        assert rev["status"] == "draft"
        assert rev["familyName"] == "base coating"
        assert len(rev["payload"]["ingredients"]) == 2

        accepted = _gql(
            client,
            'mutation($r: ID!) { formulations { revisionAccept(input: {revisionId: $r}) '
            "{ revision { id status } errors { message } } } }",
            {"r": rev["id"]},
        )
        assert accepted["data"]["formulations"]["revisionAccept"]["errors"] == []
        assert (
            accepted["data"]["formulations"]["revisionAccept"]["revision"]["status"]
            == "accepted"
        )

        proc = _gql(
            client,
            """mutation($f: ID!, $p: JSON!, $key: String) { formulations { processDraft(input: {
              familyId: $f, payload: $p, idempotencyKey: $key }) {
              revision { id revision status payload } errors { message } } } }""",
            {
                "f": fid,
                "key": f"pd-{uuid.uuid4()}",
                "p": {
                    "steps": [
                        {"order": 1, "action": "disperse", "equipment": "stirrer"},
                        {"order": 2, "action": "bake", "conditions": {"temp": "80 degC"}},
                    ]
                },
            },
        )
        assert proc["data"]["formulations"]["processDraft"]["errors"] == []
        proc_id = proc["data"]["formulations"]["processDraft"]["revision"]["id"]
        acc = _gql(
            client,
            'mutation($r: ID!) { formulations { processAccept(input: {revisionId: $r}) '
            "{ revision { status } errors { message } } } }",
            {"r": proc_id},
        )
        assert acc["data"]["formulations"]["processAccept"]["revision"]["status"] == "accepted"

        feed = _gql(
            client,
            'query($f: ID!) { formulationRevisions(familyId: $f) '
            "{ edges { node { revision status familyName } } } "
            "processRevisions(familyId: $f) { edges { node { revision status } } } }",
            {"f": fid},
        )
        assert "errors" not in feed, feed
        assert feed["data"]["formulationRevisions"]["edges"][0]["node"]["status"] == "accepted"
        assert feed["data"]["processRevisions"]["edges"][0]["node"]["status"] == "accepted"

    def test_draft_records_malformed_quantity_as_finding(
        self, db_url: str, session: Session
    ) -> None:
        """Drafts may be incomplete: a malformed amount is a stored
        finding, never a silent fix and never a wire-level error."""
        client = _client(db_url)
        _setup_owner(client)
        fid = self._family(client, "bad payload")
        out = _gql(
            client,
            """mutation($f: ID!, $p: JSON!) { formulations { revisionDraft(input: {
              familyId: $f, payload: $p }) {
              revision { id status payload } errors { code message fieldPath } } } }""",
            {
                "f": fid,
                "p": {"ingredients": [{"name": "water", "amount": {"value": "x"}}]},
            },
        )
        res = out["data"]["formulations"]["revisionDraft"]
        assert res is not None, out
        assert res["errors"] == [], res["errors"]
        kinds = [f["kind"] for f in res["revision"]["payload"]["validationFindings"]]
        assert "invalid_amount" in kinds
        # and it still can't be accepted — the gate holds
        rej = _gql(
            client,
            'mutation($r: ID!) { formulations { revisionAccept(input: {revisionId: $r}) '
            "{ revision { status } errors { code message } } } }",
            {"r": res["revision"]["id"]},
        )
        acc = rej["data"]["formulations"]["revisionAccept"]
        assert acc["errors"] and acc["errors"][0]["code"] == "VALIDATION"

    def test_fraction_range_check_uses_canonical_value(
        self, db_url: str, session: Session
    ) -> None:
        """mass_percent amounts are canonically [0,1] fractions — a valid
        70% recipe must not flag; a genuinely out-of-range 1.5 must."""
        client = _client(db_url)
        _setup_owner(client)
        ok = self._family(client, "valid percent")
        good = _gql(
            client,
            'mutation($f: ID!, $p: JSON!) { formulations { revisionDraft(input: {familyId: $f, '
            'payload: $p}) { revision { payload } errors { message } } } }',
            {
                "f": ok,
                "p": {
                    "ingredients": [
                        {
                            "name": "water",
                            "amount": {
                                "value": "70",
                                "unit": "mass_percent",
                                "basis": "as_supplied",
                            },
                        }
                    ]
                },
            },
        )
        findings = good["data"]["formulations"]["revisionDraft"]["revision"]["payload"][
            "validationFindings"
        ]
        assert not any(f["kind"] == "fraction_out_of_range" for f in findings), findings

        bad = self._family(client, "bad percent")
        over = _gql(
            client,
            'mutation($f: ID!, $p: JSON!) { formulations { revisionDraft(input: {familyId: $f, '
            'payload: $p}) { revision { payload } errors { message } } } }',
            {
                "f": bad,
                "p": {
                    "ingredients": [
                        {
                            "name": "water",
                            "amount": {
                                "value": "150",
                                "unit": "mass_percent",
                                "basis": "as_supplied",
                            },
                        }
                    ]
                },
            },
        )
        findings = over["data"]["formulations"]["revisionDraft"]["revision"]["payload"][
            "validationFindings"
        ]
        flagged = [f for f in findings if f["kind"] == "fraction_out_of_range"]
        assert len(flagged) == 1
        assert "1.5" in flagged[0]["detail"]

    def test_parent_must_share_family(self, db_url: str, session: Session) -> None:
        client = _client(db_url)
        _setup_owner(client)
        fa = self._family(client, "fam-a")
        fb = self._family(client, "fam-b")
        d = _gql(
            client,
            'mutation($f: ID!, $p: JSON!) { formulations { revisionDraft(input: {familyId: $f, '
            'payload: $p}) { revision { id } errors { message } } } }',
            {"f": fa, "p": _complete_payload([{"name": "w", "amount": _fraction("1")}])},
        )
        parent = d["data"]["formulations"]["revisionDraft"]["revision"]["id"]
        out = _gql(
            client,
            'mutation($f: ID!, $p: JSON!, $par: ID) { formulations { revisionDraft(input: {'
            'familyId: $f, payload: $p, parentRevisionId: $par}) { revision { id } '
            "errors { message fieldPath } } } }",
            {
                "f": fb,
                "p": _complete_payload([{"name": "w", "amount": _fraction("1")}]),
                "par": parent,
            },
        )
        errs = out["data"]["formulations"]["revisionDraft"]["errors"]
        assert errs and "different family" in errs[0]["message"]

    def test_cross_family_revision_search(self, db_url: str, session: Session) -> None:
        """The baseline picker feeds on this: family name match returns
        the revision with its family label attached."""
        client = _client(db_url)
        _setup_owner(client)
        fid = self._family(client, "epoxy primer")
        _gql(
            client,
            'mutation($f: ID!, $p: JSON!) { formulations { revisionDraft(input: {familyId: $f, '
            'payload: $p}) { revision { id } errors { message } } } }',
            {"f": fid, "p": _complete_payload([{"name": "w", "amount": _fraction("1")}])},
        )
        _gql(
            client,
            'mutation($f: ID!, $p: JSON!) { formulations { revisionDraft(input: {familyId: $f, '
            'payload: $p}) { revision { id } errors { message } } } }',
            {"f": fid, "p": _complete_payload([{"name": "w2", "amount": _fraction("1")}])},
        )
        out = _gql(
            client,
            'query($s: String) { formulationRevisions(search: $s) '
            "{ edges { node { revision status familyName } } } }",
            {"s": "epoxy"},
        )
        assert "errors" not in out, out
        edges = out["data"]["formulationRevisions"]["edges"]
        assert len(edges) == 2
        assert {e["node"]["revision"] for e in edges} == {1, 2}
        assert all(e["node"]["familyName"] == "epoxy primer" for e in edges)
