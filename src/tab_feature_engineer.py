"""
Feature Engineering — transforms raw runner data into the 74 columns
expected by the pre-trained .pkl venue models.

The 74 features are defined in MODEL_FEATURES below (extracted from the
scaler.feature_names_in_ attribute of the trained StandardScaler files).

Feature tiers:
  Tier 1 (Direct)    — mapped directly from CSV/API fields
  Tier 2 (Derived)   — computed from Tier 1 using formulae from src/features.py
  Tier 3 (Composite) — field-level stats and scored composites (FinalScore)

Public API:
  engineer_features(df) → pd.DataFrame  (74 feature columns + metadata)
"""

import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

AEST = timezone(timedelta(hours=10))

# The exact 74 features expected by the pkl models, in order.
# Extracted from scaler.feature_names_in_ (identical across all 3 venue scalers).
MODEL_FEATURES = [
    "Box", "Weight", "Draw", "CareerWins", "CareerPlaces", "CareerStarts",
    "PrizeMoney", "RTC", "DLR", "DLW", "Distance", "BestTimeSec",
    "SectionalSec", "BoxBiasFactor", "TrackConditionAdj", "RestFactor",
    "Speed_kmh", "EarlySpeedIndex", "FinishConsistency", "MarginAvg",
    "FormMomentum", "ConsistencyIndex", "RecentFormBoost", "DistanceSuit",
    "TrainerStrikeRate", "OverexposedPenalty", "PlaceRate", "DLWFactor",
    "WeightFactor", "DrawFactor", "FormMomentumNorm", "MarginFactor",
    "RTCFactor", "BoxPositionBias", "BoxPlaceRate", "BoxTop3Rate",
    "TrackBox1Adjustment", "TrackBox4Adjustment",
    "TrackComprehensiveAdjustment", "AgeMonths", "AgeFactor",
    "RailPreference", "BoxPenaltyFactor", "SpeedAtDistance",
    "SpeedClassification", "ExperienceTier", "WinStreakFactor",
    "FreshnessFactor", "ClassRating", "GradeFactor", "Last3AvgFinish",
    "Last3FinishFactor", "DistanceChangeFactor", "PaceBoxFactor",
    "TrainerTier", "FreshnessFactorV2", "AgeFactorV2",
    "SurfacePreferenceFactor", "WinPlaceRate", "EarlySpeedPercentile",
    "BestTimePercentile", "FieldSpeedStd", "FieldTimeStd",
    "FieldSimilarityIndex", "TrackUpsetFactor", "CompetitorDensity",
    "CompetitorAdjustment", "FieldSize", "FieldSizeAdjustment",
    "WinStreakFactorV2", "RecentPlaceStreak", "CloserBonus",
    "TrainerMomentum", "FinalScore",
]

# Grade mapping: grade string → numeric value (higher = better class)
GRADE_MAP = {
    "maiden": 1,
    "grade 7": 2, "7": 2,
    "grade 6": 3, "6": 3,
    "grade 5": 4, "5": 4,
    "grade 4": 5, "4": 5,
    "grade 3": 5, "3": 5,
    "grade 2": 6, "2": 6,
    "grade 1": 6, "1": 6,
    "mixed": 4, "mixed 6/7": 3, "mixed 5/6": 4,
    "restricted win": 3,
    "ffa": 7, "free for all": 7,
    "open": 8,
    "invitation": 8,
}


def _grade_to_num(grade_str):
    """Map a grade string to a numeric class rating."""
    if pd.isna(grade_str) or not isinstance(grade_str, str):
        return 4  # default mid-grade
    g = grade_str.strip().lower()
    if g in GRADE_MAP:
        return GRADE_MAP[g]
    # Partial match
    for key in sorted(GRADE_MAP.keys(), key=len, reverse=True):
        if key in g:
            return GRADE_MAP[key]
    try:
        return int(g)
    except ValueError:
        return 4


def _parse_pir(pir_str):
    """
    Parse PIR (positions in running) string into list of ints.

    '3211' → [3, 2, 1, 1]
    '876'  → [8, 7, 6]
    ''     → []
    """
    if pd.isna(pir_str) or not isinstance(pir_str, str):
        return []
    positions = []
    for ch in str(pir_str).strip():
        if ch.isdigit():
            positions.append(int(ch))
    return positions


