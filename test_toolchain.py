#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具链API测试脚本
测试前四个API的可用性，复现 wuhan_satellite_uav_coverage_planner.py 的结果
"""

import requests
import json
import os
import time
from typing import Dict, Any

# API服务器配置
from shapely.geometry import mapping

BASE_URL = "http://localhost:8000"  # 根据实际情况修改

class ToolchainAPITester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        
    def test_api(self, endpoint: str, data: Dict[str, Any], description: str) -> Dict[str, Any]:
        """测试单个API端点"""
        print(f"\n{'='*60}")
        print(f"测试: {description}")
        print(f"端点: {endpoint}")
        print(f"{'='*60}")
        
        try:
            response = self.session.post(f"{self.base_url}{endpoint}", json=data)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 成功: {result.get('message', 'API调用成功')}")
                return result
            else:
                print(f"❌ 失败: HTTP {response.status_code}")
                print(f"错误信息: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络错误: {e}")
            return None
        except Exception as e:
            print(f"❌ 其他错误: {e}")
            return None

def main():
    """主测试函数"""
    print("工具链API测试脚本")
    print("=" * 60)
    print("此脚本将测试前四个API，复现 wuhan_satellite_uav_coverage_planner.py 的结果")
    
    tester = ToolchainAPITester()
    
    # 测试参数（与 wuhan_satellite_uav_coverage_planner.py 保持一致）
    satellite_db_path = "D:\\GeoSensingAPI\\data\\satellite_data.db"
    wuhan_geojson_path = "D:\\GeoSensingAPI\\data\\Wuhan.geojson"
    uav_db_path = "data/UAV_data.db"
    stations_db_path = "data/Stations_data.db"
    
    # 输出目录
    base_output_dir = "api_test_results"
    overlap_output_dir = os.path.join(base_output_dir, "B_observation_overlaps")
    final_plan_output_dir = os.path.join(base_output_dir, "C_final_plan")
    uav_output_dir = os.path.join(base_output_dir, "uav_completion")
    
    # 创建输出目录
    os.makedirs(overlap_output_dir, exist_ok=True)
    os.makedirs(final_plan_output_dir, exist_ok=True)
    os.makedirs(uav_output_dir, exist_ok=True)
    
    # 步骤1: 获取卫星TLE数据
    print(f"\n{'='*20} 步骤1: 获取卫星TLE数据 {'='*20}")
    tle_request = {
        "satellite_db_path": satellite_db_path,
        "mission_theme": "Land cover",
        "sensor_type": "Optical Sensor"
    }
    
    tle_result = tester.test_api(
        "/get_satellite_tle",
        tle_request,
        "获取卫星TLE数据"
    )
    
    if not tle_result or not tle_result.get('success'):
        print("❌ 获取TLE数据失败，测试终止")
        return
    
    tle_data = tle_result['data']
    print(f"✅ 成功获取 {len(tle_data)} 颗卫星的TLE数据")
    
    # 步骤2: 计算卫星观测重叠率
    print(f"\n{'='*20} 步骤2: 计算卫星观测重叠率 {'='*20}")
    overlap_request = {
        "tle_dict": tle_data,
        "start_time_str": "2025-08-01 00:00:00.000",
        "end_time_str": "2025-08-01 23:59:59.000",
        "target_geojson_path": wuhan_geojson_path,
        "fov": 10.0,
        "interval_seconds": 600,
        "output_dir": overlap_output_dir
    }
    
    overlap_result = tester.test_api(
        "/get_observation_overlap",
        overlap_request,
        "计算卫星观测重叠率"
    )
    
    if not overlap_result or not overlap_result.get('success'):
        print("❌ 计算观测重叠率失败，测试终止")
        return
    
    coverage_results = overlap_result['coverage_results']
    print("✅ 成功计算卫星观测重叠率")
    
    # 步骤3: 规划卫星方案
    print(f"\n{'='*20} 步骤3: 规划卫星方案 {'='*20}")
    planning_request = {
        "coverage_results": coverage_results,
        "target_geojson_path": wuhan_geojson_path,
        "target_coverage": 0.99,
        "output_dir": final_plan_output_dir
    }
    
    planning_result = tester.test_api(
        "/plan_satellite_combination",
        planning_request,
        "规划卫星方案"
    )
    
    print("✅ 成功规划卫星方案")
    
    # 分析卫星规划结果
    report = planning_result['report']
    final_plan = (report['optimal_plan'] or report['best_effort_plan'])
    
    if not final_plan:
        print("❌ 卫星规划失败或未找到任何相交卫星，无法进行无人机补全")
        return
    
    total_coverage = final_plan['coverage']
    is_optimal = planning_result['success']
    
    if is_optimal:
        print(f"卫星最优方案已找到，覆盖率: {total_coverage:.2%}")
    else:
        print(f"未找到满足目标的方案，采纳'尽力而为'的最佳方案，覆盖率: {total_coverage:.2%}")
    
    if total_coverage >= 0.99:
        print(f"✅ 卫星覆盖率已达到 {total_coverage:.2%}，无需无人机补全")
        print("测试完成！")
        return
    
    print(f"⚠️卫星覆盖率 {total_coverage:.2%} < 99%，开始计算无人机补全区域")
    
    # 计算未覆盖区域（使用difference API）
    print(f"\n{'='*20} 计算未覆盖区域 {'='*20}")
    intersection_file = planning_result['intersection_path']
    if not intersection_file or not os.path.exists(intersection_file):
        print(f"❌ 卫星规划的交集文件不存在，无法进行无人机补全")
        return
    
    # 创建差集输出目录
    difference_output_dir = os.path.join(base_output_dir, "intermediate_difference")
    
    # 步骤3.1: 使用difference API计算未覆盖区域
    difference_request = {
        "input_list": [
            {
                "source": wuhan_geojson_path,
                "clip": intersection_file
            }
        ],
        "output_directory": difference_output_dir
    }
    
    difference_result = tester.test_api(
        "/difference",
        difference_request,
        "计算目标区域与卫星覆盖区域的差集"
    )
    
    if not difference_result or "errors" in difference_result:
        print("❌ 计算差集失败")
        return
    
    # 获取差集结果文件路径
    difference_key = list(difference_result.keys())[0]  # 应该是类似 "Wuhan_difference_Wuhan_final_intersection" 的键
    uncovered_raw_path = difference_result[difference_key]
    
    # 检查差集是否为空
    try:
        with open(uncovered_raw_path, 'r', encoding='utf-8') as f:
            uncovered_data = json.load(f)
        
        if not uncovered_data.get('features'):
            print("✅ 计算后发现未覆盖区域为空，无需进行补全规划")
            print("🎉 测试完成！")
            return
    except Exception as e:
        print(f"❌ 读取差集结果时出错: {e}")
        return
    
    print(f"✅ 差集计算完成，结果保存到: {uncovered_raw_path}")
    
    # 步骤3.2: 使用过滤API过滤细小区域
    print(f"\n{'='*20} 过滤细小区域 {'='*20}")
    filtered_output_dir = os.path.join(difference_output_dir, "filtered")
    
    filter_request = {
        "input_files_dict": {
            "uncovered_area": uncovered_raw_path
        },
        "output_directory": filtered_output_dir,
        "min_area_threshold_m2": 500.0  # 过滤掉小于500平方米的区域
    }
    
    filter_result = tester.test_api(
        "/filter_sliver_polygons",
        filter_request,
        "过滤细小的未覆盖区域"
    )
    
    if not filter_result or not filter_result.get('success'):
        print("⚠️  过滤API失败，使用原始差集结果")
        temp_uncovered_path = uncovered_raw_path
    else:
        filtered_results = filter_result.get('cleaned_results', {})
        if 'uncovered_area' in filtered_results:
            temp_uncovered_path = filtered_results['uncovered_area']
            print(f"✅ 细小区域过滤完成，结果保存到: {temp_uncovered_path}")
        else:
            print("⚠️  过滤结果中未找到预期文件，使用原始差集结果")
            temp_uncovered_path = uncovered_raw_path
    
    # 检查过滤后的区域是否为空
    try:
        with open(temp_uncovered_path, 'r', encoding='utf-8') as f:
            filtered_data = json.load(f)
        
        if not filtered_data.get('features'):
            print("✅ 过滤后发现未覆盖区域为空，无需进行补全规划")
            print("🎉 测试完成！")
            return
    except Exception as e:
        print(f"❌ 读取过滤结果时出错: {e}")
        return
    
    # 步骤4: 无人机协同规划
    print(f"\n{'='*20} 步骤4: 无人机协同规划 {'='*20}")
    uav_request = {
        "geojson_path": temp_uncovered_path,
        "output_dir": uav_output_dir,
        "create_map": True,
        "verbose": True,
        "UAV_db_path": uav_db_path,
        "stations_db_path": stations_db_path
    }
    
    uav_result = tester.test_api(
        "/run_UAV_GS_planning",
        uav_request,
        "无人机协同规划"
    )
    
    if not uav_result or not uav_result.get('success'):
        print("❌ 无人机规划失败")
    else:
        print("✅ 无人机协同规划完成")
    
    # 测试总结
    print(f"\n{'='*60}")
    print("🎉 测试完成！")
    print(f"{'='*60}")
    print(f"测试结果保存在: {base_output_dir}")
    print(f"卫星规划结果: {final_plan_output_dir}")
    print(f"差集计算结果: {difference_output_dir}")
    print(f"无人机规划结果: {uav_output_dir}")
    
    # 显示最终覆盖率
    if uav_result and uav_result.get('success'):
        planning_mode = "空地协同" if (uav_result.get('results_data', {}).get('ground_station_contribution', {}).get('station_count', 0) > 0) else "纯无人机"
        print(f"规划模式: {planning_mode}")
        print(f"卫星覆盖率: {total_coverage:.2%}")
    else:
        print(f"规划模式: 仅卫星")
        print(f"卫星覆盖率: {total_coverage:.2%}")

if __name__ == "__main__":
    main()