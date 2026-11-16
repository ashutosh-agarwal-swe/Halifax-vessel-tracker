import collect_ais


def test_position_message_is_parsed():
    message = {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 316001234, "ShipName": "TEST SHIP  ",
                     "latitude": 44.6, "longitude": -63.55,
                     "time_utc": "2026-01-05 12:34:56.123456789 +0000 UTC"},
        "Message": {"PositionReport": {"UserID": 316001234, "Sog": 11.2, "Cog": 201.5,
                                       "Latitude": 44.61, "Longitude": -63.56}},
    }
    kind, row = collect_ais.parse_message(message)
    assert kind == "position"
    assert row["mmsi"] == 316001234
    assert row["lat"] == 44.61
    assert row["sog"] == 11.2
    assert row["vessel_name"] == "TEST SHIP"
    assert row["timestamp"] == "2026-01-05 12:34:56"


def test_position_falls_back_to_metadata_with_capital_letters():
    message = {
        "MessageType": "StandardClassBPositionReport",
        "MetaData": {"MMSI": 316001234, "ShipName": "SMALL BOAT",
                     "Latitude": 44.6, "Longitude": -63.55},
        "Message": {"StandardClassBPositionReport": {"Sog": 4.0, "Cog": 90.0}},
    }
    kind, row = collect_ais.parse_message(message)
    assert kind == "position"
    assert row["lat"] == 44.6
    assert len(row["timestamp"]) == 19


def test_static_message_is_parsed():
    message = {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 316001234, "ShipName": "TEST SHIP"},
        "Message": {"ShipStaticData": {"Name": "TEST SHIP", "Type": 80,
                                       "Dimension": {"A": 150, "B": 30, "C": 10, "D": 10},
                                       "Destination": "SAINT JOHN"}},
    }
    kind, row = collect_ais.parse_message(message)
    assert kind == "static"
    assert row["vessel_type"] == 80
    assert row["length_m"] == 180


def test_other_messages_are_ignored():
    kind, row = collect_ais.parse_message({"MessageType": "BaseStationReport",
                                           "MetaData": {"MMSI": 3160001}})
    assert kind is None


def test_only_one_position_per_minute_is_saved():
    collect_ais.last_saved.clear()
    assert collect_ais.should_save_position(316001234, 1000)
    assert not collect_ais.should_save_position(316001234, 1030)
    assert collect_ais.should_save_position(316001234, 1061)
