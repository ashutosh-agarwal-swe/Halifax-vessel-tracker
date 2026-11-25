"""
All the settings for the project live in this one file.

If you want to study a different area or make a detector stricter,
change the number here instead of hunting through the code.
"""

# ---------------------------------------------------------------
# 1. Study area (a rectangle around Halifax harbour and its approaches)
# ---------------------------------------------------------------
AREA_NAME = "Halifax harbour and approaches"

LAT_MIN = 44.2
LAT_MAX = 44.9
LON_MIN = -64.2
LON_MAX = -63.1

# ---------------------------------------------------------------
# 2. Ports and anchorages
# ---------------------------------------------------------------
# Ships stop, drift and sit next to each other in ports all the time,
# so the loitering and rendezvous detectors ignore anything inside
# these circles.
#
# Format: (name, latitude, longitude, radius in km)
#
# NOTE: these positions are approximate. After the first run, open
# outputs/map.html, look at where slow ships really bunch up, and
# adjust the circles (or add new ones for anchorages).
PORTS = [
    ("Halifax harbour and Bedford Basin", 44.64, -63.56, 9.0),
    ("Chebucto Head anchorage", 44.51, -63.52, 4.0),
]

# ---------------------------------------------------------------
# 3. Cleaning
# ---------------------------------------------------------------
# Keep at most one position per ship per this many seconds.
DOWNSAMPLE_SECONDS = 60

# No ship here does 50 knots, so a position that needs more than
# this speed to reach is treated as a GPS glitch and removed.
MAX_SPEED_KNOTS = 50

# ---------------------------------------------------------------
# 4. Coverage (where can the receivers actually hear ships?)
# ---------------------------------------------------------------
# The area is cut into square cells this many degrees wide.
# 0.05 degrees is about 5.5 km north-south and about 4 km east-west.
GRID_SIZE_DEG = 0.05

# If a ship is not heard for this many minutes after being in a cell,
# that visit counts as "went silent".
SILENCE_MINUTES = 10

# A cell is only trusted if enough ships have passed through it...
COVERAGE_MIN_VISITS = 20
# ...and only a small share of those visits ended in silence.
COVERAGE_MAX_SILENCE_RATE = 0.10

# The data feed itself can go down (laptop asleep, wifi drops).
# Time is cut into bins of this many minutes. A bin with zero messages
# from ANY ship means the feed was probably down.
FEED_BIN_MINUTES = 10

# ---------------------------------------------------------------
# 5. Gap detector ("going dark")
# ---------------------------------------------------------------
GAP_MIN_MINUTES = 60          # shortest silence worth looking at
GAP_MIN_SPEED_BEFORE = 1.0    # knots - the ship must have been moving
EDGE_MARGIN_KM = 5.0          # ignore gaps that start this close to the edge of the study area
GAP_MIN_FEED_ALIVE = 0.90     # share of the gap during which the feed was working
GAP_FIRST_CHECK_MINUTES = 60  # the feed check is also applied to just this much of the gap's start
GAP_MIN_PATH_COVERED = 0.80   # share of the straight line start->end that is well covered

# ---------------------------------------------------------------
# 6. Loitering detector
# ---------------------------------------------------------------
# A ship drifting with the tide and wind, or nudging around its anchor,
# can still show 1-2 knots. That is why this is not set lower.
LOITER_MAX_SPEED = 2.0        # knots
LOITER_MIN_HOURS = 2.0
LOITER_MAX_PING_GAP_MIN = 15  # a longer silence ends the loitering run

# ---------------------------------------------------------------
# 7. Rendezvous detector (two ships meeting at sea)
# ---------------------------------------------------------------
RDV_BUCKET_MINUTES = 5        # positions are compared in 5 minute steps
RDV_MAX_DISTANCE_KM = 0.5
RDV_MAX_SPEED = 3.0           # knots - both ships must be slow
RDV_MIN_MINUTES = 30

# ---------------------------------------------------------------
# 8. Ship types that loiter or meet other ships as part of their job
# ---------------------------------------------------------------
# These are standard AIS ship type codes. Ships with these codes are
# still reported, but marked "likely_routine" and sorted to the bottom.
ROUTINE_TYPES = {
    30: "fishing",
    31: "towing",
    32: "towing (large)",
    33: "dredging",
    34: "diving operations",
    50: "pilot vessel",
    51: "search and rescue",
    52: "tug",
    53: "port tender",
    55: "law enforcement",
}
# Passenger ships (60-69) include the Halifax - Dartmouth ferries.
for code in range(60, 70):
    ROUTINE_TYPES[code] = "passenger / ferry"

# ---------------------------------------------------------------
# 9. Ship types that are left out completely
# ---------------------------------------------------------------
# Warships often switch AIS off on purpose, which is normal for them,
# so a gap from a navy ship is not a finding. Publishing a list of
# when navy ships went silent is also not something I want this
# project to do. They are removed during cleaning.
EXCLUDED_TYPES = {
    35: "military",
}


# ---------------------------------------------------------------
# 10. A made-up area used only for the fake sample data and the tests
# ---------------------------------------------------------------
# The fake data and the tests use their own area and their own port,
# so changing the real study area above never breaks them.
def use_sample_area():
    global AREA_NAME, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, PORTS
    AREA_NAME = "a made-up sample area"
    LAT_MIN = 44.2
    LAT_MAX = 44.8
    LON_MIN = -63.9
    LON_MAX = -63.1
    PORTS = [("Sample harbour", 44.64, -63.57, 9.0)]
