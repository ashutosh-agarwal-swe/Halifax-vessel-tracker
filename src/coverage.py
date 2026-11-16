"""
Step 2: work out where the receivers can actually hear ships.

This is the most important step in the project.

AIS positions are picked up by radio receivers on shore. If a ship
sails somewhere no receiver can hear, it disappears from the data even
though its transponder is still on. If we flagged every disappearance
we would just be drawing a map of bad reception.

The idea used here:

    If lots of DIFFERENT ships go silent in the same place,
    the problem is the place, not the ships.

So the area is cut into grid cells. Each time a ship passes through a
cell counts as one "visit". For every cell we measure what share of
visits ended with the ship going silent. Cells where that share is low
are "well covered", and only gaps that start in those cells are
treated as suspicious later on.
"""

import os

import pandas as pd

import config
from src import helpers


def feed_alive_bins(df):
    """
    Return the set of time bins in which at least one ship was heard.

    If the collector was down (laptop asleep, internet dropped) then no
    ship at all is heard, and that bin is missing from the set.
    """
    bin_seconds = config.FEED_BIN_MINUTES * 60
    bins = helpers.to_epoch_seconds(df["timestamp"]) // bin_seconds
    return set(bins.unique().tolist())


def compute_coverage(df, alive_bins):
    """
    Build the coverage table: one row per grid cell.

    Columns: cell_y, cell_x, lat, lon (cell centre), n_visits,
             n_silent, silence_rate, well_covered
    """
    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)
    cell_y, cell_x = helpers.cell_index(df["lat"], df["lon"])
    df["cell_y"] = cell_y
    df["cell_x"] = cell_x

    # --- split each ship's pings into visits --------------------------
    # A new visit starts when the ship changes, the cell changes, or the
    # ship was silent for a while before this ping.
    prev_mmsi = df["mmsi"].shift(1)
    prev_y = df["cell_y"].shift(1)
    prev_x = df["cell_x"].shift(1)
    prev_time = df.groupby("mmsi")["timestamp"].shift(1)
    minutes_since_prev = (df["timestamp"] - prev_time).dt.total_seconds() / 60

    new_visit = (
        (df["mmsi"] != prev_mmsi)
        | (df["cell_y"] != prev_y)
        | (df["cell_x"] != prev_x)
        | (minutes_since_prev > config.SILENCE_MINUTES)
    )
    # cumsum() turns True/False into 1, 2, 3... so every visit gets an ID.
    df["visit_id"] = new_visit.cumsum()

    # --- how long until we hear the ship again? ----------------------
    next_time = df.groupby("mmsi")["timestamp"].shift(-1)
    df["minutes_to_next"] = (next_time - df["timestamp"]).dt.total_seconds() / 60

    # The last ping of each visit tells us how the visit ended. A ping
    # is the last of a visit when the NEXT ping starts a new visit (the
    # final row of the table counts too).
    visits = df[new_visit.shift(-1, fill_value=True)].copy()

    # We cannot judge the very last ping of a ship (nothing comes after it).
    visits = visits.dropna(subset=["minutes_to_next"])

    # We also cannot judge a visit if the whole feed was down right
    # after it, because then every ship went silent at once.
    bin_seconds = config.FEED_BIN_MINUTES * 60
    next_bin = helpers.to_epoch_seconds(visits["timestamp"]) // bin_seconds + 1
    visits = visits[next_bin.isin(list(alive_bins))].copy()

    visits["went_silent"] = visits["minutes_to_next"] > config.SILENCE_MINUTES

    # --- summarise per cell ------------------------------------------
    cells = (
        visits.groupby(["cell_y", "cell_x"])
        .agg(n_visits=("went_silent", "size"), n_silent=("went_silent", "sum"))
        .reset_index()
    )
    cells["silence_rate"] = cells["n_silent"] / cells["n_visits"]
    cells["well_covered"] = (
        (cells["n_visits"] >= config.COVERAGE_MIN_VISITS)
        & (cells["silence_rate"] <= config.COVERAGE_MAX_SILENCE_RATE)
    )

    # Cell centre, only used for drawing the map.
    size = config.GRID_SIZE_DEG
    cells["lat"] = (cells["cell_y"] + 0.5) * size
    cells["lon"] = (cells["cell_x"] + 0.5) * size
    return cells


def run(df, output_folder):
    alive_bins = feed_alive_bins(df)
    cells = compute_coverage(df, alive_bins)

    os.makedirs(output_folder, exist_ok=True)
    out_path = os.path.join(output_folder, "coverage_cells.csv")
    cells.to_csv(out_path, index=False)

    n_good = int(cells["well_covered"].sum())
    print(f"\nCoverage: {n_good} of {len(cells)} grid cells are well covered")
    print(f"Saved {out_path}")
    return cells, alive_bins