def _parse_last_starts(starts_str):
    """
    Parse last starts string into list of finishing positions.

    '12341' → [1, 2, 3, 4, 1]
    'F8x12' → [8, 8, 1, 2]  (F→8, x=scratch→skip)
    """
    if pd.isna(starts_str) or not isinstance(starts_str, str):
        return []
    positions = []
    for ch in str(starts_str).strip():
        if ch.isdigit() and ch != "0":
            positions.append(int(ch))
        elif ch.upper() == "F":
            positions.append(8)
        # skip x, X, 0 (scratched)
    return positions


def _generic_box_advantage(box, dist_m):
    """Statistical box advantage by distance category (from scorer.py)."""
    box = int(box) if not pd.isna(box) else 1
    dist_m = float(dist_m) if not pd.isna(dist_m) else 350

    if dist_m <= 350:
        adv = {1: 0.18, 2: 0.15, 3: 0.12, 4: 0.11, 5: 0.10,
               6: 0.09, 7: 0.10, 8: 0.13, 9: 0.05, 10: 0.05}
    elif dist_m <= 450:
        adv = {1: 0.16, 2: 0.13, 3: 0.12, 4: 0.11, 5: 0.11,
               6: 0.11, 7: 0.12, 8: 0.12, 9: 0.05, 10: 0.05}
    else:
        adv = {1: 0.14, 2: 0.12, 3: 0.12, 4: 0.12, 5: 0.12,
               6: 0.12, 7: 0.12, 8: 0.12, 9: 0.05, 10: 0.05}
    return adv.get(box, 0.08)


def _compute_final_score(row):
    """
    Compute FinalScore using the distance-dependent weighted composite
    formula from src/features.py.
    """
    distance = row.get("Distance", 350)

    if distance < 400:  # Sprint
        weights = {
            "EarlySpeedIndex": 0.30, "Speed_kmh": 0.20,
            "ConsistencyIndex": 0.10, "FinishConsistency": 0.05,
            "PrizeMoney": 0.10, "RecentFormBoost": 0.10,
            "BoxBiasFactor": 0.10, "TrainerStrikeRate": 0.05,
            "DistanceSuit": 0.05, "TrackConditionAdj": 0.05,
        }
    elif distance <= 500:  # Middle
        weights = {
            "EarlySpeedIndex": 0.25, "Speed_kmh": 0.20,
            "ConsistencyIndex": 0.15, "FinishConsistency": 0.05,
            "PrizeMoney": 0.10, "RecentFormBoost": 0.10,
            "BoxBiasFactor": 0.05, "TrainerStrikeRate": 0.05,
            "DistanceSuit": 0.05, "TrackConditionAdj": 0.05,
        }
    else:  # Long
        weights = {
            "EarlySpeedIndex": 0.20, "Speed_kmh": 0.15,
            "ConsistencyIndex": 0.20, "FinishConsistency": 0.10,
            "PrizeMoney": 0.10, "RecentFormBoost": 0.10,
            "BoxBiasFactor": 0.05, "TrainerStrikeRate": 0.05,
            "DistanceSuit": 0.05, "TrackConditionAdj": 0.05,
        }

    score = 0.0
    for feat, w in weights.items():
        val = row.get(feat, 0)
        if pd.isna(val):
            val = 0
        # PrizeMoney is scaled down in the original features.py
        if feat == "PrizeMoney":
            val = val / 1000.0
        score += val * w

    score += row.get("OverexposedPenalty", 0)
    return score


