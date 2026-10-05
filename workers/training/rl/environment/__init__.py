"""Bounded research RL environment (CS-0901, §19.2).

Computational/replay-based only — no physical experiment autonomy
(§19.1). The environment pins task, contract and reward versions plus
the evidence-snapshot digest at ``reset`` and keeps them frozen for
the whole episode.
"""
