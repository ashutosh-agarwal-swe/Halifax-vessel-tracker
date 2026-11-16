"""
Step 6: draw the results.

Makes three files in the output folder:
  - map.png            a picture of the area with the flagged events
  - coverage_map.png   which grid cells are well covered
  - map.html           an interactive map (needs the folium library)

Each kind of event has its own colour AND its own marker shape, so the
map still works for colour-blind readers and in black and white.
"""

import html
import os

import matplotlib
matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.pyplot as plt
import numpy as np

import config

# Colours (checked for colour-blind safety)
COLOR_GAP = "#2a78d6"         # blue
COLOR_LOITER = "#eb6834"      # orange
COLOR_RENDEZVOUS = "#1baf7a"  # green
COLOR_TRACKS = "#898781"      # grey
COLOR_PORT = "#52514e"        # dark grey
COLOR_GRID = "#e1e0d9"
COLOR_TEXT = "#0b0b0b"
COLOR_BACKGROUND = "#fcfcfb"

MAX_TRACK_POINTS = 60000      # more than this just makes the picture slow


def _esc(value):
    """Escape a data value for use inside folium popup HTML."""
    return html.escape(str(value))


def setup_axes(ax, title):
    """Shared look for both pictures."""
    ax.set_facecolor(COLOR_BACKGROUND)
    ax.set_xlim(config.LON_MIN, config.LON_MAX)
    ax.set_ylim(config.LAT_MIN, config.LAT_MAX)
    # Without this the map looks stretched, because a degree of
    # longitude is shorter than a degree of latitude this far north.
    middle_lat = (config.LAT_MIN + config.LAT_MAX) / 2
    ax.set_aspect(1 / np.cos(np.radians(middle_lat)))
    ax.grid(color=COLOR_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_xlabel("Longitude", color=COLOR_TEXT)
    ax.set_ylabel("Latitude", color=COLOR_TEXT)
    ax.set_title(title, color=COLOR_TEXT, loc="left", fontsize=13)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)


def draw_ports(ax):
    for name, lat, lon, radius_km in config.PORTS:
        # Turn the radius from km into degrees to draw the circle.
        angles = np.linspace(0, 2 * np.pi, 100)
        circle_lat = lat + (radius_km / 111.0) * np.sin(angles)
        circle_lon = lon + (radius_km / (111.0 * np.cos(np.radians(lat)))) * np.cos(angles)
        ax.plot(circle_lon, circle_lat, color=COLOR_PORT, linewidth=1, linestyle="--")
        ax.annotate(name, (lon, lat), fontsize=7, color=COLOR_PORT, ha="center")


def make_static_map(df, gaps, loitering, rendezvous, output_folder, note=""):
    fig, ax = plt.subplots(figsize=(11, 8))
    fig.patch.set_facecolor(COLOR_BACKGROUND)
    setup_axes(ax, "Flagged vessel behaviour in " + config.AREA_NAME + note)

    # All ship positions as faint grey dots, so the shipping lanes show.
    tracks = df
    if len(tracks) > MAX_TRACK_POINTS:
        tracks = tracks.sample(MAX_TRACK_POINTS, random_state=1)
    ax.scatter(tracks["lon"], tracks["lat"], s=1, color=COLOR_TRACKS,
               alpha=0.25, linewidths=0, label="All ship positions")

    draw_ports(ax)

    # Gaps: a line from where the ship vanished to where it came back.
    flagged = gaps[gaps["flagged"]] if len(gaps) > 0 else gaps
    first = True
    for row in flagged.itertuples():
        ax.plot([row.start_lon, row.end_lon], [row.start_lat, row.end_lat],
                color=COLOR_GAP, linewidth=2, marker="o", markersize=6,
                label="Transmission gap (start to end)" if first else None)
        first = False

    if len(loitering) > 0:
        ax.scatter(loitering["lon"], loitering["lat"], s=70, marker="s",
                   color=COLOR_LOITER, edgecolors=COLOR_BACKGROUND, linewidths=1.5,
                   label="Loitering", zorder=3)

    if len(rendezvous) > 0:
        ax.scatter(rendezvous["lon"], rendezvous["lat"], s=110, marker="^",
                   color=COLOR_RENDEZVOUS, edgecolors=COLOR_BACKGROUND, linewidths=1.5,
                   label="Rendezvous", zorder=4)

    ax.legend(loc="upper left", frameon=True, facecolor=COLOR_BACKGROUND,
              edgecolor=COLOR_GRID, fontsize=9)

    path = os.path.join(output_folder, "map.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {path}")


def make_coverage_map(cells, output_folder, note=""):
    fig, ax = plt.subplots(figsize=(11, 8))
    fig.patch.set_facecolor(COLOR_BACKGROUND)
    setup_axes(ax, "Where ships can be heard reliably" + note)

    good = cells[cells["well_covered"]]
    poor = cells[~cells["well_covered"]]

    # Filled squares = well covered, crosses = not trusted.
    ax.scatter(good["lon"], good["lat"], s=45, marker="s", color=COLOR_GAP,
               linewidths=0, label="Well covered cell")
    ax.scatter(poor["lon"], poor["lat"], s=30, marker="x", color=COLOR_LOITER,
               linewidths=1.2, label="Too few ships or too many silences")
    draw_ports(ax)

    ax.legend(loc="upper left", frameon=True, facecolor=COLOR_BACKGROUND,
              edgecolor=COLOR_GRID, fontsize=9)

    path = os.path.join(output_folder, "coverage_map.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {path}")


