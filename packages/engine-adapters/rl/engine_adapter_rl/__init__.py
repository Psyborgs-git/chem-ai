"""RL trainer contracts — pure schema, no trainer deps (§19, CS-0902).

``contracts`` stays importable on the host without torch/trl; the
training implementation itself (``trainer``/``pico_rl``/``rollout``)
only runs inside the pinned ``workers/training/rl/trainer``
environment.
"""

from engine_adapter_rl.contracts import (
    RL_ARCHITECTURES,
    RL_MODEL_LICENSES,
    RlAdapterConfig,
    RlAlgorithmSpec,
    RlCheckpoint,
    RlCheckpointPolicy,
    RlEpisodeSummary,
    RlModelSpec,
    RlOptimizerSpec,
    RlOutcome,
    RlParameterProof,
    RlResourceEnvelope,
    RlResumeSpec,
    RlRolloutBudget,
    RlRolloutSpec,
    RlTrainSpec,
    TrainerFailure,
)

__all__ = [
    "RL_ARCHITECTURES",
    "RL_MODEL_LICENSES",
    "RlAdapterConfig",
    "RlAlgorithmSpec",
    "RlCheckpoint",
    "RlCheckpointPolicy",
    "RlEpisodeSummary",
    "RlModelSpec",
    "RlOptimizerSpec",
    "RlOutcome",
    "RlParameterProof",
    "RlResourceEnvelope",
    "RlResumeSpec",
    "RlRolloutBudget",
    "RlRolloutSpec",
    "RlTrainSpec",
    "TrainerFailure",
]
