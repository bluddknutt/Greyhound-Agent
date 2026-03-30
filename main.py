import pandas as pd
import numpy as np
import pdfplumber
import os
from src.parser import parse_race_form
from src.features import compute_features
from src.llm_prompt import generate_full_card_prompt

def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

# 🚀 Start pipeline
print("🚀 Starting Greyhound Analytics")

# ✅ Find all PDFs in data folder
pdf_folder = "data"
pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]
pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(pdf_folder, x)), reverse=True)

if not pdf_files:
    print("❌ No PDF files found in data folder.")
    exit()

all_dogs = []

# ✅ Process each PDF
for pdf_file in pdf_files:
    pdf_path = os.path.join(pdf_folder, pdf_file)
    print(f"📄 Processing: {pdf_path}")
    raw_text = extract_text_from_pdf(pdf_path)
    df = parse_race_form(raw_text)

    # ✅ Convert DLR to numeric to avoid type errors
    df["DLR"] = pd.to_numeric(df["DLR"], errors="coerce")

    # ✅ Apply enhanced scoring
    df = compute_features(df)
    all_dogs.append(df)

# ✅ Combine all dogs
combined_df = pd.concat(all_dogs, ignore_index=True)
print(f"🐾 Total dogs parsed: {len(combined_df)}")

# ✅ Save full parsed form
combined_df.to_csv("outputs/todays_form.csv", index=False)
print("📄 Saved parsed form → outputs/todays_form.csv")

# ✅ Save ranked dogs
ranked = combined_df.sort_values(["Track", "RaceNumber", "FinalScore"], ascending=[True, True, False])
ranked.to_csv("outputs/ranked.csv", index=False)
print("📊 Saved ranked dogs → outputs/ranked.csv")

# ✅ Save top picks across all tracks
picks = ranked.groupby(["Track", "RaceNumber"]).head(1).reset_index(drop=True)
picks = picks.sort_values("FinalScore", ascending=False)

# Reorder columns
priority_cols = ["Track", "RaceNumber", "Box", "DogName", "FinalScore", "PrizeMoney"]
remaining_cols = [col for col in picks.columns if col not in priority_cols]
ordered_cols = priority_cols + remaining_cols
picks = picks[ordered_cols]

picks.to_csv("outputs/picks.csv", index=False)
print("🎯 Saved top picks → outputs/picks.csv")

# ✅ Display top picks
print("\n🏁 Top Picks Across All Tracks:")
for _, row in picks.iterrows():
    print(f"{row.Track} | Race {row.RaceNumber} | {row.DogName} | Score: {round(row.FinalScore, 3)}")

# ✅ Generate LLM analysis prompt
generate_full_card_prompt(ranked)

print("\n📌 Press Enter to exit...")
input()
