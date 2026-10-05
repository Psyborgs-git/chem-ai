# Chemistry Studio — canonical design map

`design-map.json` is the canonical mapping between stable logical
IDs (from handoff §22.2/§22.3) and real code + tests.

## Status

`design_status` is **`logical-specification-only`**. No Figma file
was supplied or created. Every `figma_node_id` is `null`; any later
Figma design must either map onto these stable IDs or go through a
reviewed migration. No pixel-parity claims may be added.

## Rules

- `screen_id` values are the §22.2 required screen families; their
  `status` moves `not_started → implemented` as routes land.
- `component_id` values are the §22.3 atoms/molecules/state
  vocabulary; `implemented` entries must have an existing
  `code_path`, and `test_path` where a test exists.
- Validation: `tests/unit/test_design_map.py` enforces schema,
  file existence, null figma IDs, and absence of parity language.
