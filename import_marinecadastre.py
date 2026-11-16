"""
PLAN B data source: import AIS files downloaded from MarineCadastre.gov.

MarineCadastre is a free archive of historical AIS data, but it only
covers the UNITED STATES Exclusive Economic Zone. Saint John and most
of the Bay of Fundy are in Canadian waters and are NOT in it.

Use this script only if you change the study area in config.py to
somewhere in US waters (for example the Maine side of the Gulf of
Maine). See docs/DATA_DOWNLOAD.md, "Plan B".

Usage:
    1. Put the downloaded .csv (or .zip) files in data/marinecadastre/
    2. python import_marinecadastre.py

The script rewrites them into the same format that collect_ais.py
produces, so the rest of the pipeline does not care where the data
came from.
"""

import glob
import os

import pandas as pd

import config

INPUT_FOLDER = os.path.join("data", "marinecadastre")
RAW_FOLDER = os.path.join("data", "raw")
CHUNK_ROWS = 500000  # read big files in pieces so they fit in memory

# MarineCadastre changed its column names in 2025, so we make every
# name lower case, remove underscores, and then look it up here.
COLUMN_NAMES = {
    "mmsi": "mmsi",
    "basedatetime": "timestamp",
    "lat": "lat",
    "latitude": "lat",
    "lon": "lon",
    "longitude": "lon",
    "sog": "sog",
    "cog": "cog",
    "vesselname": "vessel_name",
    "vesseltype": "vessel_type",
    "length": "length_m",
}


def tidy_columns(chunk):
    new_names = {}
    for column in chunk.columns:
        simple = column.lower().replace("_", "").strip()
        if simple in COLUMN_NAMES:
            new_names[column] = COLUMN_NAMES[simple]
    return chunk.rename(columns=new_names)


def import_file(path):
    base = os.path.splitext(os.path.basename(path))[0]
    positions_path = os.path.join(RAW_FOLDER, f"positions_mc_{base}.csv")
    static_path = os.path.join(RAW_FOLDER, f"static_mc_{base}.csv")

    rows_kept = 0
    static_parts = []
    first_chunk = True

    for chunk in pd.read_csv(path, chunksize=CHUNK_ROWS, low_memory=False):
        chunk = tidy_columns(chunk)

        needed = ["mmsi", "timestamp", "lat", "lon"]
        missing = [c for c in needed if c not in chunk.columns]
        if missing:
            raise SystemExit(f"{path} is missing columns {missing}. "
                             f"Columns found: {list(chunk.columns)}")

        inside = (
            (chunk["lat"] >= config.LAT_MIN) & (chunk["lat"] <= config.LAT_MAX)
            & (chunk["lon"] >= config.LON_MIN) & (chunk["lon"] <= config.LON_MAX)
        )
        chunk = chunk[inside].copy()
        if len(chunk) == 0:
            continue

        for column in ["sog", "cog", "vessel_name", "vessel_type", "length_m"]:
            if column not in chunk.columns:
                chunk[column] = None

        positions = chunk[["mmsi", "timestamp", "lat", "lon", "sog", "cog", "vessel_name"]]
        positions.to_csv(positions_path, mode="w" if first_chunk else "a",
                         header=first_chunk, index=False)
        first_chunk = False
        rows_kept += len(positions)

        static = chunk[["mmsi", "timestamp", "vessel_name", "vessel_type", "length_m"]]
        static_parts.append(static.drop_duplicates(subset="mmsi", keep="last"))

    if static_parts:
        static = pd.concat(static_parts).drop_duplicates(subset="mmsi", keep="last")
        static["destination"] = ""
        static.to_csv(static_path, index=False)

    print(f"{os.path.basename(path)}: kept {rows_kept:,} rows inside the study area")
    return rows_kept


def main():
    os.makedirs(RAW_FOLDER, exist_ok=True)
    files = sorted(glob.glob(os.path.join(INPUT_FOLDER, "*.csv"))
                   + glob.glob(os.path.join(INPUT_FOLDER, "*.zip")))
    if len(files) == 0:
        raise SystemExit(f"No .csv or .zip files found in {INPUT_FOLDER}")

    total = 0
    for path in files:
        total += import_file(path)

    if total == 0:
        print("\nNo rows were inside the study area. MarineCadastre only covers US "
              "waters, so check the box in config.py (see docs/DATA_DOWNLOAD.md).")
    else:
        print(f"\nDone. {total:,} rows written to {RAW_FOLDER}. "
              "Now run: python run_pipeline.py")


if __name__ == "__main__":
    main()
