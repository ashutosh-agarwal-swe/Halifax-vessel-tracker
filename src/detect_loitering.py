"""
Step 4: find ships that sit almost still at sea for a long time.

A "loitering run" is a stretch of pings from one ship where:
  - every ping is slower than LOITER_MAX_SPEED
  - there is no long silence in the middle
  - the whole stretch lasts at least LOITER_MIN_HOURS
  - it happens outside the port circles

Fishing boats, tugs, pilot boats and ferries do this as part of their
job, so they are kept in the results but marked "likely_routine".
"""

import os

import pandas as pd

import config
from src import helpers


def find_loitering(df):
    columns = ["mmsi", "vessel_name", "vessel_type", "start", "end",
               "duration_hours", "lat", "lon", "n_pings", "mean_speed_knots",
               "km_from_port", "routine_type", "likely_routine"]

    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    # A ping with no speed value is not counted as slow.
    df["is_slow"] = df["sog"] < config.LOITER_MAX_SPEED

    prev_mmsi = df["mmsi"].shift(1)
    prev_slow = df["is_slow"].shift(1, fill_value=False)
    prev_time = df.groupby("mmsi")["timestamp"].shift(1)
    minutes_since_prev = (df["timestamp"] - prev_time).dt.total_seconds() / 60

    # A new run starts at a slow ping when the ping before it was
    # a different ship, was not slow, or was a long time ago.
    starts_new_run = df["is_slow"] & (
        (df["mmsi"] != prev_mmsi)
        | (~prev_slow)
        | (minutes_since_prev > config.LOITER_MAX_PING_GAP_MIN)
    )
    # cumsum() gives every run its own number.
    df["run_id"] = starts_new_run.cumsum()

    slow = df[df["is_slow"]]
    if len(slow) == 0:
        return pd.DataFrame(columns=columns)

    runs = (
        slow.groupby("run_id")
        .agg(
            mmsi=("mmsi", "first"),
            vessel_name=("vessel_name", "first"),
            vessel_type=("vessel_type", "first"),
            start=("timestamp", "min"),
            end=("timestamp", "max"),
            lat=("lat", "mean"),
            lon=("lon", "mean"),
            n_pings=("timestamp", "size"),
            mean_speed_knots=("sog", "mean"),
        )
        .reset_index(drop=True)
    )

    runs["duration_hours"] = (runs["end"] - runs["start"]).dt.total_seconds() / 3600
    runs = runs[runs["duration_hours"] >= config.LOITER_MIN_HOURS].copy()

    # Keep only runs outside the port circles.
    runs["km_from_port"] = helpers.km_to_nearest_port(runs["lat"], runs["lon"])
    runs = runs[runs["km_from_port"] > 0].copy()

    runs["routine_type"] = [helpers.routine_label(t) for t in runs["vessel_type"]]
    runs["likely_routine"] = runs["routine_type"] != ""

    # Most interesting first: not routine, then longest.
    runs = runs.sort_values(["likely_routine", "duration_hours"], ascending=[True, False])
    return runs[columns].reset_index(drop=True)


def run(df, output_folder):
    loitering = find_loitering(df)

    os.makedirs(output_folder, exist_ok=True)
    loitering.to_csv(os.path.join(output_folder, "loitering.csv"), index=False)

    n_routine = int(loitering["likely_routine"].sum()) if len(loitering) > 0 else 0
    print(f"\nLoitering: {len(loitering)} runs of {config.LOITER_MIN_HOURS}+ hours "
          f"outside ports ({n_routine} by ship types that do this routinely)")
    return loitering
