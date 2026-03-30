"""
llm_prompt.py — Generate structured prompts for Claude LLM race analysis.

Usage:
    from src.llm_prompt import generate_full_card_prompt

    prompt_text = generate_full_card_prompt(ranked_df)
    # prompt_text is a ready-to-send string for Claude
    # Also saved to outputs/llm_analysis_prompt.txt
"""

import os
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# System prompt — greyhound racing domain knowledge
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert Australian greyhound racing analyst with deep knowledge of \
form analysis, pace dynamics, box-draw theory, and value betting.

## Your Knowledge Base

### Distance Categories
- **Sprint (<400 m):** Early speed and box draw are critical. Inside boxes (1-2) \
have a significant rail advantage. The first dog to the first turn usually wins.
- **Middle (400-500 m):** Balanced races where early speed still matters but \
dogs with strong mid-race pace and consistency can run down leaders.
- **Long (>500 m):** Stamina and consistency dominate. Box draw matters less. \
Dogs with high win rates over distance are strongly favoured.

### Box Draw Theory (Australian Tracks)
- **Box 1-2:** Strong inside advantage, especially on sprint tracks with tight first turns.
- **Box 3-4:** Neutral to slight advantage depending on track geometry.
- **Box 5-6:** Neutral to slight disadvantage.
- **Box 7-8:** Wide draw disadvantage; dogs must cover extra ground on turns.
- **Box 9-10 (wide boxes):** Significant disadvantage on most tracks.

### Key Form Indicators
- **Win Rate (W%):** Career wins / starts. Elite dogs >25%, competitive >15%.
- **Place Rate (P%):** (Wins + Places) / starts. Consistent dogs >45%.
- **Prize $/Start:** Earnings per start — the best single indicator of class. \
Higher = stronger opposition beaten.
- **Days Last Run (DLR):** Fitness indicator. 5-14 days ideal, >28 days = fitness query.
- **Days Last Win (DLW):** Confidence/form indicator. <30 days = in-form.
- **RTC:** Recent Track Class number. Lower = higher recent class level.
- **Age:** Peak performance at 2-3 years. Decline usually starts at 4+.
- **Career Starts:** 30-60 is experienced prime. >80 may indicate declining form.

### Pace Mapping
Identify likely race shape:
- **Leaders:** Dogs with high early speed, inside boxes, recent front-running wins.
- **Stalkers:** Dogs that settle 2nd-4th and finish strongly.
- **Closers:** Dogs with strong finishing records but slow beginnings.
Races with one clear leader and no pace pressure favour that leader. \
Races with multiple speed dogs create pace pressure benefiting stalkers/closers.

### Betting Framework
- **WIN bet:** High confidence (strong class edge + good draw + in-form).
- **PLACE bet:** Consistent dog (high place rate) with some query (wide draw, returning from spell).
- **PASS:** Competitive race with no clear edge, or insufficient data to assess.
- **Value:** When a dog's true chance is better than its score suggests \
(e.g. class dropper, returning champion, favourable pace scenario).

## Your Task
Analyse the race data provided below. For EACH race:

1. **Assess** each runner's class, form, fitness, box draw, and age profile.
2. **Map the pace** — identify likely leaders and how the race will be run.
3. **Rank** all runners from 1st to last with a brief reason for each.
4. **Recommend** a betting action: WIN / PLACE / PASS with reasoning.
5. **Flag value plays** where the model score may underrate a dog.
6. **Confidence level** for your top pick: HIGH / MEDIUM / LOW.

