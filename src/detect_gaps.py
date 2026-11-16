"""
Step 3: find ships that "went dark".

A gap is a long silence between two pings of the same ship.
Most gaps are innocent, so every gap has to pass six checks before it
is flagged:

  1. the ship was moving before it went silent
  2. the gap started in a well covered grid cell
  3. the gap did not start in a port
  4. the gap did not start at the edge of the study area
  5. the data feed was working during the gap, and in its first hour
  6. the straight line from where the ship vanished to where it came
     back runs through well covered water

Every gap is saved together with which checks it passed, so it is easy
to see why something was or was not flagged.
"""

import os

import numpy as np
import pandas as pd

import config
from src import helpers


def feed_alive_fractions(start_seconds, end_seconds, alive_bins):
    """
    For every gap, what share of the time bins between start and end
    had any data? Returns one number per gap.
    """
    bin_seconds = config.FEED_BIN_MINUTES * 60
    first_bin = np.asarray(start_seconds) // bin_seconds + 1
    last_bin = np.asarray(end_seconds) // bin_seconds - 1

    total = np.maximum(last_bin - first_bin + 1, 0)
    sorted_bins = np.array(sorted(alive_bins), dtype=np.int64)
    alive = (np.searchsorted(sorted_bins, last_bin + 1)
             - np.searchsorted(sorted_bins, first_bin))
    return np.where(total > 0, alive / np.maximum(total, 1), 1.0)


def path_covered_fractions(start_lat, start_lon, end_lat, end_lon, good_cells):
    """
    For every gap, walk along the straight line from start to end in 20
    steps and count how many of those points are in a well covered cell.

    Ships do not sail in perfectly straight lines, so this is only a
    rough check.
    """
    steps = np.linspace(0, 1, 20)
    start_lat = np.asarray(start_lat, dtype=float)[:, None]
    end_lat = np.asarray(end_lat, dtype=float)[:, None]
    start_lon = np.asarray(start_lon, dtype=float)[:, None]
    end_lon = np.asarray(end_lon, dtype=float)[:, None]
    lats = start_lat + (end_lat - start_lat) * steps
    lons = start_lon + (end_lon - start_lon) * steps
    cell_y, cell_x = helpers.cell_index(lats, lons)

    points = pd.MultiIndex.from_arrays([cell_y.ravel(), cell_x.ravel()])
    covered = points.isin(good_cells).reshape(lats.shape)
    return covered.mean(axis=1)


