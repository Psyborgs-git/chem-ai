"""Controlled RL for research decisions (CS-0901, §19).

``environment/`` holds the bounded replay/computational environment —
reset/step/terminate, approved typed tools, replay provenance and hard
budgets enforced independently of the model. ``rewards/`` holds the
separate reward service: eligibility gates outside the performance
trade-off plus versioned measurable components with provenance.
"""
