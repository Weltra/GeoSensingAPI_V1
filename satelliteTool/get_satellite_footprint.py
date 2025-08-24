
import json
import numpy as np
from datetime import datetime, timedelta
from skyfield.api import load, EarthSatellite
from skyfield.timelib import utc
from shapely.geometry import Polygon, mapping

def get_satellite_footprint(*args, multiInvocation: bool = False, times: int = 1):
    if multiInvocation:
        if len(args) < times * 4:
            return "Invalid number of arguments for multiInvocation"

        results = []
        for i in range(times):
            tle_data, start_time_str, end_time_str, fov = args[i * 4:i * 4 + 4]
            results.append(compute_footprint(tle_data, start_time_str, end_time_str, fov))
        return json.dumps(results, indent=2)
    else:
        if len(args) < 4:
            return "Invalid number of arguments for single invocation"

        tle_data, start_time_str, end_time_str, fov = args[:4]
        return json.dumps(compute_footprint(tle_data, start_time_str, end_time_str, fov), indent=2)

def compute_footprint(tle_data, start_time_str, end_time_str, fov):
    lines = tle_data.strip().split("\n")
    if len(lines) < 3:
        return "Invalid TLE data"

    satellite = EarthSatellite(lines[1], lines[2], lines[0], load.timescale())
    ts = load.timescale()

    start_time = ts.utc(datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=utc))
    end_time = ts.utc(datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=utc))
    step = 60  # Step in seconds
    times = []
    t = start_time
    while t.tt <= end_time.tt:
        times.append(t)
        t = ts.utc(t.utc_datetime() + timedelta(seconds=step))

    latitudes, longitudes = [], []
    for t in times:
        geocentric = satellite.at(t)
        subpoint = geocentric.subpoint()
        latitudes.append(subpoint.latitude.degrees)
        longitudes.append(subpoint.longitude.degrees)

    footprint_polygons = []
    for lat, lon in zip(latitudes, longitudes):
        d_lat = fov / 2 / 111  # Approximate latitude shift (1° ≈ 111 km)
        d_lon = fov / 2 / (111 * np.cos(np.radians(lat)))  # Approximate longitude shift

        polygon = Polygon([
            ((lon - d_lon + 180) % 360 - 180, lat - d_lat),  # Handle -180 to 180 wrap
            ((lon + d_lon + 180) % 360 - 180, lat - d_lat),
            ((lon + d_lon + 180) % 360 - 180, lat + d_lat),
            ((lon - d_lon + 180) % 360 - 180, lat + d_lat)
        ])
        footprint_polygons.append(polygon)

    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": mapping(poly), "properties": {}} for poly in footprint_polygons
        ]
    }