def make_interactive_map(df, gaps, loitering, rendezvous, output_folder):
    """Interactive map you can zoom and click. Skipped if folium is missing."""
    try:
        import folium
    except ImportError:
        print("folium is not installed, skipping map.html "
              "(run: pip install folium)")
        return

    centre = [(config.LAT_MIN + config.LAT_MAX) / 2, (config.LON_MIN + config.LON_MAX) / 2]
    fmap = folium.Map(location=centre, zoom_start=9, tiles="CartoDB positron")

    # --- ship positions ----------------------------------------------
    tracks_layer = folium.FeatureGroup(name="All ship positions")
    tracks = df
    if len(tracks) > 5000:
        tracks = tracks.sample(5000, random_state=1)
    for row in tracks.itertuples():
        folium.CircleMarker(
            location=[row.lat, row.lon], radius=1, color=COLOR_TRACKS,
            weight=0, fill=True, fill_opacity=0.4,
        ).add_to(tracks_layer)
    tracks_layer.add_to(fmap)

    # --- port circles ------------------------------------------------
    ports_layer = folium.FeatureGroup(name="Port circles")
    for name, lat, lon, radius_km in config.PORTS:
        folium.Circle(
            location=[lat, lon], radius=radius_km * 1000, color=COLOR_PORT,
            weight=1, dash_array="6", fill=False, tooltip=name,
        ).add_to(ports_layer)
    ports_layer.add_to(fmap)

    # --- gaps --------------------------------------------------------
    gaps_layer = folium.FeatureGroup(name="Transmission gaps")
    flagged = gaps[gaps["flagged"]] if len(gaps) > 0 else gaps
    for row in flagged.itertuples():
        text = (f"GAP: {_esc(row.vessel_name)} (MMSI {_esc(row.mmsi)})<br>"
                f"{_esc(row.gap_start)} to {_esc(row.gap_end)}<br>"
                f"{row.gap_hours:.1f} hours, {row.distance_km:.0f} km apart")
        folium.PolyLine(
            locations=[[row.start_lat, row.start_lon], [row.end_lat, row.end_lon]],
            color=COLOR_GAP, weight=3, popup=text,
        ).add_to(gaps_layer)
        folium.CircleMarker(
            location=[row.start_lat, row.start_lon], radius=6, color=COLOR_GAP,
            fill=True, fill_opacity=1, popup=text, tooltip="Gap start",
        ).add_to(gaps_layer)
    gaps_layer.add_to(fmap)

    # --- loitering ---------------------------------------------------
    loiter_layer = folium.FeatureGroup(name="Loitering")
    for row in loitering.itertuples():
        text = (f"LOITERING: {_esc(row.vessel_name)} (MMSI {_esc(row.mmsi)})<br>"
                f"{_esc(row.start)} to {_esc(row.end)}<br>"
                f"{row.duration_hours:.1f} hours<br>"
                f"Routine type: {_esc(row.routine_type or 'no')}")
        folium.RegularPolygonMarker(
            location=[row.lat, row.lon], number_of_sides=4, radius=8,
            color=COLOR_LOITER, fill=True, fill_color=COLOR_LOITER,
            fill_opacity=0.9, popup=text, tooltip="Loitering",
        ).add_to(loiter_layer)
    loiter_layer.add_to(fmap)

    # --- rendezvous --------------------------------------------------
    rdv_layer = folium.FeatureGroup(name="Rendezvous")
    for row in rendezvous.itertuples():
        text = (f"RENDEZVOUS: {_esc(row.name_a)} and {_esc(row.name_b)}<br>"
                f"MMSI {_esc(row.mmsi_a)} and {_esc(row.mmsi_b)}<br>"
                f"{_esc(row.start)} to {_esc(row.end)}<br>"
                f"{row.duration_minutes:.0f} minutes, closest {row.closest_km * 1000:.0f} m<br>"
                f"Routine type: {_esc(row.routine_type or 'no')}")
        folium.RegularPolygonMarker(
            location=[row.lat, row.lon], number_of_sides=3, radius=9,
            color=COLOR_RENDEZVOUS, fill=True, fill_color=COLOR_RENDEZVOUS,
            fill_opacity=0.9, popup=text, tooltip="Rendezvous",
        ).add_to(rdv_layer)
    rdv_layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    path = os.path.join(output_folder, "map.html")
    fmap.save(path)
    print(f"Saved {path}")


def run(df, cells, gaps, loitering, rendezvous, output_folder, is_sample=False):
    os.makedirs(output_folder, exist_ok=True)
    print()
    # Make sure a picture of fake data can never be mistaken for a result.
    note = "  (FAKE SAMPLE DATA)" if is_sample else ""
    make_static_map(df, gaps, loitering, rendezvous, output_folder, note)
    make_coverage_map(cells, output_folder, note)
    make_interactive_map(df, gaps, loitering, rendezvous, output_folder)
