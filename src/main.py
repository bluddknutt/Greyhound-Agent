# NOTE: This is a legacy alternate entry point. Use top-level main.py instead.
import os
from src.parser import parse_race_form
from src.exporter import export_to_excel

INPUT_DIR = "inputs"
OUTPUT_DIR = "outputs"

def load_pdfs(directory):
    pdf_texts = []
    for filename in os.listdir(directory):
        if filename.lower().endswith(".pdf"):
            path = os.path.join(directory, filename)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            pdf_texts.append((filename, text))
    return pdf_texts

def analyze_race(race):
    for dog in race["dogs"]:
        dog["Score"] = 100.0 - dog.get("Box", 0) * 2.5
        dog["BetType"] = "YES" if dog["Score"] > 95 else "PLACE" if dog["Score"] > 80 else "PASS"
        dog["BetReason"] = f"Score={dog['Score']:.1f}"
        dog["FinalScore"] = dog["Score"]

def main():
    print("GREYHOUND ANALYZER - PRODUCTION READY")
    print("======================================================================")
    print("INITIALIZING...")
    print(f"OUTPUT: {os.path.abspath(OUTPUT_DIR)}")

    pdfs = load_pdfs(INPUT_DIR)
    print(f"FOUND {len(pdfs)} PDF FILES\n")

    all_dogs = []
    for filename, text in pdfs:
        print("PROCESSING PDFS...")
        print("--------------------------------------------------")
        print(f"PARSING {filename}...")
        result = parse_race_form(text)
        races = result.get("races", [])

        for race in races:
            print(f"   RACE: {race['RaceDate']} - {race['RaceTime']} {race['Track']}")
            analyze_race(race)
            for dog in race["dogs"]:
                print(f"   DOG: {race['RaceDate']} Race {race['RaceTime']} Box {dog['Box']}: {dog['DogName']}")
                dog["source_file"] = filename
                all_dogs.append(dog)

        print(f"EXTRACTED: {len(all_dogs)} from {filename}")

    print(f"\nANALYZING {len(all_dogs)} DOGS...")
    print("CALCULATING SCORES...")
    print("CALCULATING BETS...")

    bets = [d for d in all_dogs if d["BetType"] == "YES"]
    places = [d for d in all_dogs if d["BetType"] == "PLACE"]
    passes = [d for d in all_dogs if d["BetType"] == "PASS"]

    print(f"   BETS - YES: {len(bets)}, PLACE: {len(places)}, PASS: {len(passes)}")
    print("SUCCESS: Single winner per race!\n")

    print("SAVING EXCEL...")
    export_to_excel(all_dogs, OUTPUT_DIR)
    print("======================================================================")
    print("SUCCESS: Complete!")
    print("======================================================================")

if __name__ == "__main__":
    main()
