# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: UAV_GS_planner
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-13
REVISED_DATE: 2025-09-11
REVISION_NOTES:
- Fixed AttributeError by correctly calling the .union_all() method with parentheses.
"""

import logging
import math
import os
import threading

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from shapely import union_all
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, MultiPoint, MultiLineString
from shapely.ops import voronoi_diagram
from sklearn.cluster import KMeans

# --- 导入外部工具和全局配置 ---
from DeployTool.find_GS import find_stations
from DeployTool.find_UAV_combination import find_drone_combination
from config import get_geojson_path, save_geojson_file

# --- 配置 ---
os.environ['OMP_NUM_THREADS'] = '1'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_utm_crs(gdf_latlon: gpd.GeoDataFrame) -> str:
	"""根据GeoDataFrame的质心计算最合适的UTM坐标系。"""
	if gdf_latlon.empty:
		raise ValueError("输入的GeoDataFrame为空，无法确定UTM坐标系。")
	# 【已修正】调用 .union_all() 方法
	centroid = gdf_latlon.union_all().centroid
	lon, lat = centroid.x, centroid.y
	utm_band = str(int((lon + 180) // 6 + 1))
	epsg_code = '326' + utm_band.zfill(2) if lat >= 0 else '327' + utm_band.zfill(2)
	return f"EPSG:{epsg_code}"


def generate_s_path_in_polygon(polygon: (Polygon, MultiPolygon), swath_width: float) -> (object, float):
	"""在单个或多个多边形内生成S形扫描路径。"""
	if polygon.is_empty or polygon.area == 0:
		return None, 0

	try:
		if hasattr(polygon, 'geoms') and len(polygon.geoms) > 5:
			simplified_polygon = polygon.simplify(tolerance=swath_width / 10)
		elif polygon.geom_type == 'Polygon' and len(polygon.exterior.coords) > 100:
			simplified_polygon = polygon.simplify(tolerance=swath_width / 10)
		else:
			simplified_polygon = polygon
	except Exception:
		simplified_polygon = polygon

	if isinstance(simplified_polygon, MultiPolygon):
		all_path_segments = []
		total_length = 0
		for p in simplified_polygon.geoms:
			path, length = generate_s_path_in_polygon(p, swath_width)
			if path:
				geoms_to_add = list(path.geoms) if hasattr(path, 'geoms') else [path]
				all_path_segments.extend(geoms_to_add)
				total_length += length
		if not all_path_segments:
			return None, 0
		return MultiLineString(all_path_segments), total_length

	if not simplified_polygon.is_valid:
		simplified_polygon = simplified_polygon.buffer(0)
	if simplified_polygon.is_empty:
		return None, 0

	try:
		mbr = simplified_polygon.minimum_rotated_rectangle
		if mbr.is_empty:
			return None, 0

		x, y = mbr.exterior.coords.xy
		edge_lengths = (Point(x[0], y[0]).distance(Point(x[1], y[1])), Point(x[1], y[1]).distance(Point(x[2], y[2])))
		long_edge_start_pt = (Point(x[0], y[0]), Point(x[1], y[1])) if edge_lengths[0] > edge_lengths[1] else \
			(Point(x[1], y[1]), Point(x[2], y[2]))
		angle_rad = math.atan2(long_edge_start_pt[1].y - long_edge_start_pt[0].y,
		                       long_edge_start_pt[1].x - long_edge_start_pt[0].x)

		rotated_poly = gpd.GeoSeries(simplified_polygon).rotate(-math.degrees(angle_rad), origin=(0, 0)).iloc[0]
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

		return final_path, final_path.length
	except Exception as e:
		logging.warning(f"S形路径生成失败: {e}")
		return None, 0


class CollaborativePlanner:
	"""
   用于无人机（UAV）和地面站（GS）协同区域覆盖规划的类。
   """

	def __init__(self, geojson_path: str, uavs_params: list, ground_station_params: dict = None):
		logging.info("初始化协同规划器...")
		if not os.path.exists(geojson_path):
			raise FileNotFoundError(f"GeoJSON文件未找到: {geojson_path}")
		self.uavs = uavs_params
		self.num_uavs = len(uavs_params)
		self.ground_station_params = ground_station_params or {}

		self.area_gdf_latlon = gpd.read_file(geojson_path)
		self.original_crs = self.area_gdf_latlon.crs
		self.utm_crs = get_utm_crs(self.area_gdf_latlon)

		self.area_gdf_utm = self.area_gdf_latlon.to_crs(self.utm_crs)
		# 【已修正】调用 .union_all() 方法
		self.total_area_shape_utm = self.area_gdf_utm.union_all()

		self.ground_station_coverage_utm = None
		self.processed_stations = []
		self._initialize_ground_station()

		self.uav_target_area_utm = self.total_area_shape_utm.difference(
			self.ground_station_coverage_utm) if self.ground_station_coverage_utm else self.total_area_shape_utm

		self.results = []
		self.coverage_percentage = 0.0
		logging.info("规划器初始化完成。")

	def _initialize_ground_station(self):
		if not self.ground_station_params: return
		all_coverage_polygons = []
		try:
			for station_id, details in self.ground_station_params.items():
				lon, lat = details['location']['longitude'], details['location']['latitude']
				radius_m = details['observation_range_km'] * 1000
				gs_point_utm = gpd.GeoSeries([Point(lon, lat)], crs=self.original_crs).to_crs(self.utm_crs).iloc[0]
				all_coverage_polygons.append(gs_point_utm.buffer(radius_m))
				self.processed_stations.append({'id': station_id, 'geom_utm': gs_point_utm, 'radius_m': radius_m})
			if all_coverage_polygons:
				self.ground_station_coverage_utm = union_all(all_coverage_polygons)
				logging.info(f"成功处理 {len(self.processed_stations)} 个地面站。")
		except (KeyError, TypeError) as e:
			logging.error(f"处理地面站数据时出错: {e} - 请检查数据格式。")

	def pre_check_feasibility(self) -> bool:
		uav_area_needed = self.uav_target_area_utm.area
		total_max_coverage_capability = sum(
			uav['speed'] * uav['flight_time'] * uav['scan_width_m'] for uav in self.uavs)
		return total_max_coverage_capability >= uav_area_needed

	def decompose_area_and_assign(self, n_points_per_sq_km: int = 5):
		if self.uav_target_area_utm.is_empty or self.num_uavs == 0:
			self.results = [{"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": Polygon()} for uav in self.uavs]
			return

		area_sq_km = self.uav_target_area_utm.area / 1_000_000
		n_points = int(max(self.num_uavs * 20, area_sq_km * n_points_per_sq_km))

		min_x, min_y, max_x, max_y = self.uav_target_area_utm.bounds
		points_inside = []
		attempts = 0
		while len(points_inside) < n_points and attempts < n_points * 10:
			rand_points = np.random.rand(n_points - len(points_inside), 2)
			rand_points[:, 0] = rand_points[:, 0] * (max_x - min_x) + min_x
			rand_points[:, 1] = rand_points[:, 1] * (max_y - min_y) + min_y
			points_inside.extend([Point(p) for p in rand_points if self.uav_target_area_utm.contains(Point(p))])
			attempts += len(rand_points)

		if len(points_inside) < self.num_uavs:
			logging.warning("生成点不足，可能导致分配不均。")
			points_on_boundary = [self.uav_target_area_utm.exterior.interpolate(d, normalized=True) for d in
			                      np.linspace(0, 1, self.num_uavs - len(points_inside))]
			points_inside.extend(points_on_boundary)

		points_array = np.array([p.coords[0] for p in points_inside])
		kmeans = KMeans(n_clusters=self.num_uavs, random_state=42, n_init=10).fit(points_array)
		centers = MultiPoint(kmeans.cluster_centers_)
		voronoi_cells = voronoi_diagram(centers, envelope=self.uav_target_area_utm.buffer(100))

		self.results = []
		for i, center_point in enumerate(centers.geoms):
			uav = self.uavs[i]
			assigned_cell = next((cell for cell in voronoi_cells.geoms if cell.contains(center_point)), Polygon())
			sub_area_utm = self.uav_target_area_utm.intersection(assigned_cell)
			self.results.append({"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": sub_area_utm})

	def _fallback_area_assignment(self):
		if self.uav_target_area_utm.is_empty or self.num_uavs == 0:
			self.results = [{"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": Polygon()} for uav in self.uavs]
			return

		min_x, min_y, max_x, max_y = self.uav_target_area_utm.bounds
		width, height = max_x - min_x, max_y - min_y

		grid_cols = int(np.ceil(np.sqrt(self.num_uavs)))
		grid_rows = int(np.ceil(self.num_uavs / grid_cols))
		cell_width, cell_height = width / grid_cols, height / grid_rows

		self.results = []
		for i in range(self.num_uavs):
			row = i // grid_cols
			col = i % grid_cols
			uav = self.uavs[i]

			cell_min_x, cell_min_y = min_x + col * cell_width, min_y + row * cell_height
			cell_max_x, cell_max_y = cell_min_x + cell_width, cell_min_y + cell_height

			cell_polygon = Polygon.from_bounds(cell_min_x, cell_min_y, cell_max_x, cell_max_y)
			sub_area_utm = self.uav_target_area_utm.intersection(cell_polygon)
			self.results.append({"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": sub_area_utm})

	def _generate_simple_path(self, area_utm, swath_width):
		"""生成简单的直线路径作为备选方案。"""
		if area_utm.is_empty: return None, 0
		min_x, min_y, max_x, max_y = area_utm.bounds
		center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2

		horizontal_line = LineString([(min_x - 10, center_y), (max_x + 10, center_y)])
		vertical_line = LineString([(center_x, min_y - 10), (center_x, max_y + 10)])

		h_path = area_utm.intersection(horizontal_line)
		v_path = area_utm.intersection(vertical_line)

		path = h_path if h_path.length > v_path.length else v_path
		return path, path.length if not path.is_empty else 0

	def plan_paths_for_all(self):
		logging.info("开始为所有无人机规划飞行路径...")
		for result in self.results:
			uav = result['uav_params']
			sub_area_utm = result['sub_area_utm']

			if sub_area_utm.is_empty:
				result.update({'path_utm': None, 'path_length': 0, 'flight_duration_needed': 0, 'is_feasible': True})
				continue

			path_utm, path_length = None, 0
			try:
				path_info = {'path_utm': None, 'path_length': 0}

				def path_worker():
					p, l = generate_s_path_in_polygon(sub_area_utm, uav['scan_width_m'])
					path_info['path_utm'], path_info['path_length'] = p, l

				worker_thread = threading.Thread(target=path_worker)
				worker_thread.start()
				worker_thread.join(timeout=30)

				if worker_thread.is_alive() or path_info['path_utm'] is None:
					logging.warning(f"S型路径规划超时或失败(UAV ID: {uav['id']})，将采用简单路径。")
					path_utm, path_length = self._generate_simple_path(sub_area_utm, uav['scan_width_m'])
				else:
					path_utm, path_length = path_info['path_utm'], path_info['path_length']

			except Exception as e:
				logging.error(f"为无人机 {uav['id']} 规划路径时发生未知错误: {e}")
				path_utm, path_length = self._generate_simple_path(sub_area_utm, uav['scan_width_m'])

			duration = (path_length / uav['speed']) if path_length and uav['speed'] > 0 else 0
			result.update({
				'path_utm': path_utm,
				'path_length': path_length or 0,
				'flight_duration_needed': duration,
				'is_feasible': duration <= uav['flight_time']
			})
		logging.info("所有路径规划完成。")

	def calculate_coverage(self):
		logging.info("正在计算最终协同覆盖率...")
		all_coverage_polygons_utm = [self.ground_station_coverage_utm] if self.ground_station_coverage_utm else []

		for result in self.results:
			if result.get('path_utm') and not result['path_utm'].is_empty:
				uav = result['uav_params']
				try:
					buffer_polygon = result['path_utm'].buffer(uav['scan_width_m'] / 2, cap_style=2)
					all_coverage_polygons_utm.append(buffer_polygon)
				except Exception as e:
					logging.warning(f"为无人机 {uav['id']} 计算覆盖区域时失败: {e}")

		if not all_coverage_polygons_utm or self.total_area_shape_utm.area == 0:
			self.coverage_percentage = 0.0
			return

		try:
			total_coverage_union_utm = union_all(all_coverage_polygons_utm)
			effective_coverage_utm = self.total_area_shape_utm.intersection(total_coverage_union_utm)
			self.coverage_percentage = (effective_coverage_utm.area / self.total_area_shape_utm.area) * 100
		except Exception as e:
			logging.error(f"合并总覆盖区域时出错: {e}。覆盖率可能不准确。")
			approx_area = sum(p.area for p in all_coverage_polygons_utm if p)
			self.coverage_percentage = min(100.0, (approx_area / self.total_area_shape_utm.area) * 100)

		logging.info(f"计算完成，最终协同覆盖率: {self.coverage_percentage:.2f}%")

	def visualize_plan(self, output_path: str):
		logging.info("开始生成可视化地图...")
		# 【已修正】调用 .union_all() 方法
		center_latlon = self.area_gdf_latlon.union_all().centroid.coords[0][::-1]
		m = folium.Map(location=center_latlon, zoom_start=12, tiles="CartoDB positron")

		folium.GeoJson(self.area_gdf_latlon, name='总任务区域',
		               style_function=lambda x: {'color': 'black', 'weight': 2.5, 'fillOpacity': 0.05,
		                                         'fillColor': 'black'}).add_to(m)

		if self.processed_stations and self.ground_station_coverage_utm:
			gs_group = folium.FeatureGroup(name="地面站", show=True).add_to(m)
			gs_coverage_latlon = gpd.GeoSeries([self.ground_station_coverage_utm], crs=self.utm_crs).to_crs(
				self.original_crs)
			folium.GeoJson(gs_coverage_latlon, tooltip="地面站总覆盖范围",
			               style_function=lambda x: {'color': 'red', 'weight': 2, 'fillColor': 'red',
			                                         'fillOpacity': 0.3}).add_to(gs_group)
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

			if result.get('sub_area_utm') and not result['sub_area_utm'].is_empty:
				sub_area_latlon = gpd.GeoSeries([result['sub_area_utm']], crs=self.utm_crs).to_crs(self.original_crs)
				folium.GeoJson(sub_area_latlon, tooltip=f'无人机 {uav_id} 分配区域',
				               style_function=lambda x, c=color_hex: {'color': c, 'weight': 1.5, 'fillColor': c,
				                                                      'fillOpacity': 0.25}).add_to(fg)

			if result.get('path_utm') and not result['path_utm'].is_empty:
				uav = result['uav_params']
				coverage_poly_utm = result['path_utm'].buffer(uav['scan_width_m'] / 2, cap_style=2)
				path_latlon = gpd.GeoSeries([result['path_utm']], crs=self.utm_crs).to_crs(self.original_crs)
				coverage_latlon = gpd.GeoSeries([coverage_poly_utm], crs=self.utm_crs).to_crs(self.original_crs)

				folium.GeoJson(coverage_latlon, tooltip=f'无人机 {uav_id} 覆盖范围',
				               style_function=lambda x, c=color_hex: {'fillColor': c, 'fillOpacity': 0.4,
				                                                      'color': 'transparent'}).add_to(fg)
				folium.GeoJson(path_latlon, tooltip=f"无人机 {uav_id} 路径",
				               style_function=lambda x, c=color_hex: {'color': c, 'weight': 2.5}).add_to(fg)

		folium.LayerControl(collapsed=False).add_to(m)
		m.save(output_path)
		logging.info(f"可视化地图保存成功: {output_path}")

	def generate_and_save_results(self, area_name: str) -> dict:
		logging.info("正在生成并保存最终结果文件...")
		summary = {
			"area_name": area_name,
			"total_area_sqm": float(self.total_area_shape_utm.area),
			"final_collaborative_coverage_percentage": float(self.coverage_percentage),
			"ground_station_contribution": {},
			"uav_results": []
		}

		if self.processed_stations and self.ground_station_coverage_utm:
			gs_coverage_in_area = self.total_area_shape_utm.intersection(self.ground_station_coverage_utm)
			summary["ground_station_contribution"] = {
				"station_count": len(self.processed_stations),
				"total_covered_area_sqm": float(gs_coverage_in_area.area),
				"stations_details": [{
					'id': s['id'], 'radius_m': float(s['radius_m']),
					'coords_latlon':
						gpd.GeoSeries([s['geom_utm']], crs=self.utm_crs).to_crs(self.original_crs).iloc[0].coords[0]
				} for s in self.processed_stations]
			}

		for res in self.results:
			uav_id = res['uav_id']
			sub_area_utm, path_utm = res.get('sub_area_utm'), res.get('path_utm')
			sub_area_path, path_path, coverage_path = None, None, None

			if sub_area_utm and not sub_area_utm.is_empty:
				geom = gpd.GeoSeries([sub_area_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__
				filename = f"{area_name}_uav_{uav_id}_assigned_area.geojson"
				sub_area_path = save_geojson_file(filename, {"type": "Feature", "geometry": geom, "properties": {}})

			if path_utm and not path_utm.is_empty:
				path_geom = gpd.GeoSeries([path_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__
				path_filename = f"{area_name}_uav_{uav_id}_flight_path.geojson"
				path_path = save_geojson_file(path_filename,
				                              {"type": "Feature", "geometry": path_geom, "properties": {}})

				coverage_poly_utm = path_utm.buffer(res['uav_params']['scan_width_m'] / 2, cap_style=2)
				coverage_geom = gpd.GeoSeries([coverage_poly_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__
				coverage_filename = f"{area_name}_uav_{uav_id}_coverage_area.geojson"
				coverage_path = save_geojson_file(coverage_filename,
				                                  {"type": "Feature", "geometry": coverage_geom, "properties": {}})

			summary["uav_results"].append({
				"uav_id": int(uav_id), "is_feasible": bool(res.get('is_feasible', False)),
				"assigned_area_sqm": float(sub_area_utm.area if sub_area_utm else 0),
				"path_length_m": float(res.get('path_length', 0)),
				"estimated_flight_time_s": float(res.get('flight_duration_needed', 0)),
				"max_flight_time_s": int(res['uav_params']['flight_time']),
				"assigned_area_geojson_path": sub_area_path, "flight_path_geojson_path": path_path,
				"coverage_area_geojson_path": coverage_path
			})

		logging.info("结果文件生成完毕。")
		return summary

	def get_summary_report(self) -> str:
		report_lines = ["=" * 50, " " * 15 + "空地协同观测规划总结报告", "=" * 50]
		if self.processed_stations:
			gs_coverage_in_area = self.total_area_shape_utm.intersection(
				self.ground_station_coverage_utm) if self.ground_station_coverage_utm else Polygon()
			report_lines.append(f"[地面站贡献 ({len(self.processed_stations)}个)]")
			for station in self.processed_stations:
				point_latlon = gpd.GeoSeries([station['geom_utm']], crs=self.utm_crs).to_crs(self.original_crs).iloc[0]
				report_lines.append(
					f"    - ID: {station['id']} | Pos (Lon, Lat): ({point_latlon.x:.4f}, {point_latlon.y:.4f}) | Radius: {station['radius_m']} m")
			report_lines.append(f"  - 总有效覆盖面积: {gs_coverage_in_area.area:.2f} m²")
			report_lines.append("-" * 50)

		report_lines.append("[无人机机队任务详情]")
		for res in self.results:
			status = "✅ 可行" if res.get('is_feasible', False) else "❌ 超出续航"
			report_lines.extend([
				f"\n  [无人机 ID: {res['uav_id']}]",
				f"    - 分配区域面积: {res.get('sub_area_utm', Polygon()).area:.2f} m²",
				f"    - 规划路径长度: {res.get('path_length', 0):.2f} m",
				f"    - 预计飞行时间: {res.get('flight_duration_needed', 0):.2f} s / {res['uav_params']['flight_time']} s",
				f"    - 任务可行性: {status}"
			])

		report_lines.extend(["\n" + "=" * 50, f"最终协同总覆盖率: {self.coverage_percentage:.2f}%", "=" * 50])
		return "\n".join(report_lines)

	def execute_planning(self, n_points_per_sq_km: int = 5) -> bool:
		logging.info("开始执行完整规划流程...")
		if not self.pre_check_feasibility():
			logging.warning("预检查失败：无人机总覆盖能力可能不足以覆盖目标区域。")

		try:
			logging.info("执行区域分解与分配...")
			self.decompose_area_and_assign(n_points_per_sq_km=n_points_per_sq_km)
		except Exception as e:
			logging.warning(f"K-Means区域分解失败 ({e})，将使用备用网格分解法。")
			self._fallback_area_assignment()

		self.plan_paths_for_all()
		self.calculate_coverage()
		logging.info("规划流程执行完毕。")
		return True


def run_planning_scenario(geojson_path: str, UAV_db_path: str, stations_db_path: str, create_map: bool = True,
                          verbose: bool = True) -> dict:
	"""
   运行一个完整的规划场景，并将结果保存到全局目录。
   返回一个字典，包含指向最终摘要报告和地图文件的路径。
   """
	area_name = os.path.basename(geojson_path).split('.')[0]
	logging.info(f"--- 开始为区域 '{area_name}' 进行协同规划 ---")

	try:
		logging.info("步骤 1/5: 准备输入数据...")
		if not os.path.exists(geojson_path): raise FileNotFoundError(f"目标区域文件不存在: {geojson_path}")

		area_gdf = gpd.read_file(geojson_path)
		area_utm_crs = get_utm_crs(area_gdf)
		# 【已修正】调用 .union_all() 方法
		area_sq_km = area_gdf.to_crs(area_utm_crs).union_all().area / 1_000_000

		uav_fleet_dict = find_drone_combination(area_sq_km, UAV_db_path)
		if not uav_fleet_dict:
			logging.error("未能根据区域面积找到合适的无人机组合。任务终止。")
			return None

		UAV_FLEET = [{'id': i + 1, 'speed': d['average_speed_mps'], 'flight_time': d['flight_duration_s'],
		              'scan_width_m': d['scan_width_m']}
		             for i, (uid, d) in enumerate(uav_fleet_dict.items())]

		all_ground_stations = find_stations(geojson_path, stations_db_path)

		logging.info("步骤 2/5: 初始化并执行规划...")
		planner = CollaborativePlanner(geojson_path, UAV_FLEET, all_ground_stations)

		if not planner.execute_planning():
			logging.error("规划执行失败。")
			return None

		logging.info("步骤 3/5: 生成并保存结果摘要...")
		results_summary = planner.generate_and_save_results(area_name)
		summary_filename = f"{area_name}_planning_summary.json"
		summary_path = save_geojson_file(summary_filename, results_summary)
		logging.info(f"✅ 最终规划摘要已保存到: {summary_path}")

		map_path = None
		if create_map:
			logging.info("步骤 4/5: 生成可视化地图...")
			map_filename = f"{area_name}_collaborative_map.html"
			map_path = get_geojson_path(map_filename)
			planner.visualize_plan(map_path)

		if verbose:
			logging.info("步骤 5/5: 显示总结报告...")
			summary_report_text = planner.get_summary_report()
			print("\n" + summary_report_text)

		logging.info(f"--- 区域 '{area_name}' 规划成功完成 ---")
		return {"summary_json_path": summary_path, "map_html_path": map_path}

	except Exception as e:
		logging.critical(f"规划流程发生严重错误: {e}", exc_info=True)
		return None


if __name__ == '__main__':
	GEOJSON_FILE = "D:/GeoSensingAPI/data/Wuhan.geojson"
	UAV_DB = "D:/GeoSensingAPI/data/UAV_data.db"
	STATIONS_DB = "D:/GeoSensingAPI/data/Stations_data.db"

	final_result_paths = run_planning_scenario(
		geojson_path=GEOJSON_FILE,
		UAV_db_path=UAV_DB,
		stations_db_path=STATIONS_DB,
		create_map=True,
		verbose=True
	)

	if final_result_paths:
		print("\n--- 规划成功 ---")
		print(f"摘要报告JSON路径: {final_result_paths['summary_json_path']}")
		print(f"交互式地图HTML路径: {final_result_paths['map_html_path']}")
	else:
		print("\n--- 规划失败 ---")
