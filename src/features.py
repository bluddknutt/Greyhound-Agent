import pandas as pd
import numpy as np

# Points for finishing positions (5-8 all get 1 point)
POSITION_POINTS = {1: 10, 2: 7, 3: 5, 4: 3}


def score_form_string(form_str):
    """Score recent form digit string with recency-weighted position points.

    Most recent finish is weighted highest. E.g. '6533' → positions [6,5,3,3],
    most recent (3) counts most.
    """
    if not form_str:
        return 0.0
    digits = [c for c in str(form_str) if c.isdigit()][-6:]  # last 6 races
    if not digits:
        return 0.0
    total, weight_sum = 0.0, 0.0
    for i, d in enumerate(reversed(digits)):  # reversed = most recent first
        pts = POSITION_POINTS.get(int(d), 1)
        weight = 1.0 / (i + 1)  # recency decay: 1, 0.5, 0.33, ...
        total += pts * weight
        weight_sum += weight
    return total / weight_sum if weight_sum > 0 else 0.0


def dlw_factor(dlw_val):
    """Return a 0–1 factor based on days since last win."""
    s = str(dlw_val).strip().upper()
    if s in ("MDN", "FU", "NAN", "", "NONE"):
        return 0.0  # maiden / first-up — no wins on record
    try:
        dlw = float(dlw_val)
        if dlw <= 14:
            return 1.0
        if dlw <= 30:
            return 0.7
        if dlw <= 60:
            return 0.4
        return 0.2
    except (ValueError, TypeError):
        return 0.0


