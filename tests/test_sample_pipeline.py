"""
Run the whole pipeline on the fake sample data and check that it finds
the events that were planted in it, and nothing it should not.
"""

import pytest

import make_sample_data
import review
from src import clean, coverage, detect_gaps, detect_loitering, detect_rendezvous

DARK_STAR = 316001001
SLOW_DRIFTER = 316001002
NORTHERN_TRADER = 316001003
ATLANTIC_SPIRIT = 316001004
LADY_LOBSTER = 316001005
SAMPLE_WARSHIP = 316001006


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    folder = tmp_path_factory.mktemp("sample")
    make_sample_data.generate(str(folder))
    positions = clean.load_raw_positions(str(folder))
    vessel_types = clean.load_vessel_types(str(folder))
    df, report = clean.clean_positions(positions, vessel_types)

    alive_bins = coverage.feed_alive_bins(df)
    cells = coverage.compute_coverage(df, alive_bins)
    return {
        "df": df,
        "cells": cells,
        "gaps": detect_gaps.find_gaps(df, cells, alive_bins),
        "loitering": detect_loitering.find_loitering(df),
        "rendezvous": detect_rendezvous.find_rendezvous(df),
    }


def test_junk_rows_are_gone(results):
    df = results["df"]
    assert 123 not in df["mmsi"].values
    assert 992351000 not in df["mmsi"].values
    assert not df.duplicated(subset=["mmsi", "timestamp"]).any()


def test_some_cells_are_well_covered_and_some_are_not(results):
    cells = results["cells"]
    assert cells["well_covered"].sum() > 0
    assert (~cells["well_covered"]).sum() > 0


def test_only_the_planted_gap_is_flagged(results):
    flagged = results["gaps"][results["gaps"]["flagged"]]
    assert flagged["mmsi"].tolist() == [DARK_STAR]
    assert 1.9 < flagged["gap_hours"].iloc[0] < 2.1


def test_dead_zone_gaps_are_candidates_but_not_flagged(results):
    gaps = results["gaps"]
    coasters = gaps[(gaps["mmsi"] >= 316200000) & (gaps["mmsi"] < 316300000)]
    assert len(coasters) > 0
    assert not coasters["flagged"].any()


def test_outage_gap_is_rejected_because_the_feed_was_down(results):
    gaps = results["gaps"]
    outage_gaps = gaps[gaps["mmsi"] == 316100099]
    assert len(outage_gaps) > 0
    assert not outage_gaps["feed_was_working"].iloc[0]
    assert not outage_gaps["flagged"].any()


def test_planted_loitering_is_found(results):
    loitering = results["loitering"]
    drifter = loitering[loitering["mmsi"] == SLOW_DRIFTER]
    assert len(drifter) == 1
    assert not drifter["likely_routine"].iloc[0]
    assert 4.5 < drifter["duration_hours"].iloc[0] < 5.5


def test_fishing_boat_is_found_but_marked_routine(results):
    loitering = results["loitering"]
    lobster = loitering[loitering["mmsi"] == LADY_LOBSTER]
    assert len(lobster) == 1
    assert lobster["likely_routine"].iloc[0]


def test_anchored_ships_in_port_are_not_loitering(results):
    loitering = results["loitering"]
    assert not ((loitering["mmsi"] >= 316400000) & (loitering["mmsi"] < 316500000)).any()


def test_planted_rendezvous_is_found(results):
    rendezvous = results["rendezvous"]
    assert len(rendezvous) == 1
    row = rendezvous.iloc[0]
    assert {row["mmsi_a"], row["mmsi_b"]} == {NORTHERN_TRADER, ATLANTIC_SPIRIT}


def test_warship_is_removed_and_never_flagged(results):
    assert SAMPLE_WARSHIP not in results["df"]["mmsi"].values
    assert SAMPLE_WARSHIP not in results["gaps"]["mmsi"].values


def test_map_popups_escape_ship_names(results, tmp_path):
    pytest.importorskip("folium")
    from src import make_map

    evil = "<b>EVIL</b>"
    gaps = results["gaps"].copy()
    gaps["vessel_name"] = evil
    loitering = results["loitering"].copy()
    loitering["vessel_name"] = evil
    rendezvous = results["rendezvous"].copy()
    rendezvous["name_a"] = evil
    rendezvous["name_b"] = evil
    assert gaps["flagged"].any() and len(loitering) > 0 and len(rendezvous) > 0

    make_map.make_interactive_map(results["df"].head(50), gaps, loitering,
                                  rendezvous, str(tmp_path))
    page = (tmp_path / "map.html").read_text()
    assert evil not in page
    assert "&lt;b&gt;EVIL&lt;/b&gt;" in page
    assert "<br>" in page


def test_review_sheet_escapes_formula_ship_names(results, tmp_path):
    df = results["df"].copy()
    df.loc[df["mmsi"] == DARK_STAR, "vessel_name"] = "=1+1"
    folder = str(tmp_path)
    alive_bins = coverage.feed_alive_bins(df)
    detect_gaps.run(df, results["cells"], alive_bins, folder)
    detect_loitering.run(df, folder)
    detect_rendezvous.run(df, folder)

    sheet = review.build_sheet(folder)
    gap_rows = sheet[sheet["detector"] == "gap"]
    assert list(gap_rows["ships"]) == [f"'=1+1 ({DARK_STAR})"]
