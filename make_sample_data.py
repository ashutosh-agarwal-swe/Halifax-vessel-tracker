"""
Make FAKE sample data so the pipeline can be run and tested without
waiting weeks for real data.

*** Nothing in data/sample/ is real. Every ship is invented. ***

The fake data has known answers planted in it, which is what makes it
useful for testing:

  - DARK STAR        goes silent for 2 hours in open, well covered water
  - SLOW DRIFTER     sits still out at sea for 5 hours
  - NORTHERN TRADER and ATLANTIC SPIRIT meet at sea for an hour
  - LADY LOBSTER     a fishing boat that loiters (should be marked routine)

It also has things that should NOT be flagged:

  - a "dead zone" in the east where no ship is ever heard
  - SAMPLE WARSHIP, a military ship that goes silent (removed in cleaning)
  - a 2 hour outage where the whole feed goes down
  - ships that stop transmitting in port or leave the study area
  - junk rows (bad ship IDs, impossible positions, duplicates, a GPS glitch)

The fake ships live in the made-up area defined by
config.use_sample_area(), not in the real study area, so changing the
real study area never breaks the sample data or the tests.

Usage:
    python make_sample_data.py
"""

import os

import numpy as np
import pandas as pd

SAMPLE_FOLDER = os.path.join("data", "sample")
FIRST_DAY = pd.Timestamp("2026-01-05 00:00:00")
N_DAYS = 3
KM_PER_KNOT_HOUR = 1.852

# Places (latitude, longitude)
HARBOUR = (44.62, -63.55)
SEA_EXIT = (44.10, -63.30)      # south of the sample area, so ships leave the box
EAST_END = (44.40, -63.12)      # inside the dead zone
TOUR_TURN = (44.50, -63.80)     # where the tour boat turns round

DEAD_ZONE_LON = -63.30          # nothing east of this line is ever heard
OUTAGE_START = FIRST_DAY + pd.Timedelta(hours=27)   # day 2, 03:00
OUTAGE_END = FIRST_DAY + pd.Timedelta(hours=29)     # day 2, 05:00


def distance_km(p1, p2):
    """Rough distance, good enough for making fake tracks."""
    dlat = (p2[0] - p1[0]) * 111.0
    dlon = (p2[1] - p1[1]) * 111.0 * np.cos(np.radians((p1[0] + p2[0]) / 2))
    return np.sqrt(dlat ** 2 + dlon ** 2)


def make_transit(rng, mmsi, name, start_time, p1, p2, speed_knots):
    """A ship sailing in a straight line from p1 to p2, one ping a minute."""
    hours = distance_km(p1, p2) / (speed_knots * KM_PER_KNOT_HOUR)
    n = int(hours * 60)
    fraction = np.linspace(0, 1, n)
    return pd.DataFrame({
        "mmsi": mmsi,
        "timestamp": start_time + pd.to_timedelta(np.arange(n), unit="min"),
        "lat": p1[0] + (p2[0] - p1[0]) * fraction + rng.normal(0, 0.0003, n),
        "lon": p1[1] + (p2[1] - p1[1]) * fraction + rng.normal(0, 0.0003, n),
        "sog": speed_knots + rng.normal(0, 0.3, n),
        "cog": 200.0,
        "vessel_name": name,
    })


def make_stationary(rng, mmsi, name, start_time, hours, lat, lon):
    """A ship sitting almost still, one ping a minute."""
    n = int(hours * 60)
    return pd.DataFrame({
        "mmsi": mmsi,
        "timestamp": start_time + pd.to_timedelta(np.arange(n), unit="min"),
        "lat": lat + rng.normal(0, 0.0004, n),
        "lon": lon + rng.normal(0, 0.0004, n),
        "sog": np.abs(rng.normal(0.3, 0.1, n)),
        "cog": 0.0,
        "vessel_name": name,
    })


def shifted(point, offset_lon):
    """Move a point sideways a little so ships do not all use one exact line."""
    return (point[0], point[1] + offset_lon)


