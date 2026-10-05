# engine_adapter_analytics — selected analytical-data processing (CS-0703)

Pure-stdlib adapter for instrument-export ingest and scoped reference
comparison (handoff §16.5). No science dependencies, no container
runner — parsing/preprocessing/similarity are deterministic in-process
numerics.

## Selected export formats

| format    | content | parser version      |
|-----------|---------|---------------------|
| jcamp-dx  | JCAMP-DX ASCII AFFN tables: `##XYDATA`/`##XYPOINTS`/`##DATA TABLE`/`##PEAK TABLE` in `(X..Y)`, `(XY..XY)` or `(X++(Y..Y))` form | `jcampdx-reader/v1` |
| csv-xy    | generic two-column `x,y` delimiter-separated export (`,`/`;`/tab, optional preamble) | `csvxy-reader/v1` |

Anything else is **unsupported**: detection returns `None`, ingest
stores the raw export with provenance and marks interpretation
`unsupported` (AT-0703-3). Compressed JCAMP encodings (DIFDUP/SQUEEZED)
raise `ANALYTICS_UNSUPPORTED_ENCODING` rather than being guessed.

## Versioned pipeline

- preprocessing: `baseline_offset` → `baseline-offset/v1`,
  `minmax_normalize` → `minmax-normalize/v1`,
  `moving_average` → `moving-average/v1`
- alignment: `resample_linear` → `resample-linear/v1` (uniform grid over
  the shared x overlap; non-overlapping traces cannot be compared)
- similarity: `cosine` → `cosine-similarity/v1`,
  `pearson` → `pearson-correlation/v1`

Every transform records kind + pinned version + parameters on the
result — never implied.

## Scoped similarity (§16.5)

`compare` refuses cross-method and cross-x-unit pairs and returns a
`ScopedSimilarity`: algorithm + version + applied x range + aligned
point count + interpretation limits travel with the value. The value
is **not** evidence of identical composition, recipe, or molecular
identity (`scientific_status="not_composition_evidence"`); analytical
and functional evidence are compared separately.
