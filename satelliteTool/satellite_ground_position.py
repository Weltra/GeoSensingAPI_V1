from skyfield.api import load, EarthSatellite, utc
from datetime import datetime
import numpy as np
from shapely.geometry import Polygon, mapping
import json


def satellite_ground_position(tle_data, timestamp_str, fov=45):
    # 解析 TLE 数据
    lines = tle_data.strip().split("\n")
    if len(lines) < 3:
        return "Invalid TLE data"

    satellite = EarthSatellite(lines[1], lines[2], lines[0], load.timescale())
    ts = load.timescale()

    # 解析时间戳，并转换为 UTC
    observation_time = ts.utc(datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=utc))

    # 获取卫星子点位置
    geocentric = satellite.at(observation_time)
    subpoint = geocentric.subpoint()

    lat = subpoint.latitude.degrees
    lon = subpoint.longitude.degrees

    # 计算视场角覆盖的区域（近似计算）
    d_lat = fov / 2 / 111  # 1° ≈ 111 km
    d_lon = fov / 2 / (111 * np.cos(np.radians(lat)))  # 根据纬度调整经度跨度

    # 生成卫星观测区域的四边形
    polygon = Polygon([
        ((lon - d_lon + 180) % 360 - 180, lat - d_lat),  # 左下角
        ((lon + d_lon + 180) % 360 - 180, lat - d_lat),  # 右下角
        ((lon + d_lon + 180) % 360 - 180, lat + d_lat),  # 右上角
        ((lon - d_lon + 180) % 360 - 180, lat + d_lat)  # 左上角
    ])

    # 生成 Overpass API 兼容的 GeoJSON 数据
    overpass_api_result = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": mapping(polygon), "properties": {}}
        ]
    }

    return json.dumps(overpass_api_result, indent=2)


if __name__ == "__main__":
    # 示例用法
    tle_data = """
    ISS (ZARYA)
    1 25544U 98067A   24065.53334491  .00016717  00000+0  30284-3 0  9993
    2 25544  51.6412  41.1547 0003617 280.9252  79.1211 15.50344612453610
    """
    timestamp_str = "2025-03-04 12:00:00.000"  # 示例时间戳
    ground_coverage = satellite_ground_position(tle_data, timestamp_str)
    print(ground_coverage)