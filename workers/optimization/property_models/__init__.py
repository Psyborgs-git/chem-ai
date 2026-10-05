"""Property models, calibration and applicability (CS-0604, §15.3, §18.2).

Baselines first: ``evaluate_property_model`` always scores the matched
mean/median baselines on the same held-out examples before any
molecular model. The Chemprop path is a different representation
(MPNN on SMILES) that lives only inside the pinned worker image —
see ``chemprop/``.
"""

from .applicability import ApplicabilityAssessor, ApplicabilityVerdict
from .calibration import SplitConformalCalibrator
from .evaluation import evaluate_property_model
from .linear import RidgeRegressor
from .predictor import PropertyPredictor, RowPrediction
from .readiness import assess_readiness
from .transforms import CATEGORICAL, NUMERIC, FeatureSpec, FeatureVectorizer, RowFlags

__all__ = [
    "CATEGORICAL",
    "NUMERIC",
    "ApplicabilityAssessor",
    "ApplicabilityVerdict",
    "FeatureSpec",
    "FeatureVectorizer",
    "PropertyPredictor",
    "RidgeRegressor",
    "RowFlags",
    "RowPrediction",
    "SplitConformalCalibrator",
    "assess_readiness",
    "evaluate_property_model",
]
