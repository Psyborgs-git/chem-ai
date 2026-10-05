# Synthetic fixtures — provenance (AT-0003-3)

Every file here is **synthetic** and copied verbatim from the handoff
package (`docs/chemistry-studio/fixtures/`), whose `index.json`
declares: "All data synthetic. References illustrate interchange, not a
complete populated database. No real chemistry validation or
manufacturing recipe."

- `fixture_only: true` on every object is the load-bearing marker.
- `invalid-*.json` files are **expected to fail** validation per
  `index.json` (`expected_valid: false`); do not "fix" them.
- Thresholds inside fixtures are software-test tolerances, never
  scientific claims (contracts/README.md).
- UUID references are illustrative; they are not a coherent seed set.
  The demo loader (P02) creates referenced entities in an isolated
  workspace and keeps everything visibly synthetic.
- Nothing here is a real recipe, measurement, or laboratory result.
