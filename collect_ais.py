"""
Collect live ship positions for the study area from aisstream.io.

aisstream.io is a free service that sends AIS messages over a
websocket (a connection that stays open and keeps sending data).
There is no free archive of AIS data for Canadian waters, so this
script builds its own archive by listening and saving what it hears.

Usage:
    python collect_ais.py                 # run until you press Ctrl+C
    python collect_ais.py --minutes 30    # run for 30 minutes (good for a first test)

Output (in data/raw/):
    positions_YYYY-MM-DD.csv   one row per ship per minute
    static_YYYY-MM-DD.csv      ship name, type and length
    collector_log.csv          when the collector connected / disconnected

See docs/DATA_DOWNLOAD.md for the full step by step instructions.
"""

import argparse
import asyncio
import csv
import json
import os
import random
import time
from datetime import datetime, timezone

import config

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
RAW_FOLDER = os.path.join("data", "raw")

POSITION_COLUMNS = ["mmsi", "timestamp", "lat", "lon", "sog", "cog", "vessel_name"]
STATIC_COLUMNS = ["mmsi", "timestamp", "vessel_name", "vessel_type", "length_m", "destination"]

POSITION_MESSAGES = ["PositionReport", "StandardClassBPositionReport",
                     "ExtendedClassBPositionReport"]
STATIC_MESSAGES = ["ShipStaticData", "StaticDataReport"]

# Remembers when we last saved a position for each ship, so we only
# keep one per minute. {mmsi: seconds}
last_saved = {}

# CSV files are kept open between rows so we do not open and close a
# file for every single message. {path: (file, writer)}
open_files = {}


def get_api_key():
    """Read the API key from an environment variable or from api_key.txt."""
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists("api_key.txt"):
        with open("api_key.txt") as f:
            key = f.read().strip()
        if key:
            return key
    raise SystemExit(
        "No API key found. Put your aisstream.io key in a file called "
        "api_key.txt in this folder (see docs/DATA_DOWNLOAD.md)."
    )


def get_any(dictionary, name, default=None):
    """
    Look up a key without caring about upper or lower case.

    The aisstream documentation and the real messages do not always
    agree on capital letters (for example "latitude" vs "Latitude").
    """
    if not isinstance(dictionary, dict):
        return default
    for key, value in dictionary.items():
        if key.lower() == name.lower():
            return value
    return default


def message_time(meta):
    """
    Return the message time as "YYYY-MM-DD HH:MM:SS" in UTC.

    Uses the time in the message if there is one, otherwise the time
    on this computer.
    """
    text = get_any(meta, "time_utc")
    if isinstance(text, str) and len(text) >= 19:
        candidate = text[:19].replace("T", " ")
        try:
            datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
            return candidate
        except ValueError:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_message(message):
    """
    Turn one aisstream message into a row we can save.

    Returns ("position", row), ("static", row) or (None, None) if the
    message is not one we use.
    """
    message_type = get_any(message, "MessageType")
    meta = get_any(message, "MetaData", {})
    body = get_any(get_any(message, "Message", {}), message_type or "", {})

    mmsi = get_any(meta, "MMSI")
    if mmsi is None:
        mmsi = get_any(body, "UserID")
    if mmsi is None:
        return None, None

    name = str(get_any(meta, "ShipName", "") or "").strip()
    timestamp = message_time(meta)

    if message_type in POSITION_MESSAGES:
        lat = get_any(body, "Latitude")
        lon = get_any(body, "Longitude")
        if lat is None or lon is None:
            lat = get_any(meta, "Latitude")
            lon = get_any(meta, "Longitude")
        if lat is None or lon is None:
            return None, None
        row = {
            "mmsi": mmsi,
            "timestamp": timestamp,
            "lat": lat,
            "lon": lon,
            "sog": get_any(body, "Sog"),
            "cog": get_any(body, "Cog"),
            "vessel_name": name,
        }
        return "position", row

    if message_type == "ShipStaticData":
        dimension = get_any(body, "Dimension", {})
        length = None
        bow = get_any(dimension, "A")
        stern = get_any(dimension, "B")
        if bow is not None and stern is not None:
            length = bow + stern
        row = {
            "mmsi": mmsi,
            "timestamp": timestamp,
            "vessel_name": str(get_any(body, "Name", name) or name).strip(),
            "vessel_type": get_any(body, "Type"),
            "length_m": length,
            "destination": str(get_any(body, "Destination", "") or "").strip(),
        }
        return "static", row

    if message_type == "StaticDataReport":
        # Smaller boats (Class B) send their details in two parts.
        report_a = get_any(body, "ReportA", {})
        report_b = get_any(body, "ReportB", {})
        dimension = get_any(report_b, "Dimension", {})
        length = None
        bow = get_any(dimension, "A")
        stern = get_any(dimension, "B")
        if bow is not None and stern is not None:
            length = bow + stern
        row = {
            "mmsi": mmsi,
            "timestamp": timestamp,
            "vessel_name": str(get_any(report_a, "Name", name) or name).strip(),
            "vessel_type": get_any(report_b, "ShipType"),
            "length_m": length,
            "destination": "",
        }
        return "static", row

    return None, None


