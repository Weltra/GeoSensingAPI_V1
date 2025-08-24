# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: UAV_GS_planner
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-13
REVISED_DATE: 2025-08-21
REVISION_NOTES: Refactored for modularity and easier external invocation.
"""

import os
import math
import sys
import json
import geopandas as gpd
import pandas as pd
import sqlite3
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, MultiPoint, MultiLineString
from shapely.ops import unary_union, voronoi_diagram
from sklearn.cluster import KMeans
import numpy as np
import folium
import matplotlib.pyplot as plt
from DeployTool.find_GS import find_stations_nested_dict
from DeployTool.find_UAV_combination import find_drone_combination

os.environ['OMP_NUM_THREADS'] = '1'


# ==============================================================================
# 1. 辅助函数 (Helper Functions)
# ==============================================================================
def get_utm_crs(gdf_latlon):
	"""根据GeoDataFrame的质心计算最合适的UTM坐标系。"""
	if gdf_latlon.empty:
		raise ValueError("输入的GeoDataFrame为空，无法确定UTM坐标系。")
	centroid = gdf_latlon.unary_union.centroid
	lon, lat = centroid.x, centroid.y
	utm_band = str(int((lon + 180) // 6 + 1))
	epsg_code = '326' + utm_band.zfill(2) if lat >= 0 else '327' + utm_band.zfill(2)
	return f"EPSG:{epsg_code}"


# ==============================================================================
# 2. 核心路径生成函数
# ==============================================================================
def generate_s_path_in_polygon(polygon: (Polygon, MultiPolygon), swath_width: float) -> (object, float):
	"""在单个或多个多边形内生成S形扫描路径。"""
	if polygon.is_empty or polygon.area == 0:
		return None, 0

	if isinstance(polygon, MultiPolygon):
		all_path_segments = []
		total_length = 0
		for p in polygon.geoms:
			path, length = generate_s_path_in_polygon(p, swath_width)
			if path:
				all_path_segments.extend(list(path.geoms))
				total_length += length
		if not all_path_segments:
			return None, 0
		return MultiLineString(all_path_segments), total_length

	mbr = polygon.minimum_rotated_rectangle
	if mbr.is_empty:
		return None, 0

	x, y = mbr.exterior.coords.xy
	edge_lengths = (Point(x[0], y[0]).distance(Point(x[1], y[1])), Point(x[1], y[1]).distance(Point(x[2], y[2])))
	long_edge_start_pt = (Point(x[0], y[0]), Point(x[1], y[1])) if edge_lengths[0] > edge_lengths[1] else \
		(Point(x[1], y[1]), Point(x[2], y[2]))
	angle_rad = math.atan2(long_edge_start_pt[1].y - long_edge_start_pt[0].y,
	                       long_edge_start_pt[1].x - long_edge_start_pt[0].x)

	rotated_poly = gpd.GeoSeries(polygon).rotate(-math.degrees(angle_rad), origin=(0, 0)).iloc[0]
	min_x, min_y, max_x, max_y = rotated_poly.bounds

	scan_segments = []
	y_current = min_y + swath_width / 2
	direction = 1
	while y_current <= max_y:
		scan_line = LineString([(min_x - 1, y_current), (max_x + 1, y_current)])
		intersected = rotated_poly.intersection(scan_line)
		if not intersected.is_empty:
			geoms = list(intersected.geoms) if intersected.geom_type == 'MultiLineString' else [intersected]
			geoms.sort(key=lambda g: g.coords[0][0])
			if direction == -1:
				geoms.reverse()
			scan_segments.extend(geoms)
		y_current += swath_width
		direction *= -1

	if not scan_segments:
		return None, 0

	final_path_rotated = MultiLineString(scan_segments)
	final_path = gpd.GeoSeries(final_path_rotated).rotate(math.degrees(angle_rad), origin=(0, 0)).iloc[0]

	return (final_path, final_path.length) if final_path else (None, 0)


# ==============================================================================
# 3. 主规划器类 (Main Planner Class)
# ==============================================================================
class CollaborativePlanner:
	"""
	一个用于无人机（UAV）和地面站（GS）协同区域覆盖规划的类。

	该类负责接收任务区域、无人机参数和地面站信息，然后执行区域分解、
	路径规划、可行性分析和覆盖率计算。
	"""

	def __init__(self, geojson_path: str, uavs_params: list, ground_station_params: dict = None):
		print("--- 初始化空地协同规划器 ---")
		if not os.path.exists(geojson_path):
			raise FileNotFoundError(f"GeoJSON文件未找到: {geojson_path}")
		self.uavs = uavs_params
		self.num_uavs = len(uavs_params)
		self.ground_station_params = ground_station_params if ground_station_params else {}

		print(f"加载区域文件: {geojson_path}")
		self.area_gdf_latlon = gpd.read_file(geojson_path).to_crs("EPSG:4326")
		self.original_crs = self.area_gdf_latlon.crs
		self.utm_crs = get_utm_crs(self.area_gdf_latlon)
		print(f"原始坐标系: {self.original_crs}. 内部计算将使用UTM坐标系: {self.utm_crs}")

		self.area_gdf_utm = self.area_gdf_latlon.to_crs(self.utm_crs)
		self.total_area_shape_utm = self.area_gdf_utm.unary_union

		self.ground_station_coverage_utm = None
		self.processed_stations = []
		self._initialize_ground_station()

		if self.ground_station_coverage_utm:
			self.uav_target_area_utm = self.total_area_shape_utm.difference(self.ground_station_coverage_utm)
			print("已扣除所有地面站的总覆盖范围，无人机将规划剩余区域。")
		else:
			self.uav_target_area_utm = self.total_area_shape_utm

		self.results = []
		self.coverage_percentage = 0.0

	def _initialize_ground_station(self):
		if not self.ground_station_params:
			print("未提供地面站信息。")
			return
		print(f"正在处理 {len(self.ground_station_params)} 个地面站信息...")
		all_coverage_polygons = []
		try:
			for station_id, details in self.ground_station_params.items():
				lon, lat = details['location']['longitude'], details['location']['latitude']
				radius_m = details['observation_range_km'] * 1000
				gs_point_utm = gpd.GeoSeries([Point(lon, lat)], crs=self.original_crs).to_crs(self.utm_crs).iloc[0]
				all_coverage_polygons.append(gs_point_utm.buffer(radius_m))
				self.processed_stations.append({'id': station_id, 'geom_utm': gs_point_utm, 'radius_m': radius_m})
		except (KeyError, TypeError) as e:
			print(f"【错误】一个或多个地面站参数格式不正确。错误详情: {e}")
			return
		if all_coverage_polygons:
			self.ground_station_coverage_utm = unary_union(all_coverage_polygons)
			print(f"所有地面站的总覆盖区域创建成功。")

	def pre_check_feasibility(self) -> bool:
		print("\n--- 执行可行性预检查 ---")
		uav_area_needed = self.uav_target_area_utm.area
		total_max_coverage_capability = sum(uav['speed'] * uav['flight_time'] * uav['swath_width'] for uav in self.uavs)
		print(f"总任务区域面积: {self.total_area_shape_utm.area:.2f} m²")
		if self.ground_station_coverage_utm:
			gs_cover_in_area = self.total_area_shape_utm.intersection(self.ground_station_coverage_utm).area
			print(f"地面站已覆盖面积: {gs_cover_in_area:.2f} m²")
		print(f"无人机需覆盖的剩余面积: {uav_area_needed:.2f} m²")
		print(f"无人机队理论最大总覆盖能力: {total_max_coverage_capability:.2f} m²")
		if total_max_coverage_capability < uav_area_needed:
			print("【警告】无法覆盖该区域：机队总覆盖能力小于剩余的区域面积需求。")
			return False
		print("【成功】预检查通过，机队理论上有能力覆盖剩余区域。")
		return True

	def decompose_area_and_assign(self, n_points_per_sq_km: int = 5):
		print(f"\n--- 步骤 1: 使用K-Means和泰森多边形分解无人机目标区域 ---")
		if self.uav_target_area_utm.is_empty:
			print("无人机目标区域为空，无需分解。")
			self.results = [{"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": Polygon()} for uav in self.uavs]
			return

		area_sq_km = self.uav_target_area_utm.area / 1_000_000
		n_points = max(self.num_uavs * 50, int(area_sq_km * n_points_per_sq_km))
		min_x, min_y, max_x, max_y = self.uav_target_area_utm.bounds

		points_inside = []
		while len(points_inside) < n_points:
			rand_points = np.random.rand(n_points * 2, 2)
			rand_points[:, 0] = rand_points[:, 0] * (max_x - min_x) + min_x
			rand_points[:, 1] = rand_points[:, 1] * (max_y - min_y) + min_y
			for p in rand_points:
				if len(points_inside) >= n_points: break
				if self.uav_target_area_utm.contains(Point(p)):
					points_inside.append(p)

		kmeans = KMeans(n_clusters=self.num_uavs, random_state=42, n_init=10).fit(np.array(points_inside))
		centers = MultiPoint(kmeans.cluster_centers_)
		voronoi_cells = voronoi_diagram(centers, envelope=self.uav_target_area_utm)
		print(f"已生成 {len(voronoi_cells.geoms)} 个泰森多边形单元格。")

		self.results = []
		for i, center_point in enumerate(centers.geoms):
			uav = self.uavs[i]
			assigned_cell = next((cell for cell in voronoi_cells.geoms if cell.contains(center_point)), None)
			sub_area_utm = self.uav_target_area_utm.intersection(assigned_cell) if assigned_cell else Polygon()
			self.results.append({"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": sub_area_utm})
		print("无人机区域分解与分配完成。")

	def plan_paths_for_all(self):
		print("\n--- 步骤 2: 为每个无人机子区域规划路径 ---")
		for result in self.results:
			uav = result['uav_params']
			sub_area_utm = result['sub_area_utm']
			if sub_area_utm.is_empty:
				print(f"   - 无人机 {uav['id']} 分配区域为空，跳过。")
				result.update({'path_utm': None, 'path_length': 0, 'flight_duration_needed': 0, 'is_feasible': True})
				continue

			print(f"正在为无人机 {uav['id']} 规划路径...")
			path_utm, path_length = generate_s_path_in_polygon(sub_area_utm, uav['swath_width'])
			duration = (path_length / uav['speed']) if path_length and uav['speed'] > 0 else 0

			result.update({
				'path_utm': path_utm,
				'path_length': path_length or 0,
				'flight_duration_needed': duration,
				'is_feasible': duration <= uav['flight_time']
			})

	def calculate_coverage(self):
		print("\n--- 步骤 3: 计算最终协同覆盖率 ---")
		all_coverage_polygons_utm = [self.ground_station_coverage_utm] if self.ground_station_coverage_utm else []
		for result in self.results:
			if result.get('path_utm') and not result['path_utm'].is_empty:
				uav = result['uav_params']
				all_coverage_polygons_utm.append(result['path_utm'].buffer(uav['swath_width'] / 2, cap_style=2))

		if not all_coverage_polygons_utm or self.total_area_shape_utm.area == 0:
			self.coverage_percentage = 0.0
			return

		total_coverage_union_utm = unary_union(all_coverage_polygons_utm)
		effective_coverage_utm = self.total_area_shape_utm.intersection(total_coverage_union_utm)
		self.coverage_percentage = (effective_coverage_utm.area / self.total_area_shape_utm.area) * 100
		print(f"原始区域总面积: {self.total_area_shape_utm.area:.2f} m²")
		print(f"协同有效覆盖总面积: {effective_coverage_utm.area:.2f} m²")
		print(f"最终协同覆盖率: {self.coverage_percentage:.2f}%")

	def visualize_plan(self, output_path: str):
		"""将规划结果可视化并保存为HTML文件。"""
		print(f"\n--- 步骤 4: 可视化协同规划结果 ---")
		center_latlon = self.area_gdf_latlon.unary_union.centroid.coords[0][::-1]
		m = folium.Map(location=center_latlon, zoom_start=12, tiles="CartoDB positron")

		folium.GeoJson(self.area_gdf_latlon, name='总任务区域',
		               style_function=lambda x: {'color': 'black', 'weight': 2.5, 'fillOpacity': 0.05,
		                                         'fillColor': 'black'},
		               ).add_to(m)

		if self.processed_stations and self.ground_station_coverage_utm:
			gs_group = folium.FeatureGroup(name="地面站", show=True).add_to(m)
			gs_coverage_latlon = gpd.GeoSeries([self.ground_station_coverage_utm], crs=self.utm_crs).to_crs(
				self.original_crs)
			folium.GeoJson(gs_coverage_latlon, tooltip="所有地面站的总覆盖范围",
			               style_function=lambda x: {'color': 'red', 'weight': 2, 'fillColor': 'red',
			                                         'fillOpacity': 0.3},
			               ).add_to(gs_group)
			for station in self.processed_stations:
				gs_point_latlon = gpd.GeoSeries([station['geom_utm']], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0]
				folium.Marker(
					location=[gs_point_latlon.y, gs_point_latlon.x],
					popup=f"地面站ID: {station['id']}<br>半径: {station['radius_m']} m",
					icon=folium.Icon(color='red', icon='broadcast-tower', prefix='fa')
				).add_to(gs_group)

		colors = plt.cm.get_cmap('viridis', self.num_uavs)
		for i, result in enumerate(self.results):
			uav_id = result['uav_id']
			color_hex = plt.cm.colors.to_hex(colors(i))
			fg = folium.FeatureGroup(name=f"无人机 {uav_id}", show=True).add_to(m)

			sub_area_utm = result.get('sub_area_utm')
			if sub_area_utm and not sub_area_utm.is_empty:
				sub_area_latlon = gpd.GeoSeries([sub_area_utm], crs=self.utm_crs).to_crs(self.original_crs)
				folium.GeoJson(sub_area_latlon, tooltip=f'无人机 {uav_id} 分配区域',
				               style_function=lambda x, c=color_hex: {'color': c, 'weight': 1.5, 'fillColor': c,
				                                                      'fillOpacity': 0.25},
				               ).add_to(fg)

			path_utm = result.get('path_utm')
			if path_utm and not path_utm.is_empty:
				uav = result['uav_params']
				coverage_poly_utm = path_utm.buffer(uav['swath_width'] / 2, cap_style=2)
				path_latlon = gpd.GeoSeries([path_utm], crs=self.utm_crs).to_crs(self.original_crs)
				coverage_latlon = gpd.GeoSeries([coverage_poly_utm], crs=self.utm_crs).to_crs(self.original_crs)
				folium.GeoJson(coverage_latlon, tooltip=f'无人机 {uav_id} 覆盖范围',
				               style_function=lambda x, c=color_hex: {'fillColor': c, 'fillOpacity': 0.4,
				                                                      'color': 'transparent'},
				               ).add_to(fg)
				folium.GeoJson(path_latlon, tooltip=f"无人机 {uav_id} 路径",
				               style_function=lambda x, c=color_hex: {'color': c, 'weight': 2.5},
				               ).add_to(fg)

		folium.LayerControl(collapsed=False).add_to(m)
		m.save(output_path)
		print(f"可视化地图已保存至: {output_path}")

	def get_results_as_json(self) -> dict:
		"""将规划结果编译为结构化的字典（用于JSON序列化）。"""
		summary = {"total_area_sqm": float(self.total_area_shape_utm.area),  # 增加转换
		           "final_collaborative_coverage_percentage": float(self.coverage_percentage),  # 增加转换
		           "ground_station_contribution": {}, "uav_results": []}

		if self.processed_stations and self.ground_station_coverage_utm:
			gs_coverage_in_area = self.total_area_shape_utm.intersection(self.ground_station_coverage_utm)
			summary["ground_station_contribution"] = {
				"station_count": len(self.processed_stations),
				"stations_details": [{
					'id': s['id'],
					'radius_m': float(s['radius_m']),  # 增加转换
					'coords_latlon':
						gpd.GeoSeries([s['geom_utm']], crs=self.utm_crs).to_crs(self.original_crs).iloc[0].coords[0]
				} for s in self.processed_stations],
				"total_covered_area_sqm": float(gs_coverage_in_area.area)  # 增加转换
			}

		for res in self.results:
			uav_p = res['uav_params']
			sub_area_utm = res.get('sub_area_utm')
			path_utm = res.get('path_utm')

			sub_area_latlon_geom = None
			path_latlon_geom = None
			coverage_latlon_geom = None

			if sub_area_utm and not sub_area_utm.is_empty:
				sub_area_latlon_geom = gpd.GeoSeries([sub_area_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__

			if path_utm and not path_utm.is_empty:
				path_latlon_geom = gpd.GeoSeries([path_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__
				coverage_poly_utm = path_utm.buffer(uav_p['swath_width'] / 2, cap_style=2)
				coverage_latlon_geom = \
				gpd.GeoSeries([coverage_poly_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__

			# 创建一个确保所有值都是标准Python类型的无人机参数字典
			serializable_uav_params = {
				'id': int(uav_p['id']),
				'speed': float(uav_p['speed']),
				'flight_time': int(uav_p['flight_time']),
				'swath_width': float(uav_p['swath_width'])
			}

			summary["uav_results"].append({
				"uav_id": int(res['uav_id']),
				"uav_params": serializable_uav_params,  # 使用处理过后的字典
				"is_feasible": bool(res.get('is_feasible', False)),
				"assigned_area_sqm": float(sub_area_utm.area if sub_area_utm else 0),
				"path_length_m": float(res.get('path_length', 0)),
				"estimated_flight_time_s": float(res.get('flight_duration_needed', 0)),
				"max_flight_time_s": int(uav_p['flight_time']),
				"assigned_area_geojson": sub_area_latlon_geom,
				"flight_path_geojson": path_latlon_geom,
				"coverage_area_geojson": coverage_latlon_geom
			})
		return summary

	def get_summary_report(self) -> str:
		"""生成一份文本格式的规划总结报告。"""
		report_lines = ["=" * 50, " " * 15 + "空地协同观测规划总结报告", "=" * 50]
		if self.processed_stations and self.ground_station_coverage_utm:
			gs_coverage_in_area = self.total_area_shape_utm.intersection(self.ground_station_coverage_utm)
			report_lines.append(f"[地面站贡献 ({len(self.processed_stations)}个)]")
			for station in self.processed_stations:
				point_latlon = gpd.GeoSeries([station['geom_utm']], crs=self.utm_crs).to_crs(self.original_crs).iloc[0]
				report_lines.append(
					f"     - ID: {station['id']} | Pos (Lon, Lat): ({point_latlon.x:.4f}, {point_latlon.y:.4f}) | Radius: {station['radius_m']} m")
			report_lines.append(f"   - 总有效覆盖面积: {gs_coverage_in_area.area:.2f} m²")
			report_lines.append("-" * 50)

		report_lines.append("[无人机机队任务详情]")
		for res in self.results:
			uav = res['uav_params']
			status = "✅ 可行" if res.get('is_feasible', False) else "❌ 超出续航"
			report_lines.extend([
				f"\n     [无人机 ID: {res['uav_id']}]",
				f"      - 分配区域面积: {res.get('sub_area_utm', Polygon()).area:.2f} m²",
				f"      - 规划路径长度: {res.get('path_length', 0):.2f} m",
				f"      - 预计飞行时间: {res.get('flight_duration_needed', 0):.2f} s / {uav['flight_time']} s",
				f"      - 任务可行性: {status}"
			])

		report_lines.extend(["\n" + "=" * 50, f"最终协同总覆盖率: {self.coverage_percentage:.2f}%", "=" * 50])
		return "\n".join(report_lines)

	def execute_planning(self, n_points_per_sq_km: int = 5):
		"""
		执行完整的规划流程。

		这是调用此类的主要方法，它按顺序运行所有必要的规划步骤。
		:param n_points_per_sq_km: 用于K-Means聚类的采样点密度。
		:return: 如果规划成功完成，则返回True；如果可行性检查失败，则返回False。
		"""
		print("\n" + "#" * 20 + " 开始执行协同规划流程 " + "#" * 20)
		if not self.pre_check_feasibility():
			print("规划因可行性检查失败而终止。请调整无人机参数或更换机队。")
			return False

		self.decompose_area_and_assign(n_points_per_sq_km=n_points_per_sq_km)
		self.plan_paths_for_all()
		self.calculate_coverage()
		print("\n" + "#" * 20 + " 协同规划流程执行完毕 " + "#" * 20)
		return True


# ==============================================================================
# 4. 场景执行函数 (Scenario Execution Function)
# ==============================================================================
def run_planning_scenario(geojson_path: str, output_dir: str = "planning_results", create_map: bool = True,
                          verbose: bool = True, UAV_db_path: str = "UAV_data.db",
                          stations_db_path: str = "Stations_data.db"):
	"""
	从文件运行一个完整的规划场景。

	此函数封装了从读取输入文件到生成输出报告和地图的整个流程。
	可从其他脚本中调用此函数来执行规划。

	:param geojson_path: 目标区域的GeoJSON文件路径。
	:param output_dir: 用于存放结果文件（JSON, HTML）的目录。
	:param create_map: 如果为True，则生成并保存HTML可视化地图。
	:param verbose: 如果为True，则在控制台打印详细的总结报告。
	:param UAV_db_path: 无人机数据库文件路径。
	:param stations_db_path: 地面站数据库文件路径。
	:return: 包含规划结果的字典，如果规划失败则返回None。
	"""
	print(f"--- 启动规划场景: {geojson_path} ---")
	os.makedirs(output_dir, exist_ok=True)

	# --- 步骤 1: 动态确定任务需求 ---
	area_gdf = gpd.read_file(geojson_path)
	area_utm_crs = get_utm_crs(area_gdf)
	area_sq_km = area_gdf.to_crs(area_utm_crs).unary_union.area / 1_000_000
	print(f"目标区域面积为: {area_sq_km:.2f} 平方公里。")

	# --- 步骤 2: 动态获取无人机和地面站 ---
	print("\n--- 动态从数据库获取无人机和地面站 ---")
	uav_fleet_dict = find_drone_combination(area_sq_km, UAV_db_path)

	UAV_FLEET = []
	if uav_fleet_dict:
		for i, (uav_id, details) in enumerate(uav_fleet_dict.items()):
			UAV_FLEET.append({'id': i + 1, 'speed': details['average_speed_mps'],
			                  'flight_time': details['flight_duration_s'], 'swath_width': details['scan_width_m']})
		print(f"已成功从数据库加载并配置 {len(UAV_FLEET)} 架次无人机。")
	else:
		print("错误: 未能从数据库中获取合适的无人机组合，规划终止。")
		return None

	with open(geojson_path, 'r', encoding='utf-8') as f:
		geojson_data = json.load(f)
	all_ground_stations = find_stations_nested_dict(geojson_data, stations_db_path)

	if all_ground_stations:
		print(f"在区域内找到 {len(all_ground_stations)} 个地面站，将全部用于规划。")
	else:
		print("警告: 在目标区域内未找到地面站，将仅使用无人机进行规划。")

	# --- 步骤 3: 初始化并执行规划器 ---
	planner = CollaborativePlanner(
		geojson_path=geojson_path,
		uavs_params=UAV_FLEET,
		ground_station_params=all_ground_stations
	)

	if not planner.execute_planning():
		return None  # 可行性检查失败

	# --- 步骤 4: 生成并保存输出 ---
	results_data = planner.get_results_as_json()
	json_output_path = os.path.join(output_dir, "collaborative_planning_results.json")
	with open(json_output_path, 'w', encoding='utf-8') as f:
		json.dump(results_data, f, ensure_ascii=False, indent=4)
	print(f"\nJSON格式的结果已保存至: {json_output_path}")

	if create_map:
		map_output_path = os.path.join(output_dir, "collaborative_coverage_map.html")
		planner.visualize_plan(map_output_path)

	if verbose:
		summary_report = planner.get_summary_report()
		print("\n" + summary_report)

	return results_data


# ==============================================================================
# 5. 主执行入口 (Main Execution Entry Point)
# ==============================================================================
if __name__ == '__main__':
	# 此部分现在仅作为如何调用`run_planning_scenario`函数的示例

	# 定义输入和输出
	GEOJSON_FILE = "D:\GeoSensingAPI\geojson\Wuhan.geojson"
	OUTPUT_DIRECTORY = "planning_output_wuhan"

	# 调用核心场景函数来运行整个流程
	planning_results = run_planning_scenario(
		geojson_path=GEOJSON_FILE,
		output_dir=OUTPUT_DIRECTORY,
		create_map=True,
		verbose=False,
		UAV_db_path="D:/GeoSensingAPI/data/UAV_data.db",
		stations_db_path="D:/GeoSensingAPI/data/Stations_data.db"
	)

	if planning_results:
		print("\n规划任务成功完成。")
	# 你可以在这里继续使用 `planning_results` 字典进行后续处理
	# 例如: print(planning_results['final_collaborative_coverage_percentage'])
	else:
		print("\n规划任务失败。")