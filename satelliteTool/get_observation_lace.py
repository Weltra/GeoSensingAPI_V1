# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: get_observation_lace
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-09-14
"""

import os
import json
import geojson
from skyfield.api import Loader, EarthSatellite, utc
from shapely.geometry import mapping, Polygon
from datetime import datetime, timedelta
import sys
import numpy as np
import math

try:
    from pyproj import Geod
except ImportError:
    print("错误: 本脚本需要 pyproj 库。请运行: pip install pyproj")
    sys.exit(1)

# 确保项目根目录在路径中，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_geojson_path


def parse_flexible_datetime(time_str: str) -> datetime:
    """
    【新增】解析多种常见的ISO类时间字符串，使其具有时区信息。
    如果缺少时区，则默认为UTC。
    """
    original_str = time_str
    
    # 预处理：将'Z'替换为strptime可以理解的UTC偏移量
    if time_str.endswith('Z'):
        time_str = time_str[:-1] + '+0000'

    # 需要尝试的格式列表，从最具体到最通用
    # 包含带'T'或空格，带或不带微秒，带或不带时区
    formats_to_try = [
        '%Y-%m-%dT%H:%M:%S.%f%z',  # 带 T, 微秒, 时区
        '%Y-%m-%dT%H:%M:%S%z',     # 带 T, 无微秒, 时区
        '%Y-%m-%d %H:%M:%S.%f%z',  # 带空格, 微秒, 时区
        '%Y-%m-%d %H:%M:%S%z',     # 带空格, 无微秒, 时区
        '%Y-%m-%dT%H:%M:%S.%f',  # 带 T, 微秒, 无时区
        '%Y-%m-%dT%H:%M:%S',     # 带 T, 无微秒, 无时区
        '%Y-%m-%d %H:%M:%S.%f',  # 带空格, 微秒, 无时区
        '%Y-%m-%d %H:%M:%S',     # 带空格, 无微秒, 无时区
    ]

    for fmt in formats_to_try:
        try:
            dt_obj = datetime.strptime(time_str, fmt)
            # 如果解析成功但没有时区，则假定为UTC
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=utc)
            return dt_obj
        except ValueError:
            continue
            
    # 如果所有格式都失败了
    raise ValueError(f"无法解析提供的时间字符串: '{original_str}'")


def get_observation_lace(tle_dict: dict, start_time_str: str, end_time_str: str,
                         target_geojson_path: str, fov: float = 10.0,
                         interval_seconds: int = 600) -> dict:
    """
    计算多个卫星在指定时间段内的地面覆盖轨迹，并将每个卫星的结果保存到单独的GeoJSON文件中。
    """
    load = Loader('~/skyfield-data', verbose=False)
    ts = load.timescale()

    satellite_paths = {}

    for name, tle_lines_str in tle_dict.items():
        print(f"---> 正在处理卫星: {name}")
        features_for_satellite = []
        output_path = None

        try:
            try:
                tle_line1, tle_line2 = tle_lines_str.strip().split('\n')
            except ValueError:
                raise ValueError("TLE 格式无效，必须是包含换行符的两行字符串。")

            satellite = EarthSatellite(tle_line1, tle_line2, name, ts)
            
            # 【核心修正】使用更灵活的时间解析函数
            start_datetime = parse_flexible_datetime(start_time_str)
            end_datetime = parse_flexible_datetime(end_time_str)

            time_steps = []
            current_datetime = start_datetime
            while current_datetime <= end_datetime:
                t = ts.from_datetime(current_datetime)
                time_steps.append(t)
                current_datetime += timedelta(seconds=interval_seconds)

            for i, t in enumerate(time_steps):
                geocentric = satellite.at(t)
                subpoint = geocentric.subpoint()

                lat = subpoint.latitude.degrees
                lon = subpoint.longitude.degrees
                altitude_km = subpoint.elevation.km

                if math.isnan(lat) or math.isnan(lon) or math.isnan(altitude_km):
                    print(f"⚠️ 警告: 在时间 {t.utc_iso()} 无法计算卫星 '{name}' 的有效位置，跳过此时间步。")
                    continue

                coverage_radius_meters = altitude_km * 1000 * math.tan(math.radians(fov / 2.0))
                if coverage_radius_meters <= 0:
                    continue

                coverage_polygon = create_accurate_circular_polygon(lon, lat, coverage_radius_meters)

                feature = geojson.Feature(
                    geometry=coverage_polygon,
                    properties={
                        "satellite": name,
                        "timestamp": t.utc_iso(),
                        "latitude": lat,
                        "longitude": lon,
                        "altitude_km": altitude_km,
                        "fov_deg": fov,
                        "step": i
                    }
                )
                features_for_satellite.append(feature)

            if features_for_satellite:
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-')).rstrip().replace(' ', '_')
                file_name = f"{safe_name}_observation_trace.geojson"
                output_path = get_geojson_path(file_name)
                feature_collection = geojson.FeatureCollection(features_for_satellite)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(feature_collection, f, ensure_ascii=False, indent=2)
                satellite_paths[name] = output_path
                print(f"✅ 卫星 {name} 观测轨迹已保存到: {output_path}")
            else:
                print(f"⚠️ 卫星 {name} 没有生成有效的观测轨迹")

        except Exception as e:
            print(f"❌ 处理卫星 {name} 时出错: {e}")
            satellite_paths[name] = None

    return satellite_paths


def create_accurate_circular_polygon(center_lon: float, center_lat: float, radius_meters: float,
                                     num_points: int = 64) -> dict:
    """
    使用 geod.fwd 和 numpy.linspace 来精确、稳定地创建圆形多边形。
    """
    geod = Geod(ellps='WGS84')
    azimuths = np.linspace(0, 360, num_points)
    num_points = len(azimuths)
    lons, lats, _ = geod.fwd(
        lons=np.full(num_points, center_lon),
        lats=np.full(num_points, center_lat),
        az=azimuths,
        dist=np.full(num_points, radius_meters)
    )
    polygon = Polygon(zip(lons, lats))
    return mapping(polygon)


if __name__ == "__main__":
    test_tle = {
       "Worldview 3": "1 40115U 14045A   25253.16825499  .00000154  00000+0  31345-4 0  9993\n2 40115  97.9723 349.5222 0010431  83.2118 276.9142 14.71268688582685"
    }
    result = get_observation_lace(
        tle_dict=test_tle,
        # 测试之前导致问题的格式
        start_time_str="2025-08-1 07:00:00",
        end_time_str="2025-08-1 08:30:00",
        target_geojson_path="test.geojson"
    )
    print(f"\n最终结果: {result}")
