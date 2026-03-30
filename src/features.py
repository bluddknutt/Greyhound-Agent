import pandas as pd
import numpy as np
import re

from src.config import (
    SPRINT_WEIGHTS, MIDDLE_WEIGHTS, LONG_WEIGHTS,
    BOX_BIAS, TRIFECTA_TIERS, TRIFECTA_DEFAULT_TIER,
    OVEREXPOSED_STARTS, EXPERIENCE_CAP_STARTS,
)


# ---------------------------------------------------------------------------
# Helper: parse age from SexAge field  ("3d" → 3, "2b" → 2)
# ---------------------------------------------------------------------------

def _parse_age(sex_age):
    m = re.match(r"(\d+)", str(sex_age))
    return int(m.group(1)) if m else 3  # default to peak age if unparsable


# ---------------------------------------------------------------------------
# Helper: distance category string
# ---------------------------------------------------------------------------

def _distance_category(distance):
    if distance < 400:
        return "sprint"
    elif distance <= 500:
        return "middle"
    return "long"


# ---------------------------------------------------------------------------
# Main feature computation
# ---------------------------------------------------------------------------

def compute_features(df):
    df = df.copy()

    # --- ensure columns exist with defaults ----------------------------------
    defaults = {
        "DLR": 0, "DLW": 0, "CareerStarts": 0, "CareerWins": 0,
        "CareerPlaces": 0, "PrizeMoney": 0, "Distance": 400,
        "Box": 5, "Weight": 0, "SexAge": "3d", "RTC": "",
        "Track": "Unknown", "RaceNumber": 0,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    for col in ("DLR", "DLW", "CareerStarts", "CareerWins", "CareerPlaces",
                "PrizeMoney", "Distance", "Box", "Weight"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["CareerStarts"] = df["CareerStarts"].fillna(0)
    df["CareerWins"]   = df["CareerWins"].fillna(0)
    df["CareerPlaces"] = df["CareerPlaces"].fillna(0)
    df["PrizeMoney"]   = df["PrizeMoney"].fillna(0)
    df["Distance"]     = df["Distance"].fillna(400)
    df["Box"]          = df["Box"].fillna(5).astype(int)

    # -----------------------------------------------------------------------
    # A. Class Rating  (prize money per start – normalised within each race)
    # -----------------------------------------------------------------------
    df["PrizePerStart"] = df["PrizeMoney"] / df["CareerStarts"].clip(lower=1)

    # Normalise within each race so the best dog = 1.0
    df["ClassRating"] = df.groupby(["Track", "RaceNumber"])["PrizePerStart"].transform(
        lambda s: s / s.max() if s.max() > 0 else 0
    )

    # -----------------------------------------------------------------------
    # B. Form Rating  (weighted blend of win rate and place rate)
    # -----------------------------------------------------------------------
    df["WinRate"]   = df["CareerWins"]  / df["CareerStarts"].clip(lower=1)
    df["PlaceRate"] = (df["CareerWins"] + df["CareerPlaces"]) / df["CareerStarts"].clip(lower=1)
    df["FormRating"] = df["WinRate"] * 0.6 + df["PlaceRate"] * 0.4

    # -----------------------------------------------------------------------
    # C. Box Advantage  (distance-aware inside/outside bias)
    # -----------------------------------------------------------------------
    def _box_advantage(row):
        cat = _distance_category(row["Distance"])
        bias_map = BOX_BIAS.get(cat, BOX_BIAS["middle"])
        return bias_map.get(int(row["Box"]), 0.0)

    df["BoxAdvantage"] = df.apply(_box_advantage, axis=1)

    # -----------------------------------------------------------------------
    # D. Days-Since-Last-Win (DLW) Factor
    #    1.0 if won in last 14 days → 0.0 if maiden or > 365 days
    # -----------------------------------------------------------------------
    def _dlw_factor(dlw):
        if pd.isna(dlw) or dlw <= 0:
            return 0.0       # maiden / unknown
        if dlw <= 14:
            return 1.0
        if dlw <= 30:
            return 0.8
        if dlw <= 60:
            return 0.6
        if dlw <= 120:
            return 0.4
        if dlw <= 365:
            return 0.2
        return 0.0

    df["DLWFactor"] = df["DLW"].apply(_dlw_factor)

    # -----------------------------------------------------------------------
    # E. Age Factor  (peak at 2-3, tails off)
    # -----------------------------------------------------------------------
    def _age_factor(sex_age):
        age = _parse_age(sex_age)
        if age <= 1:
            return 0.85
        if age <= 3:
            return 1.0
        if age == 4:
            return 0.90
        if age == 5:
            return 0.75
        return 0.60  # 6+

    df["AgeFactor"] = df["SexAge"].apply(_age_factor)

    # -----------------------------------------------------------------------
    # F. RTC (Recent Track Class) Factor
    #    Lower numeric RTC = higher class. Normalised within race.
    # -----------------------------------------------------------------------
    df["RTC_numeric"] = pd.to_numeric(df["RTC"], errors="coerce")

    def _normalise_rtc(group):
        valid = group.dropna()
        if valid.empty or valid.max() == valid.min():
            return pd.Series(0.5, index=group.index)
        # Invert so that lower RTC → higher factor
        inverted = valid.max() - valid
        return (inverted / inverted.max()).reindex(group.index, fill_value=0.5)

    df["RTCFactor"] = df.groupby(["Track", "RaceNumber"])["RTC_numeric"].transform(
        lambda g: _normalise_rtc(g)
    )

    # -----------------------------------------------------------------------
    # G. Improved Recent Form Boost  (gradient based on DLR)
    # -----------------------------------------------------------------------
    def _recent_form_boost(row):
        dlr = row["DLR"]
        if pd.isna(dlr) or dlr < 0:
            return 0.0
        if dlr <= 5:
            base = 1.0
        elif dlr <= 10:
            base = 0.8
        elif dlr <= 21:
            base = 0.5
        elif dlr <= 42:
            base = 0.2
        else:
            base = 0.0
        # Boost further if the dog has recent wins
        dlw_mult = row.get("DLWFactor", 0.5)
        return base * (0.5 + 0.5 * dlw_mult)

    df["RecentFormBoost"] = df.apply(_recent_form_boost, axis=1)

    # -----------------------------------------------------------------------
    # H. Experience Factor  (more starts = more reliable, caps at threshold)
    # -----------------------------------------------------------------------
    df["ExperienceFactor"] = (df["CareerStarts"] / EXPERIENCE_CAP_STARTS).clip(upper=1.0)

    # -----------------------------------------------------------------------
    # I. Overexposed Penalty
    # -----------------------------------------------------------------------
    df["OverexposedPenalty"] = df["CareerStarts"].apply(
        lambda x: -0.1 if x > OVEREXPOSED_STARTS else 0.0
    )

    # -----------------------------------------------------------------------
    # Keep legacy speed columns when real parsed data exists
    # -----------------------------------------------------------------------
    if "BestTimeSec" in df.columns and df["BestTimeSec"].notna().any():
        df["Speed_kmh"] = (df["Distance"] / df["BestTimeSec"]) * 3.6
    else:
        df["Speed_kmh"] = np.nan

    if "SectionalSec" in df.columns and df["SectionalSec"].notna().any():
        df["EarlySpeedIndex"] = df["Distance"] / df["SectionalSec"]
    else:
        df["EarlySpeedIndex"] = np.nan

    # -----------------------------------------------------------------------
    # Final Score  (distance-adaptive weighted sum)
    # -----------------------------------------------------------------------
    def _get_weights(distance):
        cat = _distance_category(distance)
        if cat == "sprint":
            return SPRINT_WEIGHTS
        elif cat == "middle":
            return MIDDLE_WEIGHTS
        return LONG_WEIGHTS

    final_scores = []
    for _, row in df.iterrows():
        w = _get_weights(row["Distance"])
        score = 0.0
        for feature, weight in w.items():
            val = row.get(feature, 0.0)
            if pd.isna(val):
                val = 0.0
            score += val * weight
        # Scale up so scores are in a readable range (roughly 0-50)
        score *= 50
        final_scores.append(score)

    df["FinalScore"] = final_scores
    return df


# ---------------------------------------------------------------------------
# Trifecta table generation
# ---------------------------------------------------------------------------

def generate_trifecta_table(df):
    trifecta_rows = []

    for (track, race), group in df.groupby(["Track", "RaceNumber"]):
        top3 = group.sort_values("FinalScore", ascending=False).head(3)
        if len(top3) < 3:
            continue

        scores = top3["FinalScore"].values
        separation_score = (scores[0] - scores[1]) + (scores[1] - scores[2])

        # Determine confidence tier
        tier_info = TRIFECTA_DEFAULT_TIER
        for t in TRIFECTA_TIERS:
            if scores[0] > t["min_score"] and separation_score > t["min_sep"]:
                tier_info = t
                break

        trifecta_rows.append({
            "Track": track,
            "RaceNumber": race,
            "Dog1": top3.iloc[0]["DogName"],
            "Dog2": top3.iloc[1]["DogName"],
            "Dog3": top3.iloc[2]["DogName"],
            "Score1": scores[0],
            "Score2": scores[1],
            "Score3": scores[2],
            "SeparationScore": round(separation_score, 3),
            "ConfidenceTier": tier_info["tier"],
            "BetFlag": "BET" if tier_info.get("bet") else "NO BET",
        })

    trifecta_df = pd.DataFrame(trifecta_rows)
    if not trifecta_df.empty:
        trifecta_df = trifecta_df.sort_values("SeparationScore", ascending=False)
    return trifecta_df
