
import json
import numpy as np
from datetime import datetime, timedelta
from skyfield.api import load, EarthSatellite
from skyfield.timelib import utc
from shapely.geometry import Polygon, mapping
import os
import sys

# 添加项目根目录到Python路径以导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import save_geojson_file

def get_satellite_footprint(tle_dict, start_time_str, end_time_str, fov):
    """
    计算多个卫星的足迹并保存到全局文件夹
    
    Args:
        tle_dict: 卫星TLE数据字典，键为卫星名，值为TLE数据
        start_time_str: 开始时间字符串
        end_time_str: 结束时间字符串
        fov: 视场角度
    
    Returns:
        字典，键为卫星名，值为保存的文件路径
    """
    result_paths = {}
    
    for satellite_name, tle_data in tle_dict.items():
        try:
            # 计算单个卫星的足迹
            footprint_data = compute_footprint(tle_data, start_time_str, end_time_str, fov)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"satellite_footprint_{satellite_name}_{timestamp}.geojson"
            
            # 保存到全局文件夹
            file_path = save_geojson_file(filename, footprint_data)
            result_paths[satellite_name] = file_path
            
        except Exception as e:
            print(f"处理卫星 {satellite_name} 时出错: {str(e)}")
            result_paths[satellite_name] = None
    
    return result_paths

def compute_footprint(tle_data, start_time_str, end_time_str, fov):
    """
    计算单个卫星的足迹
    
    Args:
        tle_data: TLE数据字符串
        start_time_str: 开始时间字符串
        end_time_str: 结束时间字符串
        fov: 视场角度
    
    Returns:
        GeoJSON格式的足迹数据
    """
    lines = tle_data.strip().split("\n")
    if len(lines) < 3:
        raise ValueError("Invalid TLE data")

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


