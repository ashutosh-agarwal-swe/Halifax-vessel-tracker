"""
Check the detectors by hand.

A detector that flags 100 things is useless if 95 of them are wrong,
so the top results of each detector get looked at one by one.

Usage:
    python review.py            # make outputs/review_sheet.csv
    (open the sheet, look each event up on the map, fill in the "label" column)
    python review.py --score    # work out how many flags were genuine

Labels to use:
    genuine          looks like real unusual behaviour
    false_positive   has an ordinary explanation (anchorage, ferry, bad reception...)
    unsure           cannot tell

Add --sample to either command to use outputs_sample/ instead.
"""

import argparse
import os

import pandas as pd

from src import helpers

TOP_N = 20  # how many events per detector to review


def build_sheet(output_folder):
    rows = []

    gaps = pd.read_csv(os.path.join(output_folder, "gaps_flagged.csv"))
    for row in gaps.head(TOP_N).itertuples():
        rows.append({
            "detector": "gap",
            "ships": f"{row.vessel_name} ({row.mmsi})",
            "start": row.gap_start,
            "end": row.gap_end,
            "lat": round(row.start_lat, 4),
            "lon": round(row.start_lon, 4),
            "details": f"{row.gap_hours:.1f} h silent, reappeared {row.distance_km:.0f} km away",
        })

    loitering = pd.read_csv(os.path.join(output_folder, "loitering.csv"))
    for row in loitering.head(TOP_N).itertuples():
        rows.append({
            "detector": "loitering",
            "ships": f"{row.vessel_name} ({row.mmsi})",
            "start": row.start,
            "end": row.end,
            "lat": round(row.lat, 4),
            "lon": round(row.lon, 4),
            "details": f"{row.duration_hours:.1f} h, {row.km_from_port:.0f} km from nearest port circle",
        })

    rendezvous = pd.read_csv(os.path.join(output_folder, "rendezvous.csv"))
    for row in rendezvous.head(TOP_N).itertuples():
        rows.append({
            "detector": "rendezvous",
            "ships": f"{row.name_a} ({row.mmsi_a}) + {row.name_b} ({row.mmsi_b})",
            "start": row.start,
            "end": row.end,
            "lat": round(row.lat, 4),
            "lon": round(row.lon, 4),
            "details": f"{row.duration_minutes:.0f} min, closest {row.closest_km * 1000:.0f} m",
        })

    sheet = pd.DataFrame(rows, columns=["detector", "ships", "start", "end",
                                        "lat", "lon", "details"])
    sheet["label"] = ""
    sheet["notes"] = ""
    return sheet


def score(sheet_path):
    sheet = pd.read_csv(sheet_path)
    sheet["label"] = sheet["label"].fillna("").str.strip().str.lower()

    unlabelled = int((sheet["label"] == "").sum())
    if unlabelled > 0:
        print(f"Note: {unlabelled} rows have no label yet and are ignored.\n")

    print(f"{'detector':<12} {'genuine':>8} {'false pos':>10} {'unsure':>7} {'precision':>10}")
    for detector, rows in sheet.groupby("detector"):
        genuine = int((rows["label"] == "genuine").sum())
        false_pos = int((rows["label"] == "false_positive").sum())
        unsure = int((rows["label"] == "unsure").sum())
        decided = genuine + false_pos
        # Precision = of the flags I could judge, what share were genuine?
        precision = f"{genuine / decided:.0%}" if decided > 0 else "n/a"
        print(f"{detector:<12} {genuine:>8} {false_pos:>10} {unsure:>7} {precision:>10}")


def main():
    parser = argparse.ArgumentParser(description="Review flagged events by hand")
    parser.add_argument("--score", action="store_true", help="score a filled-in sheet")
    parser.add_argument("--sample", action="store_true", help="use outputs_sample/")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing review sheet (labels are lost!)")
    args = parser.parse_args()

    output_folder = "outputs_sample" if args.sample else "outputs"
    sheet_path = os.path.join(output_folder, "review_sheet.csv")

    if args.score:
        score(sheet_path)
        return

    if os.path.exists(sheet_path) and not args.overwrite:
        raise SystemExit(f"{sheet_path} already exists. Use --overwrite to replace it "
                         "(any labels you typed will be lost).")

    sheet = build_sheet(output_folder)
    helpers.spreadsheet_safe(sheet).to_csv(sheet_path, index=False)
    print(f"Wrote {len(sheet)} events to {sheet_path}")
    print("Fill in the label column, then run: python review.py --score")


if __name__ == "__main__":
    main()
