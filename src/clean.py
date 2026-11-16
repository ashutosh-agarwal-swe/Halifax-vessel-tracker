"""
Step 1: load the raw position files and clean them.

Raw AIS data is messy. This script:
  - throws away rows with broken ship IDs or impossible positions
  - keeps only the study area
  - removes duplicates
  - keeps one position per ship per minute
  - removes GPS glitches (positions the ship could not have reached)
  - adds the ship type from the static data files
  - removes ship types listed in config.EXCLUDED_TYPES (military)
"""

import glob
import os

import numpy as np
import pandas as pd

import config
from src import helpers


def load_raw_positions(raw_folder):
    """Read every positions_*.csv file in the folder into one table."""
    files = sorted(glob.glob(os.path.join(raw_folder, "positions_*.csv")))
    if len(files) == 0:
        raise FileNotFoundError(
            f"No positions_*.csv files found in {raw_folder}. "
            "See docs/DATA_DOWNLOAD.md for how to get data."
        )

    tables = []
    for path in files:
        tables.append(pd.read_csv(path))
    positions = pd.concat(tables, ignore_index=True)
    print(f"Loaded {len(positions):,} raw rows from {len(files)} file(s)")
    return positions


def load_vessel_types(raw_folder):
    """
    Read every static_*.csv file and keep the latest known type and
    length for each ship.

    Ships send their type in a separate message from their position,
    so some ships will not have a type at all.
    """
    files = sorted(glob.glob(os.path.join(raw_folder, "static_*.csv")))
    empty = pd.DataFrame(columns=["mmsi", "vessel_type", "length_m"])
    if len(files) == 0:
        return empty

    tables = []
    for path in files:
        tables.append(pd.read_csv(path))
    static = pd.concat(tables, ignore_index=True)

    static["mmsi"] = pd.to_numeric(static["mmsi"], errors="coerce")
    static["vessel_type"] = pd.to_numeric(static["vessel_type"], errors="coerce")
    static["length_m"] = pd.to_numeric(static["length_m"], errors="coerce")

    # Type 0 means "not available" in AIS.
    static.loc[static["vessel_type"] == 0, "vessel_type"] = np.nan
    static = static.dropna(subset=["mmsi", "vessel_type"])
    if len(static) == 0:
        return empty

    static["mmsi"] = static["mmsi"].astype("int64")
    static = static.sort_values("timestamp")
    static = static.drop_duplicates(subset="mmsi", keep="last")
    return static[["mmsi", "vessel_type", "length_m"]]


def remove_position_jumps(df):
    """
    Remove single positions that are impossibly far from the positions
    before and after them.

    For every ping we work out the speed the ship would have needed to
    get there from its previous ping. A glitch looks like a ship that
    suddenly does hundreds of knots to a point and then hundreds of
    knots back again, so we only remove a ping if BOTH the speed into
    it and the speed out of it are too high.
    """
    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    prev = df.groupby("mmsi")[["lat", "lon", "timestamp"]].shift(1)

    distance_km = helpers.haversine_km(prev["lat"], prev["lon"], df["lat"], df["lon"])
    hours = (df["timestamp"] - prev["timestamp"]).dt.total_seconds() / 3600
    df["speed_in"] = distance_km / hours / helpers.KM_PER_NAUTICAL_MILE
    df["speed_out"] = df.groupby("mmsi")["speed_in"].shift(-1)

    too_fast_in = df["speed_in"] > config.MAX_SPEED_KNOTS
    too_fast_out = (df["speed_out"] > config.MAX_SPEED_KNOTS) | df["speed_out"].isna()
    is_jump = too_fast_in & too_fast_out

    df = df[~is_jump].drop(columns=["speed_in", "speed_out"])
    return df.reset_index(drop=True)


def clean_positions(positions, vessel_types=None):
    """
    Clean the raw position table. Returns (clean table, report).

    The report is a list of (step name, rows left) so we can show how
    many rows each cleaning step removed.
    """
    report = []
    df = positions.copy()
    report.append(("raw rows", len(df)))

    # --- make sure every column has the right type -------------------
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for column in ["mmsi", "lat", "lon", "sog", "cog"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["mmsi", "timestamp", "lat", "lon"])
    df["mmsi"] = df["mmsi"].astype("int64")
    report.append(("after dropping unreadable rows", len(df)))

    # --- ship IDs -----------------------------------------------------
    # A real ship MMSI has 9 digits and starts with 2 to 7.
    # Other numbers are things like buoys, base stations or typos.
    valid_mmsi = (df["mmsi"] >= 200000000) & (df["mmsi"] <= 799999999)
    df = df[valid_mmsi]
    report.append(("after dropping invalid ship IDs", len(df)))

    # --- study area ---------------------------------------------------
    # This also removes the AIS "no position" values (lat 91, lon 181).
    inside = (
        (df["lat"] >= config.LAT_MIN)
        & (df["lat"] <= config.LAT_MAX)
        & (df["lon"] >= config.LON_MIN)
        & (df["lon"] <= config.LON_MAX)
    )
    df = df[inside].copy()
    report.append(("after keeping only the study area", len(df)))

    # --- speed --------------------------------------------------------
    # 102.3 knots is the AIS code for "speed not available".
    df.loc[df["sog"] > 102, "sog"] = np.nan

    # --- duplicates ---------------------------------------------------
    df = df.drop_duplicates(subset=["mmsi", "timestamp"])
    report.append(("after dropping duplicates", len(df)))

    # --- one ping per ship per minute --------------------------------
    df = df.sort_values(["mmsi", "timestamp"])
    df["time_slot"] = df["timestamp"].dt.floor(f"{config.DOWNSAMPLE_SECONDS}s")
    df = df.drop_duplicates(subset=["mmsi", "time_slot"], keep="first")
    df = df.drop(columns=["time_slot"])
    report.append(("after keeping one ping per minute", len(df)))

    # --- GPS glitches -------------------------------------------------
    df = remove_position_jumps(df)
    report.append(("after removing position jumps", len(df)))

    # --- ship names ---------------------------------------------------
    if "vessel_name" not in df.columns:
        df["vessel_name"] = ""
    df["vessel_name"] = df["vessel_name"].fillna("").astype(str).str.strip()

    # --- ship types ---------------------------------------------------
    if vessel_types is not None and len(vessel_types) > 0:
        df = df.merge(vessel_types, on="mmsi", how="left")
    else:
        df["vessel_type"] = np.nan
        df["length_m"] = np.nan

    # --- ship types that are left out (see config.EXCLUDED_TYPES) -----
    is_excluded = df["vessel_type"].isin(list(config.EXCLUDED_TYPES))
    df = df[~is_excluded]
    report.append(("after removing excluded ship types", len(df)))

    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)
    columns = ["mmsi", "timestamp", "lat", "lon", "sog", "cog",
               "vessel_name", "vessel_type", "length_m"]
    return df[columns], report


def print_report(report):
    print("\nCleaning report")
    for step, rows in report:
        print(f"  {step:<40} {rows:>12,}")


def run(raw_folder, processed_folder):
    """Load, clean and save. Returns the clean table."""
    positions = load_raw_positions(raw_folder)
    vessel_types = load_vessel_types(raw_folder)
    clean, report = clean_positions(positions, vessel_types)
    print_report(report)

    os.makedirs(processed_folder, exist_ok=True)
    out_path = os.path.join(processed_folder, "clean.csv")
    clean.to_csv(out_path, index=False)
    print(f"Saved {out_path}")
    return clean, report
