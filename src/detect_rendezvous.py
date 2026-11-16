"""
Step 5: find two ships that meet at sea.

A rendezvous is two different ships that stay within
RDV_MAX_DISTANCE_KM of each other, both moving slowly, outside any
port, for at least RDV_MIN_MINUTES.

How it works:
  1. keep only slow pings outside ports
  2. put time into 5 minute buckets, one position per ship per bucket
  3. join the table to itself on the bucket and a coarse grid cell
     (plus its 8 neighbours), which gives every pair of ships that were
     seen in the same 5 minutes and could be close enough to count
  4. keep the pairs that were close together
  5. glue neighbouring buckets of the same pair into one event
"""

import os

import numpy as np
import pandas as pd

import config
from src import helpers


def add_grid_cells(slow):
    """
    Put every position in a lat/lon grid cell at least
    RDV_MAX_DISTANCE_KM wide, so two ships that are close enough to
    count are always in the same cell or in neighbouring cells.

    Returns the number of longitude cells around the globe, so the
    caller can wrap neighbours across the 180 degree line.
    """
    # Slightly smaller than a real degree, so the cells come out a bit
    # wider than they need to be rather than a bit narrower.
    km_per_degree = 0.99 * np.pi * helpers.EARTH_RADIUS_KM / 180
    lat_step = config.RDV_MAX_DISTANCE_KM / km_per_degree

    # A degree of longitude shrinks towards the poles, so size the
    # longitude cells for the most northern / southern ship.
    max_abs_lat = min(float(slow["lat"].abs().max()) + lat_step, 90.0)
    cos_lat = np.cos(np.radians(max_abs_lat))
    if cos_lat * 360 > lat_step:
        lon_step = lat_step / cos_lat
    else:
        lon_step = 360.0
    n_lon_cells = max(int(360 // lon_step), 1)
    lon_step = 360.0 / n_lon_cells

    slow["lat_cell"] = np.floor((slow["lat"] + 90) / lat_step).astype("int64")
    slow["lon_cell"] = (np.floor((slow["lon"] + 180) / lon_step).astype("int64")) % n_lon_cells
    return n_lon_cells


def neighbour_cells(slow, n_lon_cells):
    """One row per ship per bucket for its own cell and each of the 8 around it."""
    lon_offsets = sorted({dx % n_lon_cells for dx in (-1, 0, 1)})
    copies = []
    for dy in (-1, 0, 1):
        for dx in lon_offsets:
            copy = slow.copy()
            copy["lat_cell"] = copy["lat_cell"] + dy
            copy["lon_cell"] = (copy["lon_cell"] + dx) % n_lon_cells
            copies.append(copy)
    return pd.concat(copies, ignore_index=True)


def find_rendezvous(df):
    columns = ["mmsi_a", "name_a", "type_a", "mmsi_b", "name_b", "type_b",
               "start", "end", "duration_minutes", "lat", "lon",
               "closest_km", "routine_type", "likely_routine"]
    empty = pd.DataFrame(columns=columns)

    # --- 1. slow pings outside ports ---------------------------------
    slow = df[df["sog"] < config.RDV_MAX_SPEED].copy()
    if len(slow) == 0:
        return empty
    slow = slow[~helpers.is_near_port(slow["lat"], slow["lon"])].copy()
    if len(slow) == 0:
        return empty

    # --- 2. one position per ship per 5 minute bucket ----------------
    bucket_seconds = config.RDV_BUCKET_MINUTES * 60
    seconds = helpers.to_epoch_seconds(slow["timestamp"])
    slow["bucket"] = (seconds // bucket_seconds) * bucket_seconds
    slow = slow.sort_values(["mmsi", "timestamp"])
    slow = slow.drop_duplicates(subset=["mmsi", "bucket"], keep="first")
    slow = slow[["mmsi", "vessel_name", "vessel_type", "bucket", "lat", "lon"]]

    # --- 3. every pair of nearby ships seen in the same bucket -------
    # Joining on the bucket alone would pair every ship with every other
    # ship in those 5 minutes, which grows with the square of the number
    # of ships. Only ships in the same or a neighbouring cell can be
    # close enough, so only those are paired.
    n_lon_cells = add_grid_cells(slow)
    pairs = slow.merge(
        neighbour_cells(slow, n_lon_cells),
        on=["bucket", "lat_cell", "lon_cell"],
        suffixes=("_a", "_b"),
    )
    # Keep each pair once (A-B but not B-A, and not A-A).
    pairs = pairs[pairs["mmsi_a"] < pairs["mmsi_b"]].copy()
    if len(pairs) == 0:
        return empty

    # --- 4. keep the pairs that were close ---------------------------
    pairs["distance_km"] = helpers.haversine_km(
        pairs["lat_a"], pairs["lon_a"], pairs["lat_b"], pairs["lon_b"]
    )
    close = pairs[pairs["distance_km"] <= config.RDV_MAX_DISTANCE_KM].copy()
    if len(close) == 0:
        return empty

    # --- 5. glue neighbouring buckets into events --------------------
    close = close.sort_values(["mmsi_a", "mmsi_b", "bucket"]).reset_index(drop=True)
    prev_bucket = close.groupby(["mmsi_a", "mmsi_b"])["bucket"].shift(1)
    # A new event starts for a new pair, or if the pair was apart for
    # more than two buckets (one missed bucket is forgiven).
    starts_new_event = prev_bucket.isna() | ((close["bucket"] - prev_bucket) > 2 * bucket_seconds)
    close["event_id"] = starts_new_event.cumsum()

    events = (
        close.groupby("event_id")
        .agg(
            mmsi_a=("mmsi_a", "first"),
            name_a=("vessel_name_a", "first"),
            type_a=("vessel_type_a", "first"),
            mmsi_b=("mmsi_b", "first"),
            name_b=("vessel_name_b", "first"),
            type_b=("vessel_type_b", "first"),
            first_bucket=("bucket", "min"),
            last_bucket=("bucket", "max"),
            lat=("lat_a", "mean"),
            lon=("lon_a", "mean"),
            closest_km=("distance_km", "min"),
        )
        .reset_index(drop=True)
    )

    # The last bucket covers 5 minutes itself, so add it on.
    events["duration_minutes"] = (
        events["last_bucket"] - events["first_bucket"] + bucket_seconds
    ) / 60
    events = events[events["duration_minutes"] >= config.RDV_MIN_MINUTES].copy()

    events["start"] = pd.to_datetime(events["first_bucket"], unit="s", utc=True)
    events["end"] = pd.to_datetime(events["last_bucket"] + bucket_seconds, unit="s", utc=True)

    # If either ship is a pilot boat, tug, fishing boat and so on,
    # the meeting is probably routine work.
    labels = []
    for type_a, type_b in zip(events["type_a"], events["type_b"]):
        label = helpers.routine_label(type_a) or helpers.routine_label(type_b)
        labels.append(label)
    events["routine_type"] = labels
    events["likely_routine"] = events["routine_type"] != ""

    events = events.sort_values(["likely_routine", "duration_minutes"], ascending=[True, False])
    return events[columns].reset_index(drop=True)


def run(df, output_folder):
    events = find_rendezvous(df)

    os.makedirs(output_folder, exist_ok=True)
    helpers.spreadsheet_safe(events).to_csv(os.path.join(output_folder, "rendezvous.csv"), index=False)

    n_routine = int(events["likely_routine"].sum()) if len(events) > 0 else 0
    print(f"\nRendezvous: {len(events)} meetings of {config.RDV_MIN_MINUTES}+ minutes "
          f"outside ports ({n_routine} involving ship types that do this routinely)")
    return events
