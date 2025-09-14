#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
武汉市卫星+无人机协同覆盖规划器 (v4.0 - 对接模块化工具链)
功能：调用模块化的卫星规划工具链进行分析 + 调用高层场景函数进行补全规划
"""

import json
import sys
import os
import traceback

# --- 导入所有工具函数 ---
from GeoPandasTool.difference import difference
from satelliteTool.find_Satellite import get_valid_satellite_tle_as_dict
from DeployTool.UAV_GS_planner import run_planning_scenario
import geopandas as gpd
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union
from DeployTool.satellite_observation_planner import plan_satellite_combination
from satelliteTool.get_observation_overlap import get_observation_overlap


def load_wuhan_boundary(geojson_path="data/Wuhan.geojson"):
	"""加载武汉市边界"""
	with open(geojson_path, 'r', encoding="utf-8") as f:
		return json.load(f)


def get_utm_crs(gdf_latlon):
	"""为给定的GeoDataFrame计算合适的UTM坐标参考系。"""
	try:
		centroid = gdf_latlon.unary_union.centroid
		lon, lat = centroid.x, centroid.y
		utm_band = str(int((lon + 180) // 6 + 1))
		epsg_code = '326' + utm_band.zfill(2) if lat >= 0 else '327' + utm_band.zfill(2)
		return f"EPSG:{epsg_code}"
	except Exception:
		return "EPSG:32649"


def create_comprehensive_visualization(wuhan_boundary, uncovered_area,
                                       completion_results, planning_mode, satellite_plan_data=None,
                                       output_file="comprehensive_coverage_map.html"):
	"""创建信息丰富的综合可视化地图 (更新以展示无人机分配区域、覆盖区域和路径)"""
	print("\n=== 正在创建最终的综合可视化地图... ===")
	try:
		import folium
		import matplotlib.cm as cm
		import matplotlib.colors as colors

		center_lat, center_lon = 30.547, 114.405
		m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles="CartoDB positron")

		folium.GeoJson(wuhan_boundary, name='总任务区域（武汉市）',
		               style_function=lambda x: {'color': 'black', 'weight': 3, 'fillOpacity': 0.05,
		                                         'fillColor': 'black'}, tooltip='总任务区域').add_to(m)

		# 可视化卫星方案
		if satellite_plan_data:
			plan_name = "卫星最优方案" if satellite_plan_data['is_optimal'] else "卫星尽力而为方案"
			coverage_ratio = satellite_plan_data['coverage_ratio']
			footprints = satellite_plan_data['intersection_footprints']

			folium.GeoJson({"type": "FeatureCollection", "features": footprints},
			               name=plan_name,
			               style_function=lambda x: {'color': 'blue', 'weight': 0, 'fillColor': 'blue',
			                                         'fillOpacity': 0.4},
			               tooltip=f'{plan_name} (覆盖率: {coverage_ratio:.2%})').add_to(m)

		if uncovered_area and uncovered_area.get('features'):
			folium.GeoJson(uncovered_area, name='卫星未覆盖区域 (无人机任务区)',
			               style_function=lambda x: {'color': 'orange', 'weight': 2, 'dashArray': '5, 5',
			                                         'fillColor': 'orange', 'fillOpacity': 0.1},
			               tooltip='需要补全的区域').add_to(m)
		if completion_results:
			gs_contribution = completion_results.get("ground_station_contribution", {})
			if gs_contribution and gs_contribution.get("stations_details"):
				gs_group = folium.FeatureGroup(name="地面站贡献", show=True).add_to(m)
				for gs_detail in gs_contribution["stations_details"]:
					lon, lat = gs_detail['coords_latlon']
					radius_m = gs_detail['radius_m']
					gs_point = Point(lon, lat)
					gs_gdf = gpd.GeoDataFrame(geometry=[gs_point], crs="EPSG:4326")
					utm_crs = get_utm_crs(gs_gdf)
					gs_coverage_latlon = gs_gdf.to_crs(utm_crs).buffer(radius_m).to_crs("EPSG:4326")
					folium.GeoJson(gs_coverage_latlon,
					               style_function=lambda x: {'color': 'red', 'weight': 2, 'fillColor': 'red',
					                                         'fillOpacity': 0.3},
					               tooltip=f"地面站 {gs_detail['id']} (半径: {radius_m} m)").add_to(gs_group)
					folium.Marker(location=[lat, lon], popup=f"地面站 {gs_detail['id']}",
					              icon=folium.Icon(color='red', icon='broadcast-tower', prefix='fa')).add_to(gs_group)

			uav_results = completion_results.get("uav_results", [])
			if uav_results:
				uav_count = len(uav_results)
				cmap = cm.get_cmap('viridis', uav_count if uav_count > 0 else 1)
				for i, uav_res in enumerate(uav_results):
					uid = uav_res.get('uav_id', i + 1)
					color = colors.to_hex(cmap(i))
					fg = folium.FeatureGroup(name=f"无人机 {uid}", show=True).add_to(m)
					if uav_res.get("assigned_area_geojson"):
						folium.GeoJson(uav_res["assigned_area_geojson"],
						               tooltip=f'无人机 {uid} 分配区域',
						               style_function=lambda x, c=color: {'color': c, 'weight': 2, 'dashArray': '5, 5',
						                                                  'fillOpacity': 0.15, 'fillColor': c}
						               ).add_to(fg)
					if uav_res.get("coverage_area_geojson"):
						folium.GeoJson(uav_res["coverage_area_geojson"],
						               tooltip=f'无人机 {uid} 覆盖范围',
						               style_function=lambda x, c=color: {'fillColor': c, 'fillOpacity': 0.4,
						                                                  'color': 'transparent', 'weight': 0}
						               ).add_to(fg)
					if uav_res.get("flight_path_geojson"):
						folium.GeoJson(uav_res["flight_path_geojson"],
						               tooltip=f'无人机 {uid} 飞行路径',
						               style_function=lambda x, c=color: {'color': c, 'weight': 3, 'opacity': 0.9}
						               ).add_to(fg)

		folium.LayerControl(collapsed=False, position='topleft').add_to(m)
		m.save(output_file)
		print(f"✅ 综合可视化地图已保存到: {output_file}")
		return output_file
	except Exception as e:
		print(f"❌ 生成综合可视化地图时出错: {e}")
		traceback.print_exc()
		return None


def main():
	"""主函数 (对接模块化工具链版)"""
	print("🛰️  武汉市卫星+无人机协同覆盖规划器 (v4.0 - 对接版)")
	print("=" * 60)

	# --- 步骤 1: 准备输入数据 ---
	print("\n" + "=" * 20 + " 步骤1: 准备输入数据 " + "=" * 20)
	tle_data = get_valid_satellite_tle_as_dict(satellite_db_path='D:\\GeoSensingAPI\\data\\satellite_data.db',
	                                           mission_theme='Land cover',
	                                           sensor_type='Optical Sensor')
	wuhan_boundary = load_wuhan_boundary()
	wuhan_geojson_path = "D:\\GeoSensingAPI\\data\\Wuhan.geojson"

	# 定义卫星规划各阶段的输出目录
	base_sat_output_dir = "satellite_planning_output"
	overlap_output_dir = os.path.join(base_sat_output_dir, "B_observation_overlaps")
	final_plan_output_dir = os.path.join(base_sat_output_dir, "C_final_plan")

	# --- [修改] 步骤 2: 调用模块化的卫星规划工具链 ---
	print("\n" + "=" * 20 + " 步骤2.1: 计算卫星观测重叠率 " + "=" * 20)
	coverage_results = get_observation_overlap(
		tle_dict=tle_data,
		start_time_str="2025-08-01 00:00:00.000",
		end_time_str="2025-08-01 23:59:59.000",
		target_geojson_path=wuhan_geojson_path,
		fov=9.0,
		interval_seconds=600,
		output_dir=overlap_output_dir
	)

	if not coverage_results:
		print("❌ 在指定时间段内，没有卫星与目标区域发生重叠，规划终止。")
		return

	print("\n" + "=" * 20 + " 步骤2.2: 规划卫星方案并生成报告 " + "=" * 20)
	sat_plan_results = plan_satellite_combination(
		coverage_results=coverage_results,
		target_geojson_path=wuhan_geojson_path,
		target_coverage=0.99,
		output_dir=final_plan_output_dir
	)

	# --- 步骤 3: 处理卫星规划结果，计算未覆盖区域 ---
	print("\n" + "=" * 20 + " 步骤3: 分析卫星结果，计算补全区域 " + "=" * 20)
	final_plan = (sat_plan_results['report']['optimal_plan'] or
	              sat_plan_results['report']['best_effort_plan'])

	if not final_plan:
		print("❌ 卫星规划失败或未找到任何相交卫星，无法进行无人机补全。")
		return

	total_coverage = final_plan['coverage']
	is_optimal = sat_plan_results['success']
	intersection_file = sat_plan_results.get('intersection_path')

	if not intersection_file or not os.path.exists(intersection_file):
		print(f"❌ 卫星规划的交集文件不存在或为空，无法进行无人机补全。路径: {intersection_file}")
		return

	if is_optimal:
		print(f"🛰️  卫星最优方案已找到，覆盖率: {total_coverage:.2%}")
	else:
		print(f"🛰️  未找到满足目标的方案，采纳'尽力而为'的最佳方案，覆盖率: {total_coverage:.2%}")

	if total_coverage >= 0.99:
		print(f"✅ 卫星覆盖率已达到 {total_coverage:.2%}，无需无人机补全。")
		with open(intersection_file, 'r', encoding='utf-8') as f:
			covered_geojson = json.load(f)
		satellite_plan_data = {
			"is_optimal": is_optimal, "coverage_ratio": total_coverage,
			"intersection_footprints": covered_geojson['features']
		}
		create_comprehensive_visualization(
			wuhan_boundary=wuhan_boundary, uncovered_area={}, completion_results=None,
			planning_mode="仅卫星", satellite_plan_data=satellite_plan_data,
			output_file="final_coverage_map.html"
		)
		return

	print(f"⚠️  卫星覆盖率 {total_coverage:.2%} < 99%，开始计算无人机补全区域。")

	task_to_run = {
		"source": wuhan_geojson_path,
		"clip": intersection_file
	}
	batch_tasks_list = [task_to_run]
	intermediate_output_dir = os.path.join(base_sat_output_dir, "intermediate_difference")
	filtered_output_dir = os.path.join(intermediate_output_dir, "filtered")  # 过滤后文件的存放目录

	# 步骤 3.2: 调用 difference 函数获取原始差集结果
	print("\n--- 步骤 3.2: 执行差集计算 ---")
	raw_difference_results = difference(
		batch_tasks_list,
		output_directory=intermediate_output_dir
	)

	if not raw_difference_results or all(k == "errors" for k in raw_difference_results):
		print("差集计算步骤未能生成有效输出。")
		return

	# 步骤 3.3: 调用 filter_sliver_polygons 函数清理碎片
	print("\n--- 步骤 3.3: 执行碎片过滤 ---")
	filtered_results = filter_sliver_polygons(
		input_files_dict=raw_difference_results,
		output_directory=filtered_output_dir,
		min_area_threshold_m2=100.0  # 在这里设置过滤阈值
	)

	# 步骤 3.4: 解析最终过滤后的结果
	# 构造原始键名以在过滤结果中查找对应的文件路径
	source_basename = os.path.splitext(os.path.basename(wuhan_geojson_path))[0]
	clip_basename = os.path.splitext(os.path.basename(intersection_file))[0]
	expected_key = f"{source_basename}_difference_{clip_basename}"

	final_geojson_filepath = filtered_results.get(expected_key)

	if not final_geojson_filepath:
		print(f"错误：无法在过滤结果中找到键 '{expected_key}' 对应文件。")
		print(f"可用键: {filtered_results.keys()}")
		return

	print(f"最终使用的干净文件: {final_geojson_filepath}")

	try:
		# 重新读取过滤后的文件内容以转换为 Shapely 对象
		with open(final_geojson_filepath, 'r', encoding='utf-8') as f:
			uncovered_data = json.load(f)

		uncovered_geometries = [shape(feature['geometry']) for feature in uncovered_data.get('features', []) if
		                        feature.get('geometry')]
		uncovered_geom = unary_union(uncovered_geometries)

	except Exception as e:
		print(f"读取过滤后的差集文件 {final_geojson_filepath} 时出错: {e}")
		return

	uncovered_features = []
	if not uncovered_geom.is_empty:
		# hasattr(uncovered_geom, 'geoms') 是一种可靠的方式来检查一个几何对象是否是集合类型 (如 MultiPolygon)
		if hasattr(uncovered_geom, 'geoms'):
			for geom in uncovered_geom.geoms:
				uncovered_features.append({
					"type": "Feature",
					"geometry": mapping(geom),
					"properties": {}
				})
		else:  # 如果它是一个单一的几何体 (如 Polygon)
			uncovered_features.append({
				"type": "Feature",
				"geometry": mapping(uncovered_geom),
				"properties": {}
			})

	uncovered_area = {
		"type": "FeatureCollection",
		"features": uncovered_features
	}
	# --- [修复结束] ---

	if uncovered_geom.is_empty:
		print("✅ 计算后发现未覆盖区域为空，无需进行补全规划。")
		with open(intersection_file, 'r', encoding='utf-8') as f:
			covered_geojson = json.load(f)
		satellite_plan_data = {"is_optimal": is_optimal, "coverage_ratio": total_coverage,
		                       "intersection_footprints": covered_geojson['features']}
		create_comprehensive_visualization(
			wuhan_boundary=wuhan_boundary, uncovered_area={}, completion_results=None,
			planning_mode="仅卫星", satellite_plan_data=satellite_plan_data,
			output_file="final_coverage_map.html"
		)
		return

	# --- 步骤 4: 调用无人机补全规划 ---
	print("\n" + "=" * 20 + " 步骤4: 调用无人机场景函数进行补全规划 " + "=" * 20)
	TEMP_FILE_PATH = "temp_uncovered_for_scenario.geojson"
	completion_results = None
	try:
		with open(TEMP_FILE_PATH, 'w', encoding='utf-8') as f:
			json.dump(uncovered_area, f)
		completion_results = run_planning_scenario(
			geojson_path=TEMP_FILE_PATH,
			create_map=True,
			verbose=True,
			UAV_db_path="data/UAV_data.db",
			stations_db_path="data/Stations_data.db"
		)
	finally:
		if os.path.exists(TEMP_FILE_PATH):
			os.remove(TEMP_FILE_PATH)
			print(f"\n临时文件 '{TEMP_FILE_PATH}' 已删除。")

	# --- 步骤 5: 处理结果并生成最终的综合地图 ---
	if completion_results:
		# print(f"\n🎉 补全规划成功！详细结果保存在 '{}' 文件夹中。")
		with open(intersection_file, 'r', encoding='utf-8') as f:
			covered_geojson = json.load(f)
		planning_mode = "空地协同" if completion_results.get("ground_station_contribution", {}).get("station_count",
		                                                                                        0) > 0 else "纯无人机"
		satellite_plan_data = {
			"is_optimal": is_optimal, "coverage_ratio": total_coverage,
			"intersection_footprints": covered_geojson['features']
		}
		create_comprehensive_visualization(
			wuhan_boundary=wuhan_boundary,
			uncovered_area=uncovered_area,
			completion_results=completion_results,
			planning_mode=planning_mode,
			satellite_plan_data=satellite_plan_data,
			output_file="final_coverage_map.html"
		)
	else:
		print("\n❌ 补全规划失败。")


if __name__ == "__main__":
	main()