Format your analysis clearly with headers for each race.\
"""


# ---------------------------------------------------------------------------
# Format a single race into a readable data block
# ---------------------------------------------------------------------------

def _format_race_block(race_df, track, race_number, distance):
    """Return a formatted text block for one race."""
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"RACE {race_number} — {track} — {int(distance)}m "
                 f"({_distance_label(distance)})")
    lines.append(f"{'='*70}")
    lines.append("")

    # Table header
    header = (
        f"{'Box':>3} | {'Dog':<22} | {'W%':>5} | {'P%':>5} | "
        f"{'Starts':>6} | {'$/Start':>8} | {'DLR':>4} | {'DLW':>5} | "
        f"{'Age':>3} | {'RTC':>4} | {'Score':>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    # Sort by FinalScore descending within race
    sorted_df = race_df.sort_values("FinalScore", ascending=False)

    for _, row in sorted_df.iterrows():
        win_pct = _safe_pct(row.get("WinRate", 0))
        place_pct = _safe_pct(row.get("PlaceRate", 0))
        starts = int(row.get("CareerStarts", 0))
        pps = row.get("PrizePerStart", 0)
        dlr = _fmt_val(row.get("DLR"))
        dlw = _fmt_val(row.get("DLW"))
        age = _parse_age_str(row.get("SexAge", ""))
        rtc = _fmt_val(row.get("RTC"))
        score = row.get("FinalScore", 0)
        dog = str(row.get("DogName", ""))[:22]

        lines.append(
            f"{int(row.get('Box', 0)):>3} | {dog:<22} | {win_pct:>5} | "
            f"{place_pct:>5} | {starts:>6} | ${pps:>7,.0f} | "
            f"{dlr:>4} | {dlw:>5} | {age:>3} | {rtc:>4} | {score:>6.1f}"
        )

    lines.append("")

    # Quick summary of model's top 3
    top3 = sorted_df.head(3)
    lines.append("Model Top 3:")
    for i, (_, r) in enumerate(top3.iterrows(), 1):
        lines.append(f"  {i}. {r['DogName']} (Box {int(r['Box'])}) — "
                     f"Score {r['FinalScore']:.1f}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generate prompt for the full race card
# ---------------------------------------------------------------------------

def generate_full_card_prompt(ranked_df, output_path="outputs/llm_analysis_prompt.txt"):
    """
    Build a complete Claude-ready prompt from the ranked dataframe.

    Parameters
    ----------
    ranked_df : pd.DataFrame
        The scored & ranked dataframe (output of compute_features).
    output_path : str or None
        If set, write the prompt to this file.

    Returns
    -------
    str
        The full prompt text (system + race data + instructions).
    """
    sections = []

    # Header
    sections.append("=" * 70)
    sections.append("GREYHOUND RACING ANALYSIS — FULL CARD")
    sections.append("=" * 70)
    sections.append("")

    # Count summary
    tracks = ranked_df["Track"].nunique()
    races = ranked_df.groupby(["Track", "RaceNumber"]).ngroups
    dogs = len(ranked_df)
    sections.append(f"Tracks: {tracks} | Races: {races} | Total Runners: {dogs}")
    sections.append("")

    # Scoring methodology note
    sections.append("SCORING METHODOLOGY:")
    sections.append("The model scores each runner 0-50 using these weighted factors:")
    sections.append("  - Class Rating (prize $/start, normalised within race)")
    sections.append("  - Form Rating (60% win rate + 40% place rate)")
    sections.append("  - Box Advantage (distance-aware inside/outside bias)")
    sections.append("  - Recent Form Boost (days since last run + recent win activity)")
    sections.append("  - Days-Since-Last-Win Factor (recency of winning)")
    sections.append("  - Age Factor (peak at 2-3 years)")
    sections.append("  - RTC Class Factor (recent track class, normalised)")
    sections.append("  - Experience Factor (career starts, capped at 30)")
    sections.append("  - Overexposed Penalty (>80 career starts)")
    sections.append("Weights shift by distance: sprints favour box draw & form; "
                    "long races favour consistency & class.")
    sections.append("")
    sections.append("-" * 70)
    sections.append("RACE DATA")
    sections.append("-" * 70)
    sections.append("")

    # Generate each race block
    for (track, race_num), group in ranked_df.groupby(["Track", "RaceNumber"]):
        distance = group["Distance"].iloc[0]
        sections.append(_format_race_block(group, track, race_num, distance))

    # Closing instruction
    sections.append("=" * 70)
    sections.append("ANALYSIS REQUEST")
    sections.append("=" * 70)
    sections.append("")
    sections.append(
        "Please analyse each race above following the framework in the system prompt. "
        "For each race provide:\n"
        "1. Runner-by-runner assessment (2-3 sentences each)\n"
        "2. Pace map / likely race shape\n"
        "3. Final ranking (1st to last)\n"
        "4. Betting recommendation: WIN / PLACE / PASS + reasoning\n"
        "5. Any value plays the model may have missed\n"
        "6. Confidence level: HIGH / MEDIUM / LOW\n"
    )

    full_prompt = "\n".join(sections)

    # Write to file
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("SYSTEM PROMPT:\n")
            f.write("-" * 70 + "\n")
            f.write(SYSTEM_PROMPT + "\n\n")
            f.write("-" * 70 + "\n")
            f.write("USER PROMPT:\n")
            f.write("-" * 70 + "\n\n")
            f.write(full_prompt)
        print(f"📝 Saved LLM analysis prompt → {output_path}")

    return full_prompt


def get_system_prompt():
    """Return the system prompt for use with the Claude API."""
    return SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _distance_label(distance):
    if distance < 400:
        return "Sprint"
    elif distance <= 500:
        return "Middle"
    return "Staying"


def _safe_pct(val):
    try:
        return f"{float(val)*100:.0f}%"
    except (ValueError, TypeError):
        return "  —"


def _fmt_val(val):
    if pd.isna(val):
        return "—"
    try:
        v = int(float(val))
        return str(v)
    except (ValueError, TypeError):
        return str(val)[:5]


def _parse_age_str(sex_age):
    import re
    m = re.match(r"(\d+)", str(sex_age))
    return m.group(1) if m else "?"
