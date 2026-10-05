"""Independent evaluation workers (CS-0803, §18.1-18.4).

The *harness* is real and deterministic: versioned suite contracts,
matched base-vs-adapted comparison on identical tasks/budget/tool
pins, honest scoring, safety/privacy regression detection. The
*model-under-test* is an injectable backend — when no local runtime
is installed the backend reports honest unavailability and no scores
are fabricated (fixture-only data is labelled, never marketed).
"""
