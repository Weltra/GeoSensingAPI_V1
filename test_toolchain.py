#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具链API测试脚本
复现 wuhan_satellite_uav_coverage_planner.py 的结果。
此版本集成了细碎区域过滤功能到差集计算步骤中，并使用通用可视化API。
"""

import json
import os
from typing import Dict, Any

import requests

# API服务器配置
BASE_URL = "http://localhost:8000"  # 根据实际情况修改


class ToolchainAPITester:
	def __init__(self, base_url: str = BASE_URL):
		self.base_url = base_url
		self.session = requests.Session()

	def test_api(self, endpoint: str, data: Dict[str, Any], description: str) -> Dict[str, Any]:
		"""测试单个API端点"""
		print(f"\n{'=' * 60}")
		print(f"测试: {description}")
		print(f"端点: {endpoint}")
		print(f"{'=' * 60}")

		try:
			response = self.session.post(f"{self.base_url}{endpoint}", json=data)

			if response.status_code == 200:
				result = response.json()
				# 统一的成功消息处理
				msg = result.get('message', 'API调用成功') if isinstance(result, dict) else 'API调用成功'
				print(f"✅ 成功: {msg}")
				return result
			else:
				print(f"❌ 失败: HTTP {response.status_code}")
				print(f"错误信息: {response.text}")
				return {}

		except requests.exceptions.RequestException as e:
			print(f"❌ 网络错误: {e}")
			return {}
		except Exception as e:
			print(f"❌ 其他错误: {e}")
			return {}


def main():
	"""主测试函数"""
	print("工具链API测试脚本")
	print("=" * 60)
	print("此脚本将复现 wuhan_satellite_uav_coverage_planner.py 的结果")

	tester = ToolchainAPITester()

	# --- 参数和目录设置 ---
	satellite_db_path = "D:\\GeoSensingAPI\\data\\satellite_data.db"
	wuhan_geojson_path = "D:\\GeoSensingAPI\\data\\Wuhan.geojson"
	uav_db_path = "data/UAV_data.db"
	stations_db_path = "data/Stations_data.db"

	geojson_dir = "geojson"
	os.makedirs(geojson_dir, exist_ok=True)

	wuhan_geojson_target = os.path.join(geojson_dir, "Wuhan.geojson")
	if not os.path.exists(wuhan_geojson_target):
		import shutil
		shutil.copy2(wuhan_geojson_path, wuhan_geojson_target)
		print(f"✅ Wuhan.geojson已复制到geojson目录")

	base_output_dir = "api_test_results"
	uav_output_dir = os.path.join(base_output_dir, "uav_completion")
	os.makedirs(uav_output_dir, exist_ok=True)

	# --- 步骤1: 获取卫星TLE数据 ---
	print(f"\n{'=' * 20} 步骤1: 获取卫星TLE数据 {'=' * 20}")
	tle_request = {
		"satellite_db_path": satellite_db_path,
		"mission_theme": "Land cover",
		"sensor_type": "Optical Sensor"
	}
	tle_result = tester.test_api("/get_satellite_tle", tle_request, "获取卫星TLE数据")
	if not tle_result or not tle_result.get('success'):
		print("❌ 获取TLE数据失败，测试终止")
		return
	tle_data = tle_result['data']
	print(f"✅ 成功获取 {len(tle_data)} 颗卫星的TLE数据")

	# --- 步骤2: 计算卫星观测重叠率 ---
	print(f"\n{'=' * 20} 步骤2: 计算卫星观测重叠率 {'=' * 20}")
	# 注意：为了复现您提到的情况，我将时间调整为您项目常用的2025-08-01
	overlap_request = {
		"tle_dict": tle_data,
		"start_time_str": "2025-08-01 00:00:00.000",
		"end_time_str": "2025-08-01 23:59:59.000",
		"target_geojson_path": wuhan_geojson_target,
		"fov": 10.0,
		"interval_seconds": 600
	}
	overlap_result = tester.test_api("/get_observation_overlap", overlap_request, "计算卫星观测重叠率")
	if not overlap_result or not overlap_result.get('success'):
		print("❌ 计算观测重叠率失败，测试终止")
		return
	coverage_results = overlap_result['coverage_results']
	print("✅ 成功计算卫星观测重叠率")

	# --- 步骤3: 规划卫星方案 ---
	print(f"\n{'=' * 20} 步骤3: 规划卫星方案 {'=' * 20}")
	planning_request = {
		"coverage_results": coverage_results,
		"target_geojson_path": wuhan_geojson_target,
		"target_coverage": 0.95
	}
	planning_result = tester.test_api("/plan_satellite_combination", planning_request, "规划卫星方案")

	final_plan = {}  # 默认final_plan为空字典
	if not planning_result:
		print("❌ 规划卫星方案API调用失败")
	else:
		print("✅ 成功调用卫星方案规划API")
		# 尝试获取规划，不管success字段的值
		report = planning_result.get('report', {})
		final_plan = report.get('optimal_plan') or report.get('best_effort_plan') or {}

		# 如果report中没有找到规划，尝试直接从planning_result中获取
		if not final_plan:
			final_plan = planning_result.get('optimal_plan') or planning_result.get('best_effort_plan') or {}

		# 打印调试信息
		print(f"Debug: planning_result keys: {list(planning_result.keys()) if planning_result else 'None'}")
		if planning_result and 'report' in planning_result:
			print(f"Debug: report keys: {list(planning_result['report'].keys())}")
		print(f"Debug: final_plan keys: {list(final_plan.keys()) if final_plan else 'Empty'}")

	# 【关键修改】无论final_plan是否为空，都继续执行
	if not final_plan:
		print("⚠️ 警告: 未能找到满足要求的卫星规划方案 (可能无卫星覆盖或覆盖率过低)")

	# 初始化无人机和未覆盖区域相关的变量
	uav_result = {}
	uncovered_filtered_path = ""
	run_uav_planning = False
	total_coverage = final_plan.get('coverage', 0)  # 如果final_plan为空，覆盖率将是0

	if total_coverage >= 0.95:
		print(f"✅ 卫星覆盖率已达到 {total_coverage:.2%}，无需无人机补全")
	else:
		print(f"⚠️ 卫星覆盖率 {total_coverage:.2%} < 95%，检查是否需要无人机补全")

		# 仅当有卫星覆盖时，才计算未覆盖区域
		intersection_path = planning_result.get('intersection_path')
		if intersection_path and os.path.exists(intersection_path):
			print(f"\n{'=' * 20} 计算未覆盖区域 (集成过滤) {'=' * 20}")
			difference_request = {
				"geojson_names": "Wuhan",
				"clip_geojson_name": os.path.splitext(os.path.basename(intersection_path))[0]
			}
			difference_result = tester.test_api("/difference", difference_request, "计算差集并自动过滤细小区域")

			if difference_result:
				uncovered_filename = difference_result.get("Wuhan")
				if uncovered_filename and not uncovered_filename.startswith("Error:"):
					uncovered_filtered_path = os.path.join(geojson_dir, f"{uncovered_filename}.geojson")
					try:
						with open(uncovered_filtered_path, 'r', encoding='utf-8') as f:
							uncovered_data = json.load(f)
						if not uncovered_data.get('features'):
							print("✅ 计算后发现未覆盖区域为空 (已自动过滤)，无需进行补全规划")
						else:
							print(f"✅ 差集计算和过滤完成，结果保存到: {uncovered_filtered_path}")
							run_uav_planning = True
					except Exception as e:
						print(f"❌ 读取差集结果文件时出错: {e}")
				else:
					print(f"❌ 计算差集时发生内部错误: {uncovered_filename}")
		else:
			# 如果一开始就没有卫星覆盖，则整个目标区域都需要无人机规划
			print("ℹ️ 无有效卫星覆盖，整个目标区域将作为无人机规划范围")
			uncovered_filtered_path = wuhan_geojson_target
			run_uav_planning = True

	# --- 步骤4: 无人机协同规划 (仅当需要时运行) ---
	if run_uav_planning:
		print(f"\n{'=' * 20} 步骤4: 无人机协同规划 {'=' * 20}")
		uav_request = {
			"geojson_path": uncovered_filtered_path,
			"create_map": True,
			"verbose": True,
			"UAV_db_path": uav_db_path,
			"stations_db_path": stations_db_path
		}
		uav_result = tester.test_api("/run_UAV_GS_planning", uav_request, "无人机协同规划")
		if not uav_result or not uav_result.get('success'):
			print("❌ 无人机规划失败")
		else:
			print("✅ 无人机协同规划完成")

	# --- 步骤5: 综合可视化 (使用新的通用可视化API) ---
	print(f"\n{'=' * 20} 步骤5: 生成综合可视化地图 {'=' * 20}")
	visualization_path = os.path.join(base_output_dir, "comprehensive_map.html")
	
	# 使用新的通用可视化API
	visualization_request = {
		"target_geojson_path": wuhan_geojson_target,
		"output_html_path": visualization_path,
		"map_config": {
			"tiles": "CartoDB positron",
			"zoom_start": 10,
			"auto_fit_bounds": True
		},
		"satellite_plan": final_plan,
		"satellite_geojson_dir": geojson_dir,
		"uav_results": uav_result,
		"planning_summary_path": os.path.join(geojson_dir, "Wuhan_difference_filtered_planning_summary.json"),
		"uncovered_geojson_path": uncovered_filtered_path,
		"show_boundary": True,
		"show_satellites": True,
		"show_uavs": True,
		"show_ground_stations": True,
		"show_uncovered": True
	}
	
	visualization_result = tester.test_api("/create_comprehensive_visualization", visualization_request, "生成综合可视化地图")
	if visualization_result and visualization_result.get('success'):
		print(f"✅ 可视化地图生成成功: {visualization_result.get('output_path')}")
	else:
		print(f"❌ 可视化地图生成失败: {visualization_result.get('message', '未知错误') if visualization_result else 'API调用失败'}")

	# --- 测试总结 (现在总会执行) ---
	print(f"\n{'=' * 60}")
	print("🎉 测试完成！")
	print(f"{'=' * 60}")
	print(f"测试结果保存在: {base_output_dir}")
	print(f"geojson文件保存在: {geojson_dir}")

	final_coverage_str = f"卫星覆盖率: {total_coverage:.2%}"

	if uav_result and uav_result.get('success'):
		planning_mode = "空地协同" if (
				uav_result.get('results_data', {}).get('ground_station_contribution', {}).get('station_count', 0) > 0
		) else "纯无人机"
		print(f"规划模式: {planning_mode}")
		print(final_coverage_str)
		print("无人机对剩余区域进行了补全规划。")
	else:
		print(f"规划模式: 仅卫星")
		print(final_coverage_str)

	if visualization_result and visualization_result.get('success') and os.path.exists(visualization_path):
		print(f"\n📊 详细的交互式可视化地图已保存至: {visualization_path}")

if __name__ == "__main__":
	main()