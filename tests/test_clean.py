import pandas as pd

from src import clean


def make_rows(rows):
    columns = ["mmsi", "timestamp", "lat", "lon", "sog", "cog", "vessel_name"]
    return pd.DataFrame(rows, columns=columns)


def test_invalid_ship_ids_are_removed():
    raw = make_rows([
        [316000001, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "GOOD"],
        [123, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "TOO SHORT"],
        [992351000, "2026-01-05 00:00:00", 44.5, -63.5, 0, 0, "BUOY"],
    ])
    df, report = clean.clean_positions(raw)
    assert df["mmsi"].tolist() == [316000001]


def test_positions_outside_study_area_are_removed():
    raw = make_rows([
        [316000001, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "IN"],
        [316000001, "2026-01-05 00:05:00", 91.0, 181.0, 10, 0, "NO POSITION"],
        [316000001, "2026-01-05 00:10:00", 40.0, -70.0, 10, 0, "BOSTON"],
    ])
    df, report = clean.clean_positions(raw)
    assert len(df) == 1


def test_duplicates_and_extra_pings_in_the_same_minute_are_removed():
    raw = make_rows([
        [316000001, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "A"],
        [316000001, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "A"],
        [316000001, "2026-01-05 00:00:30", 44.5, -63.5, 10, 0, "A"],
        [316000001, "2026-01-05 00:01:00", 44.5, -63.5, 10, 0, "A"],
    ])
    df, report = clean.clean_positions(raw)
    assert len(df) == 2


def test_gps_glitch_is_removed_but_neighbours_are_kept():
    raw = make_rows([
        [316000001, "2026-01-05 00:00:00", 44.500, -63.5, 10, 0, "A"],
        [316000001, "2026-01-05 00:01:00", 44.503, -63.5, 10, 0, "A"],
        [316000001, "2026-01-05 00:02:00", 44.790, -63.5, 10, 0, "A"],  # 32 km in a minute
        [316000001, "2026-01-05 00:03:00", 44.509, -63.5, 10, 0, "A"],
        [316000001, "2026-01-05 00:04:00", 44.512, -63.5, 10, 0, "A"],
    ])
    df, report = clean.clean_positions(raw)
    assert len(df) == 4
    assert df["lat"].max() < 44.6


def test_unknown_speed_code_becomes_missing():
    raw = make_rows([
        [316000001, "2026-01-05 00:00:00", 44.5, -63.5, 102.3, 0, "A"],
    ])
    df, report = clean.clean_positions(raw)
    assert df["sog"].isna().all()


def test_military_ships_are_removed():
    raw = make_rows([
        [316000001, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "CARGO"],
        [316000002, "2026-01-05 00:00:00", 44.5, -63.5, 10, 0, "WARSHIP"],
    ])
    types = pd.DataFrame({"mmsi": [316000001, 316000002],
                          "vessel_type": [70, 35], "length_m": [100, 130]})
    df, report = clean.clean_positions(raw, types)
    assert df["mmsi"].tolist() == [316000001]
