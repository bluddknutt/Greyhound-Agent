import pandas as pd


def generate_llm_analysis_prompt(picks_df: pd.DataFrame, ranked_df: pd.DataFrame) -> str:
    """
    Build a structured LLM analysis prompt from the picks and ranked DataFrames.

    Returns a ready-to-send prompt string that an LLM can use to provide
    race-by-race commentary and betting recommendations.
    """
    lines = []

    lines.append("# Greyhound Racing Analysis Request")
    lines.append("")
    lines.append(
        "You are an expert greyhound racing analyst. Below is today's form data, "
        "processed through a quantitative scoring pipeline. Your task is to:\n"
        "1. Provide a concise race-by-race commentary for each race.\n"
        "2. Highlight the top pick and any notable challengers.\n"
        "3. Identify races with strong betting confidence (Tier 1/2) vs caution races (Tier 3/4).\n"
        "4. Flag any standout dogs across all meetings worth special attention.\n"
        "5. Summarise overall betting recommendations at the end (Win / Place / Trifecta)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Scoring legend ---
    lines.append("## Scoring Methodology")
    lines.append("")
    lines.append(
        "Each dog receives a **FinalScore** computed from up to 10 weighted factors "
        "that adapt to race distance:"
    )
    lines.append("")
    lines.append("| Factor | Sprint (<400 m) | Middle (400–500 m) | Long (>500 m) |")
    lines.append("|---|---|---|---|")
    lines.append("| Early Speed Index | 30% | 25% | 20% |")
    lines.append("| Speed (km/h) | 20% | 20% | 15% |")
    lines.append("| Consistency Index (wins/starts) | 10% | 15% | 20% |")
    lines.append("| Finish Consistency (std dev) | 5% | 5% | 10% |")
    lines.append("| Prize Money | 10% | 10% | 10% |")
    lines.append("| Recent Form Boost (≤10 days) | 10% | 10% | 10% |")
    lines.append("| Box Bias | 10% | 5% | 5% |")
    lines.append("| Trainer Strike Rate | 5% | 5% | 5% |")
    lines.append("| Distance Suitability | 5% | 5% | 5% |")
    lines.append("| Track Condition Adj. | 5% | 5% | 5% |")
    lines.append("")
    lines.append(
        "**Confidence Tiers** (trifecta confidence):\n"
        "- **Tier 1**: Top score > 42 and separation > 3 — HIGH confidence, BET\n"
        "- **Tier 2**: Top score > 40 and separation > 2 — GOOD confidence, BET\n"
        "- **Tier 3**: Top score > 38 and separation > 1.5 — MODERATE confidence, caution\n"
        "- **Tier 4**: Below thresholds — LOW confidence, avoid"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Race-by-race data ---
    lines.append("## Race-by-Race Form Data")
    lines.append("")

    tracks = picks_df["Track"].unique() if "Track" in picks_df.columns else []

    for track in sorted(tracks):
        track_picks = picks_df[picks_df["Track"] == track].sort_values("RaceNumber")
        track_ranked = ranked_df[ranked_df["Track"] == track] if "Track" in ranked_df.columns else ranked_df

        lines.append(f"### {track}")
        lines.append("")

        for _, pick_row in track_picks.iterrows():
            race_num = pick_row.get("RaceNumber", "?")
            distance = pick_row.get("Distance", "?")
            race_date = pick_row.get("RaceDate", "")
            race_time = pick_row.get("RaceTime", "")

            lines.append(f"#### Race {race_num} — {distance}m | {race_date} {race_time}")
            lines.append("")

            # All runners for this race, sorted by score descending
            race_runners = track_ranked[
                track_ranked["RaceNumber"] == race_num
            ].sort_values("FinalScore", ascending=False)

            if race_runners.empty:
                # Fall back to just the pick row
                race_runners = pd.DataFrame([pick_row])

            lines.append("| Box | Dog | Score | Wins/Starts | Prize $ | DLR | Trainer |")
            lines.append("|---|---|---|---|---|---|---|")

            for _, row in race_runners.iterrows():
                box = row.get("Box", "?")
                dog = row.get("DogName", "?")
                score = row.get("FinalScore", 0)
                wins = row.get("CareerWins", "?")
                starts = row.get("CareerStarts", "?")
                prize = row.get("PrizeMoney", 0)
                dlr = row.get("DLR", "?")
                trainer = row.get("Trainer", "?")
                lines.append(
                    f"| {box} | **{dog}** | {round(float(score), 3)} "
                    f"| {wins}/{starts} | ${int(float(prize)):,} "
                    f"| {dlr} | {trainer} |"
                )

            lines.append("")

            # Key metrics for top pick
            top_dog = race_runners.iloc[0] if not race_runners.empty else pick_row
            lines.append(f"**Top Pick**: Box {top_dog.get('Box', '?')} — {top_dog.get('DogName', '?')} "
                         f"(Score: {round(float(top_dog.get('FinalScore', 0)), 3)})")

            consistency = top_dog.get("ConsistencyIndex", None)
            if consistency is not None:
                lines.append(f"- Consistency Index: {round(float(consistency), 3)}")

            recent_boost = top_dog.get("RecentFormBoost", None)
            if recent_boost is not None:
                lines.append(f"- Recent Form Boost: {recent_boost}")

            dist_suit = top_dog.get("DistanceSuit", None)
            if dist_suit is not None:
                lines.append(f"- Distance Suitability: {dist_suit}")

            lines.append("")

    # --- Summary table ---
    lines.append("---")
    lines.append("")
    lines.append("## Top Picks Summary — All Meetings")
    lines.append("")
    lines.append("| Track | Race | Box | Dog | Score | Distance |")
    lines.append("|---|---|---|---|---|---|")

    for _, row in picks_df.sort_values("FinalScore", ascending=False).iterrows():
        lines.append(
            f"| {row.get('Track', '?')} | {row.get('RaceNumber', '?')} "
            f"| {row.get('Box', '?')} | **{row.get('DogName', '?')}** "
            f"| {round(float(row.get('FinalScore', 0)), 3)} "
            f"| {row.get('Distance', '?')}m |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Your Analysis")
    lines.append("")
    lines.append(
        "Please provide:\n"
        "1. **Race Commentary** — for each race, briefly describe the competitive shape, "
        "the strength of the top pick, and any threats.\n"
        "2. **Confidence Assessment** — which races are strong bets vs which to avoid.\n"
        "3. **Bet Types** — for each recommended race specify Win, Place, or Trifecta.\n"
        "4. **Best Bet of the Day** — identify the single highest-confidence bet.\n"
        "5. **Races to Avoid** — flag races where the field is too even or the data is thin.\n"
        "\n"
        "Be concise, factual, and base all observations on the data provided above."
    )

    return "\n".join(lines)


def save_prompt(prompt: str, output_path: str = "outputs/llm_analysis_prompt.txt") -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"📝 Saved LLM analysis prompt → {output_path}")
