"""
FraudMLScorer — thin wrapper around sklearn IsolationForest.

Run this file directly to generate / regenerate the toy model:
  python model/scorer.py
"""
from __future__ import annotations

import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent / "fraud_v1.pkl"


# ── Feature extraction ────────────────────────────────────────────────────────

def _extract_features(ctx) -> np.ndarray:
    """
    Returns a 1-D float32 array of 6 features:
      [log1p(amount), hour/24, dow/7, is_international, merchant_age/365, 0.5]
    """
    amount = getattr(ctx, "amount", 1)
    ip = getattr(ctx, "ip_address", "") or ""
    pan6 = getattr(ctx, "pan_first6", None) or ""
    mca = getattr(ctx, "merchant_created_at", None)

    # hour of day (IST)
    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    hour_norm = ist.hour / 24.0
    dow_norm = ist.weekday() / 7.0

    # international card heuristic
    from rules.engine import _is_international_bin, _is_indian_ip
    is_intl = 1.0 if (pan6 and _is_international_bin(pan6) and _is_indian_ip(ip)) else 0.0

    # merchant age
    if mca:
        ts = mca if mca.tzinfo is None else mca.replace(tzinfo=None)
        age_days = max((datetime.utcnow() - ts).days, 0)
    else:
        age_days = 365  # assume established if unknown

    return np.array(
        [
            float(np.log1p(amount)),
            hour_norm,
            dow_norm,
            is_intl,
            min(age_days / 365.0, 5.0),
            0.5,  # placeholder for customer txn count
        ],
        dtype=np.float32,
    )


# ── Scorer class ──────────────────────────────────────────────────────────────

class FraudMLScorer:
    def __init__(self, model_path: Path = _MODEL_PATH) -> None:
        if not model_path.exists():
            log.warning("ML model not found at %s — generating toy model", model_path)
            generate_toy_model(model_path)

        with open(model_path, "rb") as f:
            self._model = pickle.load(f)
        log.info("FraudMLScorer loaded from %s", model_path)

    def extract_features(self, ctx) -> np.ndarray:
        return _extract_features(ctx)

    def predict(self, ctx) -> float:
        """
        Returns a fraud score in [0.0, 1.0].
        IsolationForest.decision_function: higher = more normal, lower = more anomalous.
        We invert and shift so that 0 = definitely normal, 1 = definitely anomalous.
        """
        features = self.extract_features(ctx).reshape(1, -1)
        raw: float = float(self._model.decision_function(features)[0])
        # IsolationForest returns values roughly in [-0.5, 0.5]
        # Invert: anomalous (negative) → high fraud score
        score = float(np.clip(raw * -1 + 0.5, 0.0, 1.0))
        return score


# ── Toy model generation ──────────────────────────────────────────────────────

def generate_toy_model(save_path: Path = _MODEL_PATH) -> None:
    """
    Train an IsolationForest on synthetic 'normal' transaction data and save.
    Called automatically if fraud_v1.pkl is missing.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required: pip install scikit-learn") from exc

    rng = np.random.default_rng(42)
    n = 20_000

    # Synthetic normal transactions:
    # - Amounts log-normally distributed (small to medium)
    # - Daytime heavy
    # - Mostly domestic
    # - Established merchants
    X = np.column_stack([
        rng.exponential(5.0, n),                         # log1p(amount)
        np.clip(rng.normal(0.55, 0.2, n), 0, 1),         # hour (daytime)
        rng.integers(0, 7, n) / 7.0,                     # day of week
        rng.binomial(1, 0.08, n).astype(float),          # is_international (rare)
        np.clip(rng.beta(5, 1, n), 0, 5),                # merchant age (old)
        np.full(n, 0.5),                                  # placeholder
    ]).astype(np.float32)

    model = IsolationForest(
        n_estimators=100,
        max_samples=256,
        contamination=0.05,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X)

    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        pickle.dump(model, f, protocol=5)

    print(f"Toy fraud model saved → {save_path}")


if __name__ == "__main__":
    generate_toy_model()