def generate(folder=SAMPLE_FOLDER, seed=42):
    rng = np.random.default_rng(seed)
    tracks = []
    static_rows = []
    total_hours = N_DAYS * 24

    # --- ordinary cargo ships and tankers on the main lane -----------
    for i in range(20):
        mmsi = 316100000 + i
        name = f"SAMPLE CARGO {i + 1:02d}"
        vessel_type = 70 if i % 2 == 0 else 80
        static_rows.append((mmsi, name, vessel_type, 180))
        offset = rng.uniform(-0.02, 0.02)
        speed = rng.uniform(9, 14)
        outbound = i % 2 == 0
        hour = rng.uniform(0, 8)
        while hour < total_hours - 6:
            if outbound:
                p1, p2 = shifted(HARBOUR, offset), shifted(SEA_EXIT, offset)
            else:
                p1, p2 = shifted(SEA_EXIT, offset), shifted(HARBOUR, offset)
            start = FIRST_DAY + pd.Timedelta(hours=hour)
            tracks.append(make_transit(rng, mmsi, name, start, p1, p2, speed))
            outbound = not outbound
            hour += rng.uniform(12, 20)

    # One slow ship that is definitely out at sea, inside the area,
    # for the whole outage.
    static_rows.append((316100099, "SAMPLE CARGO 99", 70, 200))
    tracks.append(make_transit(rng, 316100099, "SAMPLE CARGO 99",
                               OUTAGE_START - pd.Timedelta(minutes=70),
                               HARBOUR, SEA_EXIT, 6))

    # --- ships that sail into the dead zone and back ------------------
    for i in range(8):
        mmsi = 316200000 + i
        name = f"SAMPLE COASTER {i + 1:02d}"
        static_rows.append((mmsi, name, 70, 90))
        offset = rng.uniform(-0.01, 0.01)
        speed = rng.uniform(10, 13)
        hour = rng.uniform(0, 10)
        while hour < total_hours - 10:
            start = FIRST_DAY + pd.Timedelta(hours=hour)
            out = make_transit(rng, mmsi, name, start,
                               shifted(HARBOUR, offset), shifted(EAST_END, offset), speed)
            back_start = out["timestamp"].iloc[-1] + pd.Timedelta(minutes=1)
            back = make_transit(rng, mmsi, name, back_start,
                                shifted(EAST_END, offset), shifted(HARBOUR, offset), speed)
            tracks.append(out)
            tracks.append(back)
            hour += rng.uniform(16, 24)

    # --- a tour boat: out to a turning point and straight back, twice a day
    static_rows.append((316300001, "SAMPLE TOUR BOAT", 60, 30))
    for day in range(N_DAYS):
        for depart_hour in [9, 14]:
            start = FIRST_DAY + pd.Timedelta(hours=day * 24 + depart_hour)
            out = make_transit(rng, 316300001, "SAMPLE TOUR BOAT", start, HARBOUR, TOUR_TURN, 12)
            back_start = out["timestamp"].iloc[-1] + pd.Timedelta(minutes=1)
            back = make_transit(rng, 316300001, "SAMPLE TOUR BOAT", back_start,
                                TOUR_TURN, HARBOUR, 12)
            tracks.append(out)
            tracks.append(back)

    # --- ships at anchor in the harbour for the whole period ----------
    for i in range(3):
        mmsi = 316400000 + i
        name = f"SAMPLE ANCHORED {i + 1}"
        static_rows.append((mmsi, name, 80, 230))
        tracks.append(make_stationary(rng, mmsi, name, FIRST_DAY, total_hours,
                                      44.63 + 0.01 * i, -63.56 - 0.01 * i))

    # --- PLANTED: a ship that goes dark in open water ----------------
    static_rows.append((316001001, "DARK STAR", 70, 190))
    dark = make_transit(rng, 316001001, "DARK STAR",
                        FIRST_DAY + pd.Timedelta(hours=34), HARBOUR, SEA_EXIT, 7)
    silent_from = dark["timestamp"].iloc[0] + pd.Timedelta(minutes=65)
    silent_to = dark["timestamp"].iloc[0] + pd.Timedelta(minutes=185)
    dark = dark[(dark["timestamp"] < silent_from) | (dark["timestamp"] >= silent_to)]
    tracks.append(dark)

    # --- a warship that does exactly the same thing ------------------
    # Military ships are removed during cleaning, so this must NOT be flagged.
    static_rows.append((316001006, "SAMPLE WARSHIP", 35, 130))
    warship = make_transit(rng, 316001006, "SAMPLE WARSHIP",
                           FIRST_DAY + pd.Timedelta(hours=44), HARBOUR, SEA_EXIT, 7)
    silent_from = warship["timestamp"].iloc[0] + pd.Timedelta(minutes=65)
    silent_to = warship["timestamp"].iloc[0] + pd.Timedelta(minutes=185)
    warship = warship[(warship["timestamp"] < silent_from) | (warship["timestamp"] >= silent_to)]
    tracks.append(warship)

    # --- PLANTED: a tanker loitering out at sea ----------------------
    static_rows.append((316001002, "SLOW DRIFTER", 80, 240))
    tracks.append(make_stationary(rng, 316001002, "SLOW DRIFTER",
                                  FIRST_DAY + pd.Timedelta(hours=14), 5, 44.40, -63.60))

    # --- PLANTED: two ships meeting at sea ---------------------------
    static_rows.append((316001003, "NORTHERN TRADER", 70, 150))
    static_rows.append((316001004, "ATLANTIC SPIRIT", 80, 110))
    meet_time = FIRST_DAY + pd.Timedelta(hours=56)
    tracks.append(make_stationary(rng, 316001003, "NORTHERN TRADER", meet_time, 1, 44.350, -63.700))
    tracks.append(make_stationary(rng, 316001004, "ATLANTIC SPIRIT", meet_time, 1, 44.351, -63.701))

    # --- PLANTED: a fishing boat working one spot (routine) ----------
    static_rows.append((316001005, "LADY LOBSTER", 30, 14))
    tracks.append(make_stationary(rng, 316001005, "LADY LOBSTER",
                                  FIRST_DAY + pd.Timedelta(hours=30), 4, 44.47, -63.40))

    positions = pd.concat(tracks, ignore_index=True)

    # --- things that make the data realistic and messy ---------------
    # 1. the dead zone: nothing east of the line is heard
    positions = positions[positions["lon"] <= DEAD_ZONE_LON]
    # 2. the outage: nothing at all is heard for two hours
    in_outage = (positions["timestamp"] >= OUTAGE_START) & (positions["timestamp"] < OUTAGE_END)
    positions = positions[~in_outage].reset_index(drop=True)
    # 3. a GPS glitch: one ping of one ship jumps 17 km north
    glitch_row = positions[positions["mmsi"] == 316100003].index[150]
    positions.loc[glitch_row, "lat"] += 0.15
    # 4. duplicate rows
    positions = pd.concat([positions, positions.sample(200, random_state=seed)])
    # 5. junk rows
    junk = pd.DataFrame({
        "mmsi": [123, 316100001, 992351000],
        "timestamp": [FIRST_DAY + pd.Timedelta(hours=1)] * 3,
        "lat": [44.5, 91.0, 44.6],
        "lon": [-63.5, 181.0, -63.6],
        "sog": [5.0, 102.3, 0.0],
        "cog": [0.0, 0.0, 0.0],
        "vessel_name": ["BAD ID", "NO POSITION", "A BUOY"],
    })
    positions = pd.concat([positions, junk], ignore_index=True)

    # --- save one file per day, like the real collector does ---------
    os.makedirs(folder, exist_ok=True)
    positions["sog"] = positions["sog"].clip(lower=0).round(1)
    positions["lat"] = positions["lat"].round(5)
    positions["lon"] = positions["lon"].round(5)
    positions = positions.sort_values("timestamp")
    positions["day"] = positions["timestamp"].dt.strftime("%Y-%m-%d")
    positions["timestamp"] = positions["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    for day, rows in positions.groupby("day"):
        rows.drop(columns=["day"]).to_csv(
            os.path.join(folder, f"positions_{day}.csv"), index=False)

    static = pd.DataFrame(static_rows, columns=["mmsi", "vessel_name", "vessel_type", "length_m"])
    static["timestamp"] = FIRST_DAY.strftime("%Y-%m-%d %H:%M:%S")
    static["destination"] = ""
    static = static[["mmsi", "timestamp", "vessel_name", "vessel_type", "length_m", "destination"]]
    static.to_csv(os.path.join(folder, f"static_{FIRST_DAY.strftime('%Y-%m-%d')}.csv"), index=False)

    print(f"Wrote {len(positions):,} fake position rows for {len(static)} fake ships to {folder}")


if __name__ == "__main__":
    generate()