def find_gaps(df, cells, alive_bins):
    """
    Return a table with one row per gap of at least GAP_MIN_MINUTES,
    including the result of every check and a final 'flagged' column.
    """
    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    # Look one row ahead within each ship to find the next ping.
    df[["next_time", "next_lat", "next_lon"]] = (
        df.groupby("mmsi")[["timestamp", "lat", "lon"]].shift(-1)
    )
    df["gap_minutes"] = (df["next_time"] - df["timestamp"]).dt.total_seconds() / 60

    gaps = df[df["gap_minutes"] >= config.GAP_MIN_MINUTES].copy()

    columns = ["mmsi", "vessel_name", "vessel_type", "gap_start", "gap_end",
               "gap_hours", "start_lat", "start_lon", "end_lat", "end_lon",
               "distance_km", "implied_speed_knots", "speed_before_knots",
               "was_moving", "start_well_covered", "away_from_port",
               "away_from_edge", "feed_alive_fraction", "feed_alive_at_start",
               "feed_was_working",
               "path_covered_fraction", "path_is_covered", "flagged"]
    if len(gaps) == 0:
        return pd.DataFrame(columns=columns)

    gaps = gaps.rename(columns={
        "timestamp": "gap_start",
        "next_time": "gap_end",
        "lat": "start_lat",
        "lon": "start_lon",
        "next_lat": "end_lat",
        "next_lon": "end_lon",
        "sog": "speed_before_knots",
    })
    gaps["gap_hours"] = gaps["gap_minutes"] / 60

    # How far did the ship move while silent, and how fast would it
    # have needed to go?
    gaps["distance_km"] = helpers.haversine_km(
        gaps["start_lat"], gaps["start_lon"], gaps["end_lat"], gaps["end_lon"]
    )
    gaps["implied_speed_knots"] = (
        gaps["distance_km"] / helpers.KM_PER_NAUTICAL_MILE / gaps["gap_hours"]
    )

    # --- check 1: moving before the gap -------------------------------
    gaps["was_moving"] = gaps["speed_before_knots"] >= config.GAP_MIN_SPEED_BEFORE

    # --- check 2: started in a well covered cell ----------------------
    good_cells = pd.MultiIndex.from_frame(
        cells.loc[cells["well_covered"], ["cell_y", "cell_x"]]
    )
    cell_y, cell_x = helpers.cell_index(gaps["start_lat"], gaps["start_lon"])
    gaps["start_well_covered"] = pd.MultiIndex.from_arrays(
        [cell_y, cell_x]).isin(good_cells)

    # --- checks 3 and 4: not in a port, not at the edge ---------------
    gaps["away_from_port"] = ~helpers.is_near_port(gaps["start_lat"], gaps["start_lon"])
    gaps["away_from_edge"] = ~helpers.is_near_edge(gaps["start_lat"], gaps["start_lon"])

    # --- check 5: the feed was working --------------------------------
    start_seconds = helpers.to_epoch_seconds(gaps["gap_start"]).to_numpy()
    end_seconds = helpers.to_epoch_seconds(gaps["gap_end"]).to_numpy()
    # Looked at twice: over the whole gap, and over just its beginning.
    # The beginning matters most, because if the feed died right when
    # the ship went silent we cannot know what the ship did next.
    check_end = np.minimum(
        end_seconds, start_seconds + config.GAP_FIRST_CHECK_MINUTES * 60)
    gaps["feed_alive_fraction"] = feed_alive_fractions(
        start_seconds, end_seconds, alive_bins)
    gaps["feed_alive_at_start"] = feed_alive_fractions(
        start_seconds, check_end, alive_bins)
    gaps["feed_was_working"] = (
        (gaps["feed_alive_fraction"] >= config.GAP_MIN_FEED_ALIVE)
        & (gaps["feed_alive_at_start"] >= config.GAP_MIN_FEED_ALIVE)
    )

    # --- check 6: the path is through covered water -------------------
    gaps["path_covered_fraction"] = path_covered_fractions(
        gaps["start_lat"], gaps["start_lon"],
        gaps["end_lat"], gaps["end_lon"], good_cells)
    gaps["path_is_covered"] = gaps["path_covered_fraction"] >= config.GAP_MIN_PATH_COVERED

    # --- final decision ----------------------------------------------
    gaps["flagged"] = (
        gaps["was_moving"]
        & gaps["start_well_covered"]
        & gaps["away_from_port"]
        & gaps["away_from_edge"]
        & gaps["feed_was_working"]
        & gaps["path_is_covered"]
    )

    gaps = gaps.sort_values(["flagged", "gap_hours"], ascending=[False, False])
    return gaps[columns].reset_index(drop=True)


def run(df, cells, alive_bins, output_folder):
    gaps = find_gaps(df, cells, alive_bins)

    os.makedirs(output_folder, exist_ok=True)
    helpers.spreadsheet_safe(gaps).to_csv(os.path.join(output_folder, "gaps_all_candidates.csv"), index=False)
    flagged = gaps[gaps["flagged"]]
    helpers.spreadsheet_safe(flagged).to_csv(os.path.join(output_folder, "gaps_flagged.csv"), index=False)

    print(f"\nGaps: {len(gaps)} silences of {config.GAP_MIN_MINUTES}+ minutes, "
          f"{len(flagged)} flagged after all checks")
    return gaps