def compute_features(df):
    df = df.copy()

    # Ensure numeric types
    df["DLR"] = pd.to_numeric(df["DLR"], errors="coerce").fillna(99)
    df["CareerStarts"] = pd.to_numeric(df["CareerStarts"], errors="coerce").fillna(0)
    df["Distance"] = pd.to_numeric(df["Distance"], errors="coerce")

    # Use parsed timing data; fall back to physics-based estimates only when missing
    if "BestTimeSec" not in df.columns:
        df["BestTimeSec"] = None
    df["BestTimeSec"] = pd.to_numeric(df["BestTimeSec"], errors="coerce")
    df["BestTimeSec"] = df["BestTimeSec"].fillna(df["Distance"] / 16.5)

    if "SectionalSec" not in df.columns:
        df["SectionalSec"] = None
    df["SectionalSec"] = pd.to_numeric(df["SectionalSec"], errors="coerce")
    df["SectionalSec"] = df["SectionalSec"].fillna(df["Distance"] / 55.0)

    if "Last3TimesSec" not in df.columns:
        df["Last3TimesSec"] = [[] for _ in range(len(df))]
    if "Margins" not in df.columns:
        df["Margins"] = [[] for _ in range(len(df))]

    df["BoxBiasFactor"] = 0.1
    df["TrackConditionAdj"] = 1.0

    # Derived timing metrics
    df["Speed_kmh"] = (df["Distance"] / df["BestTimeSec"]) * 3.6
    df["EarlySpeedIndex"] = df["Distance"] / df["SectionalSec"]
    df["FinishConsistency"] = df["Last3TimesSec"].apply(
        lambda x: np.std(x) if len(x) >= 2 else 0.5
    )
    df["MarginAvg"] = df["Margins"].apply(
        lambda x: np.mean(x) if x else 0.0
    )
    df["FormMomentum"] = df["Margins"].apply(
        lambda x: np.mean(np.diff(x)) if len(x) >= 2 else 0.0
    )

    # Career consistency
    df["ConsistencyIndex"] = df.apply(
        lambda row: row["CareerWins"] / row["CareerStarts"] if row["CareerStarts"] > 0 else 0,
        axis=1,
    )

    # Recent form from form digit string (e.g. "6533" → scored positions)
    if "FormNumber" not in df.columns:
        df["FormNumber"] = ""
    df["RecentFormScore"] = df["FormNumber"].apply(score_form_string)

    # Win recency from DLW
    if "DLW" not in df.columns:
        df["DLW"] = ""
    df["WinRecencyFactor"] = df["DLW"].apply(dlw_factor)

    # DLR-based race recency boost (kept but reduced weight)
    df["RecentFormBoost"] = df.apply(
        lambda row: 1.0 if row["DLR"] <= 5 and row["CareerWins"] > 0 else (0.5 if row["DLR"] <= 10 else 0),
        axis=1,
    )

    # Distance suitability
    df["DistanceSuit"] = df["Distance"].apply(lambda x: 1.0 if x in [515, 595] else 0.7)

    # Fallbacks
    df["TrainerStrikeRate"] = df.get("TrainerStrikeRate", pd.Series([0.15] * len(df)))
    df["RestFactor"] = df.get("RestFactor", pd.Series([0.8] * len(df)))

    # Overexposure penalty
    df["OverexposedPenalty"] = df["CareerStarts"].apply(lambda x: -0.1 if x > 80 else 0)

    def get_weights(distance):
        if distance < 400:  # Sprint — early speed matters most
            return {
                "RecentFormScore": 0.30,
                "WinRecencyFactor": 0.12,
                "EarlySpeedIndex": 0.18,
                "Speed_kmh": 0.08,
                "ConsistencyIndex": 0.08,
                "FinishConsistency": 0.03,
                "PrizeMoney": 0.06,
                "RecentFormBoost": 0.05,
                "BoxBiasFactor": 0.05,
                "TrainerStrikeRate": 0.03,
                "DistanceSuit": 0.02,
            }
        elif distance <= 500:  # Middle
            return {
                "RecentFormScore": 0.30,
                "WinRecencyFactor": 0.15,
                "ConsistencyIndex": 0.12,
                "EarlySpeedIndex": 0.10,
                "Speed_kmh": 0.05,
                "FinishConsistency": 0.04,
                "PrizeMoney": 0.08,
                "RecentFormBoost": 0.05,
                "BoxBiasFactor": 0.05,
                "TrainerStrikeRate": 0.03,
                "DistanceSuit": 0.03,
            }
        else:  # Long — consistency & recent form dominate
            return {
                "RecentFormScore": 0.28,
                "WinRecencyFactor": 0.15,
                "ConsistencyIndex": 0.18,
                "FinishConsistency": 0.08,
                "EarlySpeedIndex": 0.07,
                "Speed_kmh": 0.04,
                "PrizeMoney": 0.07,
                "RecentFormBoost": 0.05,
                "BoxBiasFactor": 0.03,
                "TrainerStrikeRate": 0.03,
                "DistanceSuit": 0.02,
            }

    # FinalScore calculation
    final_scores = []
    for _, row in df.iterrows():
        w = get_weights(row["Distance"])
        score = (
            row["RecentFormScore"] * w["RecentFormScore"] +
            row["WinRecencyFactor"] * w["WinRecencyFactor"] +
            row["EarlySpeedIndex"] * w["EarlySpeedIndex"] +
            row["Speed_kmh"] * w["Speed_kmh"] +
            row["ConsistencyIndex"] * w["ConsistencyIndex"] +
            row["FinishConsistency"] * w["FinishConsistency"] +
            (row["PrizeMoney"] / 1000) * w["PrizeMoney"] +
            row["RecentFormBoost"] * w["RecentFormBoost"] +
            row["BoxBiasFactor"] * w["BoxBiasFactor"] +
            row["TrainerStrikeRate"] * w["TrainerStrikeRate"] +
            row["DistanceSuit"] * w["DistanceSuit"] +
            row["OverexposedPenalty"]
        )
        final_scores.append(score)

    df["FinalScore"] = final_scores

    # Normalise scores to 0–100 within each race for readable confidence tiers
    def normalise_scores(scores):
        mn, mx = scores.min(), scores.max()
        if mx == mn:
            return pd.Series(50.0, index=scores.index)
        return (scores - mn) / (mx - mn) * 100

    df["FinalScore"] = df.groupby(["Track", "RaceNumber"])["FinalScore"].transform(normalise_scores)

    return df


def generate_trifecta_table(df):
    trifecta_rows = []

    for (track, race), group in df.groupby(["Track", "RaceNumber"]):
        top3 = group.sort_values("FinalScore", ascending=False).head(3)
        if len(top3) < 3:
            continue

        scores = top3["FinalScore"].values
        separation_score = (scores[0] - scores[1]) + (scores[1] - scores[2])

        # Confidence tiering (scores now 0–100)
        if scores[0] > 70 and separation_score > 20:
            tier = "Tier 1"
        elif scores[0] > 60 and separation_score > 15:
            tier = "Tier 2"
        elif scores[0] > 50 and separation_score > 10:
            tier = "Tier 3"
        else:
            tier = "Tier 4"

        trifecta_rows.append({
            "Track": track,
            "RaceNumber": race,
            "Dog1": top3.iloc[0]["DogName"],
            "Dog2": top3.iloc[1]["DogName"],
            "Dog3": top3.iloc[2]["DogName"],
            "Score1": round(scores[0], 1),
            "Score2": round(scores[1], 1),
            "Score3": round(scores[2], 1),
            "SeparationScore": round(separation_score, 1),
            "ConfidenceTier": tier,
            "BetFlag": "BET" if tier in ["Tier 1", "Tier 2"] else "NO BET",
        })

    trifecta_df = pd.DataFrame(trifecta_rows)
    trifecta_df = trifecta_df.sort_values("SeparationScore", ascending=False)
    return trifecta_df
