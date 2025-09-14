#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
通用卫星观测规划器 (v4 - 模块化版)

此版本将复杂的规划流程拆分为一个清晰的、按顺序执行的工具链。
核心的数据获取与轨迹计算函数已移至外部模块，本脚本专注于最终的方案规划与评估。

工具链流程:
1. `get_valid_satellite_tle_as_dict` (from satelliteTool): 从数据库获取基础的卫星TLE数据。
2. `get_observation_overlap` (from satelliteTool): (核心计算) 接收TLE数据，计算每个卫星与
   目标区域的精确覆盖率，并输出中间结果文件。
3. `plan_satellite_combination` (local): 接收上一步的计算结果，寻找最优的单星或多星组合方案，
   并生成最终的报告、地图和汇总文件。

主函数 (`main`) 负责按顺序调用这些工具，并将上一步的输出作为下一步的输入。
"""

import json
import os
from datetime import datetime
from itertools import combinations

import folium
import geojson
from pyproj import Proj, Transformer
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import unary_union, transform
from shapely.validation import make_valid
import sys

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import get_geojson_path

# ==============================================================================
# 导入外部工具函数
# ==============================================================================
from satelliteTool.find_Satellite import get_valid_satellite_tle_as_dict
from satelliteTool.get_observation_overlap import get_observation_overlap


# ==============================================================================
# 本地辅助函数
# ==============================================================================
def split_antimeridian(geom):
	"""
	分割跨越180度经线（国际日期变更线）的几何图形。
	"""
	if not isinstance(geom, Polygon) or geom.bounds[2] - geom.bounds[0] < 180:
		return geom
	cutter = Polygon([(-180, -90), (-180, 90), (0, 90), (0, -90), (-180, -90)])
	parts = [geom.intersection(cutter)]
	diffed = geom.difference(cutter)
	if not diffed.is_empty:
		parts.append(transform(lambda x, y, z=None: (x - 360, y), diffed))
	return MultiPolygon([p for p in parts if not p.is_empty])


def plan_satellite_combination(
		coverage_results: dict,
		target_geojson_path: str,
		target_coverage: float = 0.99
) -> dict:
	"""
	根据预先计算好的覆盖率数据，规划最优方案并生成报告、地图。
	"""
	print("\n" + "=" * 60)
	print(" C. 卫星观测方案规划与评估 ".center(60))
	print("=" * 60)
	print(f"\n[1/3] 正在准备规划环境...")

	area_name = os.path.basename(target_geojson_path).split('.')[0]

	try:
		# 确保使用 utf-8 编码读取文件
		with open(target_geojson_path, 'r', encoding='utf-8') as f:
			target_geojson_obj = json.load(f)
		target_shape = unary_union([make_valid(shape(f['geometry'])) for f in target_geojson_obj.get('features', [])])
	except Exception as e:
		print(f"❌ 加载观测区域GeoJSON失败: {e}")
		return {'success': False, 'message': 'Failed to load target GeoJSON.'}

	print(f"\n[2/3] 正在寻找最优覆盖方案 (目标: {target_coverage:.0%})...")
	wgs84_proj = Proj('epsg:4326')
	equal_area_proj = Proj('+proj=moll')
	transformer = Transformer.from_proj(wgs84_proj, equal_area_proj, always_xy=True)
	target_area = transform(transformer.transform, target_shape).area

	# --- 性能优化: 预加载并合并每个卫星的足迹几何图形 ---
	print("   - 正在预加载卫星足迹数据以提高计算速度...")
	preloaded_geometries = {}
	for sat, data in coverage_results.items():
		# 修改：使用 'overlap_file' 而不是 'intersection_footprints_path'
		path = data.get('overlap_file')
		if path and os.path.exists(path):
			try:
				with open(path, 'r', encoding='utf-8') as f:
					geo_data = json.load(f)
				# 读取该卫星的所有足迹并合并为一个几何对象
				footprints = [make_valid(shape(feat['geometry'])) for feat in geo_data.get('features', []) if
				              feat.get('geometry')]
				if footprints:
					preloaded_geometries[sat] = unary_union(footprints)
			except Exception as e:
				print(f"   - 警告: 预加载卫星 '{sat}' 的数据失败: {e}")
	print(f"   - ✅ 成功预加载 {len(preloaded_geometries)} 颗卫星的数据。")
	# --- 优化结束 ---

	optimal_plan, best_effort_plan = None, None

	# 检查单星方案
	for sat, data in coverage_results.items():
		if data['coverage_ratio'] >= target_coverage:
			optimal_plan = {'type': 'single', 'satellites': [sat], 'coverage': data['coverage_ratio']}
			print(f"✅ 找到单个卫星解决方案: {sat} (覆盖率: {data['coverage_ratio']:.2%})")
			break

	# 检查组合方案 (使用预加载的数据)
	if not optimal_plan:
		# 使用已成功预加载数据的卫星进行组合
		available_sats = list(preloaded_geometries.keys())
		sorted_sats = sorted(available_sats, key=lambda s: coverage_results[s]['coverage_ratio'], reverse=True)

		for combo_size in range(2, min(6, len(sorted_sats) + 1)):
			print(f"   - 正在检查 {combo_size} 颗卫星的组合...")
			for combo in combinations(sorted_sats, combo_size):
				# 从预加载的字典中获取几何对象，而不是从文件中反复读取
				footprints_to_merge = [preloaded_geometries[s] for s in combo if s in preloaded_geometries]
				if not footprints_to_merge: 
					continue

				# 正确的计算方式：合并这个组合中所有卫星的几何对象
				merged_fp = unary_union(footprints_to_merge)
				combo_coverage = min(1.0, transform(transformer.transform, merged_fp).area / target_area)

				if combo_coverage >= target_coverage:
					optimal_plan = {'type': 'combination', 'satellites': list(combo), 'coverage': combo_coverage}
					print(f"✅ 找到最佳组合方案: {list(combo)} (覆盖率: {combo_coverage:.2%})")
					break
			if optimal_plan: 
				break

	# "尽力而为"方案 (同样使用预加载的数据)
	if not optimal_plan:
		print("   未能找到满足目标的方案，正在计算'尽力而为'的最佳方案...")
		all_sats = list(preloaded_geometries.keys())
		if all_sats:
			# 直接合并所有已预加载的几何对象，效率更高
			all_footprints_geom = list(preloaded_geometries.values())
			merged_all = unary_union(all_footprints_geom)
			best_effort_coverage = min(1.0, transform(transformer.transform, merged_all).area / target_area)
			best_effort_plan = {
				'type': 'best_effort_combination', 'satellites': all_sats, 'coverage': best_effort_coverage
			}
			print(f"   ✅ '尽力而为'方案计算完成，合并所有卫星可达覆盖率: {best_effort_coverage:.2%}")

	print("\n[3/3] 正在生成最终结果...")
	plan_to_use = optimal_plan or best_effort_plan

	# 生成报告
	report = {
		'target_area_path': target_geojson_path, 
		'target_coverage_goal': target_coverage,
		'coverage_by_satellite': {k: v['coverage_ratio'] for k, v in coverage_results.items()},
		'optimal_plan': optimal_plan, 
		'best_effort_plan': best_effort_plan,
		'generation_time': datetime.now().isoformat()
	}
	report_path = get_geojson_path(f"{area_name}_planning_report.json")
	with open(report_path, 'w', encoding='utf-8') as f:
		json.dump(report, f, ensure_ascii=False, indent=2)
	print(f"✅ 规划报告已保存到: {report_path}")

	# 生成地图
	m = folium.Map(location=[30.4, 114.4], zoom_start=7, tiles="CartoDB positron")
	# --- FIX: 使用已加载的 geojson 对象而非文件路径，以避免编码错误 ---
	folium.GeoJson(target_geojson_obj, name=f'观测区域: {area_name}',
	               style_function=lambda x: {'color': 'black', 'weight': 3, 'fillOpacity': 0.1}).add_to(m)
	# ---
	colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0']
	sorted_results = sorted(coverage_results.items(), key=lambda item: item[1]['coverage_ratio'], reverse=True)
	for i, (sat_name, data) in enumerate(sorted_results):
		# 修改：使用 'overlap_file' 而不是 'intersection_footprints_path'
		path = data.get('overlap_file')
		if path and os.path.exists(path):
			folium.GeoJson(
				path, name=f"{sat_name} ({data['coverage_ratio']:.1%})",
				style_function=lambda x, c=colors[i % len(colors)]: {'weight': 0, 'fillColor': c, 'fillOpacity': 0.35},
				tooltip=f"<b>{sat_name}</b><br>覆盖率: {data['coverage_ratio']:.2%}"
			).add_to(m)
	folium.LayerControl(collapsed=False).add_to(m)
	map_path = get_geojson_path(f"{area_name}_coverage_map.html")
	m.save(map_path)
	print(f"✅ 可视化地图已保存到: {map_path}")

	# 生成最终交集文件
	intersection_path = None
	if plan_to_use:
		final_footprints = []
		for s in plan_to_use['satellites']:
			# 修改：使用 'overlap_file' 而不是 'intersection_footprints_path'
			path = coverage_results[s].get('overlap_file')
			if path and os.path.exists(path):
				with open(path, 'r', encoding='utf-8') as f: 
					geo_data = json.load(f)
				final_footprints.extend([shape(feat['geometry']) for feat in geo_data.get('features', [])])
		if final_footprints:
			final_union = unary_union([make_valid(fp) for fp in final_footprints])
			final_intersection = final_union.intersection(target_shape)
			feature = geojson.Feature(geometry=mapping(final_intersection), properties=plan_to_use)
			intersection_geojson = geojson.FeatureCollection([feature])
			intersection_path = get_geojson_path(f"{area_name}_final_intersection.geojson")
			with open(intersection_path, 'w', encoding='utf-8') as f:
				json.dump(intersection_geojson, f, ensure_ascii=False, indent=2)
			print(f"✅ 最终方案交集GeoJSON已保存到: {intersection_path}")

	return {
		'success': optimal_plan is not None,
		'report': report,
		'map_path': map_path,
		'intersection_path': intersection_path
	}


def main():
	"""主函数，作为工具链的编排器，按顺序执行所有步骤。"""
	print("=" * 60)
	print("🚀 通用卫星观测规划器 (工具链版) 开始运行 🚀".center(60))
	print("=" * 60)

	# --- 0. 定义规划参数 ---
	start_time = "2025-08-1 00:00:00.000"
	end_time = "2025-08-1 23:59:59.000"
	# 请确保数据库和目标区域文件路径正确
	db_path = "D:\\GeoSensingAPI\\data\\satellite_data.db"
	target_geojson_path = "D:\\GeoSensingAPI\\data\\Wuhan.geojson"
	target_coverage_goal = 0.95
	satellite_fov = 11.0
	time_interval_seconds = 600

	# --- 步骤 A: 获取 TLE 数据 ---
	print("\n" + "=" * 60)
	print(" A. 从数据库获取卫星 TLE ".center(60))
	print("=" * 60)
	try:
		tle_data = get_valid_satellite_tle_as_dict(
			satellite_db_path=db_path,
			mission_theme='Land cover',
			sensor_type='Optical Sensor'
		)
		if not tle_data: 
			raise ValueError("数据库中没有找到符合条件的TLE数据")
		print(f"✅ 成功从数据库加载 {len(tle_data)} 颗卫星的 TLE 数据。")
	except Exception as e:
		print(f"❌ 步骤 A 失败: {e}")
		return

	# --- 步骤 B: 计算观测重叠率 ---
	print("\n" + "=" * 60)
	print(" B. 计算观测重叠率 ".center(60))
	print("=" * 60)
	try:
		coverage_results = get_observation_overlap(
			tle_dict=tle_data, 
			start_time_str=start_time, 
			end_time_str=end_time,
			target_geojson_path=target_geojson_path, 
			fov=satellite_fov,
			interval_seconds=time_interval_seconds
		)
		if not coverage_results:
			print("\n⚠️ 在指定时间段内，没有卫星覆盖目标区域。规划流程结束。")
			return
		print(f"✅ 成功计算 {len(coverage_results)} 颗相交卫星的覆盖率。")
		for sat, data in coverage_results.items():
			print(f"   - {sat}: 覆盖率 {data['coverage_ratio']:.2%}")
	except Exception as e:
		print(f"❌ 步骤 B 失败: 计算覆盖率时发生错误: {e}")
		return

	# --- 步骤 C: 规划最优方案并生成报告 ---
	final_results = plan_satellite_combination(
		coverage_results=coverage_results,
		target_geojson_path=target_geojson_path,
		target_coverage=target_coverage_goal
	)

	# --- 4. 打印最终摘要 ---
	if final_results and final_results.get('report'):
		report = final_results['report']
		if report.get('optimal_plan'):
			plan = report['optimal_plan']
			print("\n" + "=" * 60)
			print("🏆 最终推荐方案 🏆".center(60))
			print("=" * 60)
			print(f"  - 类型: {'单星覆盖' if plan['type'] == 'single' else '多星组合'}")
			print(f"  - 卫星: {', '.join(plan['satellites'])}")
			print(f"  - 预估覆盖率: {plan['coverage']:.2%}")
		elif report.get('best_effort_plan'):
			plan = report['best_effort_plan']
			print("\n" + "=" * 60)
			print("〽️ 未达目标，提供尽力而为的最佳方案 〽️".center(60))
			print("=" * 60)
			print(f"  - 类型: 所有相交卫星组合")
			print(f"  - 卫星: {', '.join(plan['satellites'])}")
			print(f"  - 预估覆盖率: {plan['coverage']:.2%}")
		print(f"  - 详细结果保存在全局 geojson 目录")
		print("=" * 60)
	else:
		print("\n❌ 未能生成任何最终规划方案。")


if __name__ == "__main__":
	main()