def should_save_position(mmsi, now_seconds):
    """Only keep one position per ship per DOWNSAMPLE_SECONDS."""
    previous = last_saved.get(mmsi)
    if previous is not None and now_seconds - previous < config.DOWNSAMPLE_SECONDS:
        return False
    last_saved[mmsi] = now_seconds
    return True


def append_row(path, columns, row):
    """Add one row to a CSV file, writing the header if the file is new."""
    if path not in open_files:
        is_new = not os.path.exists(path) or os.path.getsize(path) == 0
        f = open(path, "a", newline="", encoding="utf-8")
        writer = csv.DictWriter(f, fieldnames=columns)
        if is_new:
            writer.writeheader()
        open_files[path] = (f, writer)
    f, writer = open_files[path]
    writer.writerow(row)
    # Flush every row so a crash or power cut loses almost nothing.
    f.flush()


def close_files():
    """Close every open CSV file. Called when the collector stops."""
    for f, writer in open_files.values():
        f.close()
    open_files.clear()


def log_event(event):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    append_row(os.path.join(RAW_FOLDER, "collector_log.csv"),
               ["timestamp", "event"], {"timestamp": now, "event": event})
    print(f"[{now} UTC] {event}")


def save(kind, row):
    day = row["timestamp"][:10]
    if kind == "position":
        path = os.path.join(RAW_FOLDER, f"positions_{day}.csv")
        append_row(path, POSITION_COLUMNS, row)
    else:
        path = os.path.join(RAW_FOLDER, f"static_{day}.csv")
        append_row(path, STATIC_COLUMNS, row)


async def collect(api_key, minutes):
    import websockets  # imported here so the tests do not need it

    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[config.LAT_MIN, config.LON_MIN],
                           [config.LAT_MAX, config.LON_MAX]]],
        "FilterMessageTypes": POSITION_MESSAGES + STATIC_MESSAGES,
    }

    started = time.time()
    positions_saved = 0
    ships_seen = set()
    last_status = time.time()
    wait_seconds = 5

    while True:
        try:
            async with websockets.connect(STREAM_URL) as websocket:
                # aisstream closes the connection if this is not sent
                # within 3 seconds of connecting.
                await websocket.send(json.dumps(subscription))
                log_event("connected")
                wait_seconds = 5

                while True:
                    if minutes is not None and time.time() - started > minutes * 60:
                        log_event(f"finished after {minutes} minutes")
                        print(f"Saved {positions_saved} positions from "
                              f"{len(ships_seen)} ships.")
                        return

                    # Wait up to 5 minutes for the next message. If nothing
                    # arrives, reconnect in case the connection died quietly.
                    raw = await asyncio.wait_for(websocket.recv(), timeout=300)
                    message = json.loads(raw)

                    if "error" in message:
                        raise SystemExit(f"aisstream returned an error: {message['error']}")

                    kind, row = parse_message(message)
                    if kind == "position":
                        if should_save_position(row["mmsi"], time.time()):
                            save(kind, row)
                            positions_saved += 1
                            ships_seen.add(row["mmsi"])
                    elif kind == "static":
                        save(kind, row)

                    if time.time() - last_status > 300:
                        print(f"  ...{positions_saved} positions saved, "
                              f"{len(ships_seen)} ships seen so far")
                        last_status = time.time()

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            # Internet dropped, server restarted, 5 minutes of silence...
            # Wait a bit and try again, waiting longer each time.
            log_event(f"disconnected ({type(error).__name__}: {error})")
            await asyncio.sleep(wait_seconds + random.uniform(0, 3))
            wait_seconds = min(wait_seconds * 2, 300)


def main():
    parser = argparse.ArgumentParser(description="Collect live AIS data from aisstream.io")
    parser.add_argument("--minutes", type=float, default=None,
                        help="stop after this many minutes (default: run until Ctrl+C)")
    args = parser.parse_args()

    os.makedirs(RAW_FOLDER, exist_ok=True)
    api_key = get_api_key()

    print(f"Listening for ships between latitude {config.LAT_MIN} and {config.LAT_MAX}, "
          f"longitude {config.LON_MIN} and {config.LON_MAX}")
    print("Press Ctrl+C to stop.\n")
    try:
        asyncio.run(collect(api_key, args.minutes))
    except KeyboardInterrupt:
        log_event("stopped by user")
    finally:
        close_files()


if __name__ == "__main__":
    main()
