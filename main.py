import argparse
import os
import sys

import pandas as pd
import numpy as np


def run_pdf_pipeline():
    import pdfplumber
    from src.parser import parse_race_form
    from src.features import compute_features

    def extract_text_from_pdf(pdf_path):
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text

    print("Starting Greyhound Analytics (PDF mode)")

    pdf_folder = "data"
    pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]
    pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(pdf_folder, x)), reverse=True)

    if not pdf_files:
        print("No PDF files found in data folder.")
        sys.exit(1)

    all_dogs = []

    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_folder, pdf_file)
        print(f"Processing: {pdf_path}")
        raw_text = extract_text_from_pdf(pdf_path)
        df = parse_race_form(raw_text)
        df["DLR"] = pd.to_numeric(df["DLR"], errors="coerce")
        df = compute_features(df)
        all_dogs.append(df)

    combined_df = pd.concat(all_dogs, ignore_index=True)
    print(f"Total dogs parsed: {len(combined_df)}")

    os.makedirs("outputs", exist_ok=True)
    combined_df.to_csv("outputs/todays_form.csv", index=False)
    print("Saved parsed form → outputs/todays_form.csv")

    ranked = combined_df.sort_values(["Track", "RaceNumber", "FinalScore"], ascending=[True, True, False])
    ranked.to_csv("outputs/ranked.csv", index=False)
    print("Saved ranked dogs → outputs/ranked.csv")

    picks = ranked.groupby(["Track", "RaceNumber"]).head(1).reset_index(drop=True)
    picks = picks.sort_values("FinalScore", ascending=False)

    priority_cols = ["Track", "RaceNumber", "Box", "DogName", "FinalScore", "PrizeMoney"]
    remaining_cols = [col for col in picks.columns if col not in priority_cols]
    picks = picks[priority_cols + remaining_cols]

    picks.to_csv("outputs/picks.csv", index=False)
    print("Saved top picks → outputs/picks.csv")

    print("\nTop Picks Across All Tracks:")
    for _, row in picks.iterrows():
        print(f"{row.Track} | Race {row.RaceNumber} | {row.DogName} | Score: {round(row.FinalScore, 3)}")


def run_csv_pipeline(csv_path):
    print(f"Starting Greyhound Analytics (CSV mode: {csv_path})")

    from src.scorer import predict, get_top4, print_predictions
    df = predict(csv_path)
    top4 = get_top4(df)
    print_predictions(top4, df)

    os.makedirs("outputs", exist_ok=True)
    out_path = "outputs/picks.csv"
    keep = [
        "venue", "state", "race_number", "race_name", "race_time", "distance",
        "grade", "box", "dog_name", "trainer", "best_time", "last_4_starts",
        "composite", "win_prob", "implied_odds", "predicted_rank",
    ]
    existing = [c for c in keep if c in top4.columns]
    top4[existing].to_csv(out_path, index=False)
    print(f"Saved top picks → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Greyhound race analytics pipeline.")
    parser.add_argument(
        "--csv",
        metavar="PATH",
        help="Path to pre-fetched form guide CSV. When provided, skips PDF processing.",
    )
    args = parser.parse_args()

    if args.csv:
        run_csv_pipeline(args.csv)
    else:
        run_pdf_pipeline()
