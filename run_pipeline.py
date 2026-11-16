"""
Run the whole analysis from start to finish.

Usage:
    python run_pipeline.py            # use the real data in data/raw/
    python run_pipeline.py --sample   # use the FAKE sample data instead

Results go to outputs/ (or outputs_sample/ for the sample run).
"""

import argparse
import os

import config
from src import (clean, coverage, detect_gaps, detect_loitering,
                 detect_rendezvous, make_map)


def write_summary(df, report, cells, gaps, loitering, rendezvous, output_folder, is_sample):
    """Write the headline numbers to a text file (handy for the README)."""
    flagged_gaps = gaps[gaps["flagged"]] if len(gaps) > 0 else gaps
    hours = (df["timestamp"].max() - df["timestamp"].min()).total_seconds() / 3600

    lines = []
    if is_sample:
        lines.append("*** FAKE SAMPLE DATA - these numbers are not real findings ***")
        lines.append("")
    lines.append("DATA")
    lines.append(f"  first ping:            {df['timestamp'].min()}")
    lines.append(f"  last ping:             {df['timestamp'].max()}  ({hours / 24:.1f} days)")
    lines.append(f"  ships:                 {df['mmsi'].nunique():,}")
    lines.append(f"  raw rows:              {report[0][1]:,}")
    lines.append(f"  rows after cleaning:   {len(df):,}")
    lines.append("")
    lines.append("COVERAGE")
    lines.append(f"  grid cells with data:  {len(cells):,}")
    lines.append(f"  well covered cells:    {int(cells['well_covered'].sum()):,}")
    lines.append("")
    lines.append("GAPS")
    lines.append(f"  silences of {config.GAP_MIN_MINUTES}+ min:   {len(gaps):,}")
    if len(gaps) > 0:
        lines.append(f"    ship was moving:               {int(gaps['was_moving'].sum()):,}")
        lines.append(f"    started in well covered cell:  {int(gaps['start_well_covered'].sum()):,}")
        lines.append(f"    feed was working:              {int(gaps['feed_was_working'].sum()):,}")
    lines.append(f"  flagged after all checks: {len(flagged_gaps):,}")
    lines.append("")
    lines.append("LOITERING")
    lines.append(f"  runs outside ports:    {len(loitering):,}")
    if len(loitering) > 0:
        lines.append(f"  not a routine type:    {int((~loitering['likely_routine']).sum()):,}")
    lines.append("")
    lines.append("RENDEZVOUS")
    lines.append(f"  meetings outside ports: {len(rendezvous):,}")
    if len(rendezvous) > 0:
        lines.append(f"  not a routine type:     {int((~rendezvous['likely_routine']).sum()):,}")

    text = "\n".join(lines)
    path = os.path.join(output_folder, "summary.txt")
    with open(path, "w") as f:
        f.write(text + "\n")
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)
    print(f"Saved {path}")


def main():
    parser = argparse.ArgumentParser(description="Run the vessel tracker pipeline")
    parser.add_argument("--sample", action="store_true",
                        help="use fake sample data instead of data/raw/")
    args = parser.parse_args()

    if args.sample:
        import make_sample_data
        config.use_sample_area()
        raw_folder = make_sample_data.SAMPLE_FOLDER
        processed_folder = os.path.join("data", "sample_processed")
        output_folder = "outputs_sample"
        make_sample_data.generate(raw_folder)
    else:
        raw_folder = os.path.join("data", "raw")
        processed_folder = os.path.join("data", "processed")
        output_folder = "outputs"

    # Step 1: clean
    df, report = clean.run(raw_folder, processed_folder)
    if len(df) == 0:
        raise SystemExit("No rows left after cleaning. Check the study area in config.py.")

    # Step 2: coverage
    cells, alive_bins = coverage.run(df, output_folder)

    # Steps 3-5: the three detectors
    gaps = detect_gaps.run(df, cells, alive_bins, output_folder)
    loitering = detect_loitering.run(df, output_folder)
    rendezvous = detect_rendezvous.run(df, output_folder)

    # Step 6: maps and summary
    make_map.run(df, cells, gaps, loitering, rendezvous, output_folder, args.sample)
    write_summary(df, report, cells, gaps, loitering, rendezvous, output_folder, args.sample)


if __name__ == "__main__":
    main()
