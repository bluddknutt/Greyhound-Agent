from src.parser import parse_race_form


def main() -> None:
    sample_text = """
Track: SANDOWN
Race 1 - 6:57PM
1 Hurry Dusty 633 Billy Stockdale 2d 31.2 1 0 2 3 555 M 4 10 515
Best: 29.85 Sectional: 5.40 Last3: [29.85, 30.10, 30.00]
Margins: [0.00, 1.25, 2.00]
2 Paw Yale 51424 Luke Harris 2d 30.8 2 6 11 40 15895 M 41 4 515
Best: 30.05 Sectional: 5.45 Last3: [30.05, 30.20, 30.10]
Margins: [1.25, 0.75, 1.00]
"""

    df = parse_race_form(sample_text)
    print(f"✅ Parsed {len(df)} dogs")

    display_columns = [
        "DogName",
        "BestTimeSec",
        "SectionalSec",
        "Last3TimesSec",
        "Margins",
    ]
    available_columns = [col for col in display_columns if col in df.columns]

    if available_columns:
        print(df[available_columns].to_string(index=False))
    else:
        print("No expected display columns found in parsed DataFrame.")


if __name__ == "__main__":
    main()