def engineer_features(df):
    """
    Transform raw runner data into the 74-column feature matrix expected
    by the pkl models.

    Parameters
    ----------
    df : pd.DataFrame
        Raw runner data from csv_ingest or tab_api. Must have columns like
        dog_name, box, weight, distance, time, win_time, bon, first_split,
        margin, pir, sp, date, grade, run_sequence, etc.
        Multiple rows per dog (one per form line) with run_sequence=1 being
        the most recent.

    Returns
    -------
    pd.DataFrame
        One row per dog with exactly 74 MODEL_FEATURES columns plus
        metadata columns (dog_name, venue, race_number, dog_number).
    """
    if df.empty:
        logger.warning("Empty input DataFrame — returning empty features")
        cols = MODEL_FEATURES + ["dog_name", "venue", "race_number", "dog_number"]
        return pd.DataFrame(columns=cols)

    today = datetime.now(AEST)

    # Group by dog: aggregate form lines into per-dog features
    # Each dog identified by (venue, race_number, dog_name, dog_number)
    dog_groups = df.groupby(
        ["venue", "race_number", "dog_name", "dog_number"],
        dropna=False,
    )

    records = []
    for (venue, race_num, dog_name, dog_num), group in dog_groups:
        # Sort by run_sequence (1=most recent)
        group = group.sort_values("run_sequence")
        n_runs = len(group)
        first_run = group.iloc[0]  # most recent run

        # ── Tier 1: Direct fields ────────────────────────────────────
        box = _safe_num(first_run.get("box"), 5)
        weight = _safe_num(first_run.get("weight"), 0.0)
        distance = _safe_num(first_run.get("distance"), 350)
        grade = first_run.get("grade", "")

        # Collect times from form lines
        times = group["time"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()
        win_times = group["win_time"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()
        bons = group["bon"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()
        splits = group["first_split"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()
        margins = group["margin"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()
        sps = group["sp"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()
        weights = group["weight"].apply(lambda x: _safe_num(x, np.nan)).dropna().tolist()

        # Parse placings from PIR or PLC
        placings = []
        for _, run in group.iterrows():
            pir_positions = _parse_pir(run.get("pir", ""))
            if pir_positions:
                placings.append(pir_positions[-1])  # final position

        # Career stats (estimated from form data)
        career_starts = max(n_runs, 1)
        career_wins = sum(1 for p in placings if p == 1)
        career_places = sum(1 for p in placings if p <= 3)

        # Best time
        best_time = min(times) if times else _estimate_time(distance)
        best_split = min(splits) if splits else _estimate_split(distance)
        avg_time = np.mean(times) if times else _estimate_time(distance)

        # Days since last run
        dates = group["date"].dropna()
        dlr = 14  # default
        dlw = 60  # default
        if len(dates) > 0:
            try:
                last_date = pd.to_datetime(dates.iloc[0])
                if pd.notna(last_date):
                    dlr = max(0, (today - last_date.to_pydatetime().replace(
                        tzinfo=AEST)).days)
            except Exception:
                pass
            # Estimate DLW from wins in form
            if career_wins > 0:
                dlw = dlr * career_starts / max(career_wins, 1)
            else:
                dlw = dlr + 60

        prize_money = 0.0  # not available from CSV, default

        # RTC (runs to complete — estimated from career)
        rtc = career_starts

        # ── Tier 2: Derived features ─────────────────────────────────

        # Speed
        speed_kmh = (distance / best_time) * 3.6 if best_time > 0 else 60.0
        early_speed_index = distance / best_split if best_split > 0 else 60.0

        # Consistency
        finish_consistency = np.std(times) if len(times) >= 2 else 0.1
        margin_avg = np.mean(margins) if margins else 0.0

        # Form momentum: trend in margins (negative = improving)
        form_momentum = 0.0
        if len(margins) >= 2:
            diffs = np.diff(margins)
            form_momentum = float(np.mean(diffs))

        # Rates
        consistency_index = career_wins / career_starts if career_starts > 0 else 0.0
        place_rate = career_places / career_starts if career_starts > 0 else 0.0
        win_place_rate = (career_wins + career_places) / career_starts if career_starts > 0 else 0.0

        # Box / Track factors
        box_bias = _generic_box_advantage(box, distance)
        track_condition_adj = 1.0
        rest_factor = _compute_rest_factor(dlr)

        # Recent form boost (from features.py)
        recent_form_boost = 0.0
        if dlr <= 5 and career_wins > 0:
            recent_form_boost = 1.0
        elif dlr <= 10:
            recent_form_boost = 0.5

        # Distance suitability
        distance_suit = 1.0 if distance in [515, 595] else 0.7

        # Trainer stats (not available from CSV)
        trainer_strike_rate = 0.15
        trainer_tier = 0.5
        trainer_momentum = 0.5

        # Overexposed penalty
        overexposed_penalty = -0.1 if career_starts > 80 else 0.0

        # DLW factor
        dlw_factor = max(0, 1.0 - dlw / 365)

        # Weight factor (penalty for far from 30kg ideal)
        weight_factor = 1.0 - abs(weight - 30.0) * 0.01 if weight > 0 else 0.5

        # Draw factor
        draw_factor = 1.0 - (box - 1) * 0.05 if box else 0.5

        # FormMomentumNorm (normalised later per-field)
        form_momentum_norm = 0.5

        # Margin factor
        margin_factor = max(0, 1.0 - margin_avg / 20.0) if not np.isnan(margin_avg) else 0.6

        # RTC factor
        rtc_factor = min(1.0, rtc / 10.0)

        # Box position bias (same as box advantage)
        box_position_bias = box_bias

        # Box place/top3 rates (not available per-box from CSV)
        box_place_rate = place_rate  # use overall as proxy
        box_top3_rate = min(1.0, place_rate * 1.2)

        # Track adjustments (neutral — no per-track data)
        track_box1_adj = 0.0
        track_box4_adj = 0.0
        track_comprehensive_adj = 0.0

        # Age (estimate from career starts)
        age_months = max(18, career_starts * 1.5 + 18)
        age_factor = min(1.0, max(0.3, 1.0 - abs(age_months - 30) * 0.01))

        # Rail preference (neutral)
        rail_preference = 0.5 if box <= 4 else 0.0
        box_penalty_factor = 0.0

        # Speed at distance
        speed_at_distance = speed_kmh * distance_suit

        # Speed classification
        if speed_kmh > 65:
            speed_classification = 1.0
        elif speed_kmh > 60:
            speed_classification = 0.5
        else:
            speed_classification = 0.0

        # Experience tier
        if career_starts >= 60:
            experience_tier = 1.0
        elif career_starts >= 30:
            experience_tier = 0.8
        elif career_starts >= 10:
            experience_tier = 0.6
        else:
            experience_tier = 0.3

        # Win streak (from placings)
        win_streak = 0
        for p in placings:
            if p == 1:
                win_streak += 1
            else:
                break
        win_streak_factor = min(1.0, win_streak * 0.3)

        # Freshness factor
        freshness = _compute_freshness(dlr)

        # Class rating
        class_rating = _grade_to_num(grade) / 8.0
        grade_factor = _grade_to_num(grade) / 7.0

        # Last 3 avg finish
        last3_finishes = placings[:3] if len(placings) >= 3 else placings
        last3_avg = np.mean(last3_finishes) if last3_finishes else 4.0
        last3_finish_factor = max(0, 1.0 - last3_avg / 8.0)

        # Distance change factor (neutral — no previous race distance from same dog)
        distance_change_factor = 0.0

        # Pace-box interaction
        pace_box_factor = early_speed_index * box_bias

        # FreshnessV2 / AgeV2
        freshness_v2 = freshness * 1.05  # slight variant
        age_factor_v2 = age_factor * 0.98  # slight variant

        # Surface preference (all greyhound tracks similar)
        surface_pref = 0.5

        # Recent place streak
        recent_place_streak = 0
        for p in placings:
            if p <= 3:
                recent_place_streak += 1
            else:
                break

        # Closer bonus (requires in-running data)
        closer_bonus = 0.0
        pir_positions = _parse_pir(first_run.get("pir", ""))
        if len(pir_positions) >= 2:
            if pir_positions[-1] < pir_positions[0]:
                closer_bonus = (pir_positions[0] - pir_positions[-1]) * 0.05

        # WinStreakFactorV2
        win_streak_v2 = min(1.0, win_streak * 0.25)

        # Build the feature record
        feat = {
            "Box": box,
            "Weight": weight,
            "Draw": box,  # greyhounds: draw == box
            "CareerWins": career_wins,
            "CareerPlaces": career_places,
            "CareerStarts": career_starts,
            "PrizeMoney": prize_money,
            "RTC": rtc,
            "DLR": dlr,
            "DLW": dlw,
            "Distance": distance,
            "BestTimeSec": best_time,
            "SectionalSec": best_split,
            "BoxBiasFactor": box_bias,
            "TrackConditionAdj": track_condition_adj,
            "RestFactor": rest_factor,
            "Speed_kmh": speed_kmh,
            "EarlySpeedIndex": early_speed_index,
            "FinishConsistency": finish_consistency,
            "MarginAvg": margin_avg,
            "FormMomentum": form_momentum,
            "ConsistencyIndex": consistency_index,
            "RecentFormBoost": recent_form_boost,
            "DistanceSuit": distance_suit,
            "TrainerStrikeRate": trainer_strike_rate,
            "OverexposedPenalty": overexposed_penalty,
            "PlaceRate": place_rate,
            "DLWFactor": dlw_factor,
            "WeightFactor": weight_factor,
            "DrawFactor": draw_factor,
            "FormMomentumNorm": form_momentum_norm,
            "MarginFactor": margin_factor,
            "RTCFactor": rtc_factor,
            "BoxPositionBias": box_position_bias,
            "BoxPlaceRate": box_place_rate,
            "BoxTop3Rate": box_top3_rate,
            "TrackBox1Adjustment": track_box1_adj,
            "TrackBox4Adjustment": track_box4_adj,
            "TrackComprehensiveAdjustment": track_comprehensive_adj,
            "AgeMonths": age_months,
            "AgeFactor": age_factor,
            "RailPreference": rail_preference,
            "BoxPenaltyFactor": box_penalty_factor,
            "SpeedAtDistance": speed_at_distance,
            "SpeedClassification": speed_classification,
            "ExperienceTier": experience_tier,
            "WinStreakFactor": win_streak_factor,
            "FreshnessFactor": freshness,
            "ClassRating": class_rating,
            "GradeFactor": grade_factor,
            "Last3AvgFinish": last3_avg,
            "Last3FinishFactor": last3_finish_factor,
            "DistanceChangeFactor": distance_change_factor,
            "PaceBoxFactor": pace_box_factor,
            "TrainerTier": trainer_tier,
            "FreshnessFactorV2": freshness_v2,
            "AgeFactorV2": age_factor_v2,
            "SurfacePreferenceFactor": surface_pref,
            "WinPlaceRate": win_place_rate,
            # Percentiles computed per-field below
            "EarlySpeedPercentile": 0.5,
            "BestTimePercentile": 0.5,
            # Field-level features computed per-race below
            "FieldSpeedStd": 0.0,
            "FieldTimeStd": 0.0,
            "FieldSimilarityIndex": 0.5,
            "TrackUpsetFactor": 0.0,
            "CompetitorDensity": 0.5,
            "CompetitorAdjustment": 1.0,
            "FieldSize": 8,
            "FieldSizeAdjustment": 0.0,
            "WinStreakFactorV2": win_streak_v2,
            "RecentPlaceStreak": recent_place_streak,
            "CloserBonus": closer_bonus,
            "TrainerMomentum": trainer_momentum,
            "FinalScore": 0.0,  # computed below
            # Metadata (not part of MODEL_FEATURES)
            "_dog_name": dog_name,
            "_venue": venue,
            "_race_number": race_num,
            "_dog_number": dog_num,
            "_grade": grade,
            "_odds": np.nan,  # populated from TAB API if available
        }

        records.append(feat)

    features_df = pd.DataFrame(records)

    if features_df.empty:
        logger.warning("No feature records produced")
        cols = MODEL_FEATURES + ["_dog_name", "_venue", "_race_number", "_dog_number", "_grade", "_odds"]
        return pd.DataFrame(columns=cols)

    # ── Compute FinalScore per runner ────────────────────────────────
    features_df["FinalScore"] = features_df.apply(_compute_final_score, axis=1)

    # ── Compute field-level features per race ────────────────────────
    race_key = ["_venue", "_race_number"]
    for _, race_group in features_df.groupby(race_key):
        idx = race_group.index
        n_runners = len(race_group)

        # Field size
        features_df.loc[idx, "FieldSize"] = n_runners
        features_df.loc[idx, "FieldSizeAdjustment"] = (8 - n_runners) * 0.02
        features_df.loc[idx, "CompetitorDensity"] = n_runners / 8.0
        features_df.loc[idx, "CompetitorAdjustment"] = 1.0 - (n_runners - 8) * 0.02

        # Speed/time stats
        speeds = race_group["Speed_kmh"]
        times = race_group["BestTimeSec"]

        field_speed_std = speeds.std() if len(speeds) > 1 else 0.0
        field_time_std = times.std() if len(times) > 1 else 0.0
        mean_speed = speeds.mean() if len(speeds) > 0 else 60.0

        features_df.loc[idx, "FieldSpeedStd"] = field_speed_std
        features_df.loc[idx, "FieldTimeStd"] = field_time_std
        features_df.loc[idx, "FieldSimilarityIndex"] = (
            1.0 - field_speed_std / mean_speed if mean_speed > 0 else 0.5
        )

        # Percentile ranks within field
        if n_runners > 1:
            features_df.loc[idx, "EarlySpeedPercentile"] = (
                race_group["EarlySpeedIndex"].rank(pct=True)
            )
            # Lower time = better, so invert
            features_df.loc[idx, "BestTimePercentile"] = (
                1.0 - race_group["BestTimeSec"].rank(pct=True)
            )
        else:
            features_df.loc[idx, "EarlySpeedPercentile"] = 0.5
            features_df.loc[idx, "BestTimePercentile"] = 0.5

        # FormMomentumNorm within field
        fm = race_group["FormMomentum"]
        if fm.std() > 0:
            features_df.loc[idx, "FormMomentumNorm"] = (
                (fm - fm.min()) / (fm.max() - fm.min())
            )
        else:
            features_df.loc[idx, "FormMomentumNorm"] = 0.5

    # ── Fill NaN and validate ────────────────────────────────────────
    for col in MODEL_FEATURES:
        if col not in features_df.columns:
            logger.error("Missing feature column: %s — adding with default 0", col)
            features_df[col] = 0.0
        features_df[col] = pd.to_numeric(features_df[col], errors="coerce").fillna(0.0)

    # Validate feature count and order
    actual_features = [c for c in features_df.columns if c in MODEL_FEATURES]
    if len(actual_features) != 74:
        logger.error(
            "Feature count mismatch: expected 74, got %d. Missing: %s",
            len(actual_features),
            set(MODEL_FEATURES) - set(actual_features),
        )

    # Reorder to match MODEL_FEATURES exactly
    meta_cols = [c for c in features_df.columns if c.startswith("_")]
    features_df = features_df[MODEL_FEATURES + meta_cols]

    logger.info(
        "Engineered %d runner feature vectors (%d features)",
        len(features_df),
        len(MODEL_FEATURES),
    )
    return features_df


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_num(val, default=0.0):
    """Convert to float, returning default on failure."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _estimate_time(distance):
    """Estimate a reasonable time for a given distance when no data available."""
    # Rough pace: ~17s per 300m, scales approximately linearly
    return max(10, distance * 0.057) if distance and distance > 0 else 25.0


def _estimate_split(distance):
    """Estimate first split time for a given distance."""
    # First split covers roughly first 100-150m
    return max(3.0, distance * 0.015) if distance and distance > 0 else 5.0


def _compute_rest_factor(dlr):
    """Compute rest factor from days since last run."""
    if 7 <= dlr <= 14:
        return 1.0
    elif 4 <= dlr <= 21:
        return 0.8
    elif dlr > 35:
        return 0.5
    elif dlr > 60:
        return 0.3
    else:
        return 0.8


def _compute_freshness(dlr):
    """Compute freshness factor — peak at 7-14 days."""
    if 7 <= dlr <= 14:
        return 1.0
    elif 4 <= dlr <= 7:
        return 0.9
    elif 14 < dlr <= 21:
        return 0.85
    elif 21 < dlr <= 35:
        return 0.7
    elif dlr > 35:
        return 0.5
    else:
        return 0.8
