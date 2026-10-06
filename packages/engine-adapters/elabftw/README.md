# engine_adapter_elabftw — optional eLabFTW bridge (CS-0506)

Explicit, opt-in ELN connector. **Chemistry Studio is authoritative**
for its native records; this package never performs bidirectional
synchronization. It offers:

- **export** — one-way Studio -> eLabFTW payload assembly
  (`LocalExportRecord` -> eLabFTW API v2 create/patch body, with studio
  provenance embedded in `metadata.extra_fields.studio_provenance`),
- **selective import** — read one linked entity at a time and compare
  against the link's version/hash baseline (`modified_at` +
  `remote_fingerprint()`),
- **conflict/disconnect handling** — drift routes to
  `review_required` (never a silent overwrite, either direction);
  unreachable remote yields `unavailable`/`stale` with local evidence
  intact.

## Configuration (all optional, off by default — U16)

| Env | Meaning |
|---|---|
| `STUDIO_ELN_BASE_URL` | instance URL, e.g. `https://eln.example.org` |
| `STUDIO_ELN_API_TOKEN` | API key (sent as `Authorization: <key>`); never defaulted/logged/echoed |
| `STUDIO_ELN_ENABLED` | explicit enable; without it a configured endpoint still refuses (`configured_disabled`) |
| `STUDIO_ELN_TIMEOUT_SECONDS` | request timeout (default 10) |
| `STUDIO_ELN_VERIFY_TLS` | `0` disables TLS verification (default on) |

With nothing set, `ElabftwAdapter().capability()` reports
`not_configured` and no remote surface exists. **No live eLabFTW call
was ever made in this release** — tests exercise the real code path
through `FixtureElnTransport` (in-process double serving recorded
API-v2 responses from `tests/fixtures/`). `HttpElnTransport` is the
real wire client (stdlib urllib) and is constructed only when the
connector is enabled.

## Layout

```
engine_adapter_elabftw/
  contracts.py   ElnConfig, ElnEntityRecord (API v2 shape), ElnLink,
                 verdicts, typed ElnError {code,message}
  transport.py   ElnTransport protocol; HttpElnTransport (live, opt-in);
                 FixtureElnTransport (double: canned entities, call log,
                 go_offline()/mutate_entity() levers)
  mapping.py     entity parse/fingerprint + export payload assembly +
                 load_fixture()
  adapter.py     ElabftwAdapter: capability(), import_entity(),
                 export_record(), link_status(), resolve_review()
tests/fixtures/  recorded eLabFTW v2 responses (labelled fixtures)
```

See `docs/operations/eln.md` for the ownership model and `docs/
execution/tickets/CS-0506.md` for acceptance evidence.
