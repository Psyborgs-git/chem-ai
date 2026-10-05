"""SFT trainer contracts — pure schema, no trainer deps (§17.4, CS-0801).

``contracts`` stays importable on the host without torch/peft; the
training implementation itself (``trainer``/``pico``) only runs inside
the pinned ``workers/training/sft`` environment.
"""

from engine_adapter_sft.contracts import (
    SftAdapterConfig,
    SftCheckpoint,
    SftCheckpointPolicy,
    SftModelSpec,
    SftOptimizerSpec,
    SftOutcome,
    SftResourceEnvelope,
    SftResumeSpec,
    SftTrainingExample,
    SftTrainSpec,
    TrainerFailure,
)

__all__ = [
    "SftAdapterConfig",
    "SftCheckpoint",
    "SftCheckpointPolicy",
    "SftModelSpec",
    "SftOptimizerSpec",
    "SftOutcome",
    "SftResourceEnvelope",
    "SftResumeSpec",
    "SftTrainSpec",
    "SftTrainingExample",
    "TrainerFailure",
]
