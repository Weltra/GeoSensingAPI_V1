#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
武汉市卫星观测相交分析 - 精简版
"""

import json
import sys
import os

# 添加路径
sys.path.append('satelliteTool')

from satelliteTool.get_observation_lace import get_observation_lace
from GeoPandasTool.intersects import intersects


def main():
    # 加载TLE数据
    with open('satelliteTool/tle_data.json', 'r') as f:
        tle_data = json.load(f)

    # 加载武汉市边界
    try:
        with open('data/Wuhan.geojson', 'r') as f:
            wuhan_boundary = json.load(f)
    except:
        # 简化边界
        wuhan_boundary = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[114.0, 30.0], [114.8, 30.0], [114.8, 30.8], [114.0, 30.8], [114.0, 30.0]]]
                }
            }]
        }

    # 获取卫星覆盖轨迹
    coverage = get_observation_lace(
        tle_dict=tle_data,
        start_time_str="2025-08-01 00:00:00.000",
        end_time_str="2025-08-01 23:59:59.000",
        fov=10.0,
        interval_seconds=600
    )

    # 按卫星分组
    satellite_footprints = {}
    for feature in coverage['features']:
        sat_name = feature['properties']['satellite']
        if sat_name not in satellite_footprints:
            satellite_footprints[sat_name] = []
        satellite_footprints[sat_name].append(feature)

    # 分析相交情况
    results = []
    for sat_name, footprints in satellite_footprints.items():
        # 合并足迹
        combined = {
            "type": "FeatureCollection",
            "features": footprints
        }

        # 判断相交
        footprint_str = json.dumps(combined)
        wuhan_str = json.dumps(wuhan_boundary)
        intersect_results = intersects(footprint_str, wuhan_str)
        has_intersect = any(intersect_results)

        results.append((sat_name, has_intersect))
        print(f"{sat_name}: {'相交' if has_intersect else '不相交'}")

    # 统计结果
    intersecting = [sat for sat, intersect in results if intersect]
    print(f"\n相交卫星数量: {len(intersecting)}/{len(results)}")


if __name__ == "__main__":
    main()
