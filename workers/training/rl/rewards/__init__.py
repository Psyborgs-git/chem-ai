"""Reward service for the RL environment (CS-0901, §19.3).

Separate from the policy: it consumes the immutable episode trace the
environment recorded and writes component-level records with
provenance. Eligibility gates sit outside the performance trade-off.
It has no API that can reach the held-out promotion suite or the
evaluation label store — reward inputs arrive only as explicit,
already-sanctioned task bundles.
"""
