# config.py — Centralised scoring configuration for Greyhound Analytics

# ---------------------------------------------------------------------------
# Distance-adaptive feature weights
# Keys must match the feature names used in compute_features()
# ---------------------------------------------------------------------------

SPRINT_WEIGHTS = {  # < 400 m
    "ClassRating":      0.20,
    "FormRating":       0.20,
    "BoxAdvantage":     0.15,
    "RecentFormBoost":  0.12,
    "DLWFactor":        0.10,
    "AgeFactor":        0.08,
    "RTCFactor":        0.05,
    "ExperienceFactor": 0.05,
    "OverexposedPenalty": 0.05,
}

MIDDLE_WEIGHTS = {  # 400–500 m
    "ClassRating":      0.20,
    "FormRating":       0.20,
    "BoxAdvantage":     0.08,
    "RecentFormBoost":  0.12,
    "DLWFactor":        0.10,
    "AgeFactor":        0.08,
    "RTCFactor":        0.07,
    "ExperienceFactor": 0.08,
    "OverexposedPenalty": 0.07,
}

LONG_WEIGHTS = {  # > 500 m
    "ClassRating":      0.20,
    "FormRating":       0.25,
    "BoxAdvantage":     0.05,
    "RecentFormBoost":  0.12,
    "DLWFactor":        0.10,
    "AgeFactor":        0.08,
    "RTCFactor":        0.07,
    "ExperienceFactor": 0.08,
    "OverexposedPenalty": 0.05,
}

# ---------------------------------------------------------------------------
# Box-draw advantage lookup  (box number → bonus by distance category)
# Positive = advantage, negative = disadvantage
# ---------------------------------------------------------------------------

BOX_BIAS = {
    "sprint": {1: 1.5, 2: 1.2, 3: 0.3, 4: 0.0, 5: 0.0, 6: -0.3, 7: -1.0, 8: -1.2, 9: -1.0, 10: -1.2},
    "middle": {1: 0.8, 2: 0.6, 3: 0.2, 4: 0.0, 5: 0.0, 6: -0.2, 7: -0.5, 8: -0.6, 9: -0.5, 10: -0.6},
    "long":   {1: 0.5, 2: 0.3, 3: 0.1, 4: 0.0, 5: 0.0, 6: -0.1, 7: -0.3, 8: -0.4, 9: -0.3, 10: -0.4},
}

# ---------------------------------------------------------------------------
# Trifecta confidence tiers
# ---------------------------------------------------------------------------

TRIFECTA_TIERS = [
    {"min_score": 42, "min_sep": 3.0, "tier": "Tier 1", "bet": True},
    {"min_score": 40, "min_sep": 2.0, "tier": "Tier 2", "bet": True},
    {"min_score": 38, "min_sep": 1.5, "tier": "Tier 3", "bet": False},
]
TRIFECTA_DEFAULT_TIER = {"tier": "Tier 4", "bet": False}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

OVEREXPOSED_STARTS = 80        # Career starts above which a penalty applies
EXPERIENCE_CAP_STARTS = 30     # Starts at which experience factor maxes out
