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
from DeployTool.find_GS import find_stations
from DeployTool.find_UAV_combination import find_drone_combination

os.environ['OMP_NUM_THREADS'] = '1'


def get_utm_crs(gdf_latlon):
	"""根据GeoDataFrame的质心计算最合适的UTM坐标系。"""
	if gdf_latlon.empty:
		raise ValueError("输入的GeoDataFrame为空，无法确定UTM坐标系。")
	centroid = gdf_latlon.unary_union.centroid
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
			simplified_polygon = polygon.simplify(tolerance=swath_width/10)
		elif polygon.geom_type == 'Polygon' and len(polygon.exterior.coords) > 100:
			simplified_polygon = polygon.simplify(tolerance=swath_width/10)
		else:
			simplified_polygon = polygon
	except Exception as e:
		simplified_polygon = polygon

	if isinstance(simplified_polygon, MultiPolygon):
		all_path_segments = []
		total_length = 0
		for p in simplified_polygon.geoms:
			path, length = generate_s_path_in_polygon(p, swath_width)
			if path:
				all_path_segments.extend(list(path.geoms))
				total_length += length
		if not all_path_segments:
			return None, 0
		return MultiLineString(all_path_segments), total_length

	try:
		if not simplified_polygon.is_valid:
			simplified_polygon = simplified_polygon.buffer(0)
		if simplified_polygon.is_empty:
			return None, 0
	except Exception as e:
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

		max_scan_lines = 1000
		scan_segments = []
		y_current = min_y + swath_width / 2
		direction = 1
		scan_line_count = 0
		
		while y_current <= max_y and scan_line_count < max_scan_lines:
			scan_line = LineString([(min_x - 1, y_current), (max_x + 1, y_current)])
			try:
				intersected = rotated_poly.intersection(scan_line)
				if not intersected.is_empty:
					geoms = list(intersected.geoms) if intersected.geom_type == 'MultiLineString' else [intersected]
					geoms.sort(key=lambda g: g.coords[0][0])
					if direction == -1:
						geoms.reverse()
					scan_segments.extend(geoms)
			except Exception as e:
				pass
			
			y_current += swath_width
			direction *= -1
			scan_line_count += 1

		if not scan_segments:
			return None, 0

		if len(scan_segments) > 500:
			step = max(1, len(scan_segments) // 500)
			scan_segments = scan_segments[::step]

		final_path_rotated = MultiLineString(scan_segments)
		final_path = gpd.GeoSeries(final_path_rotated).rotate(math.degrees(angle_rad), origin=(0, 0)).iloc[0]

		return (final_path, final_path.length) if final_path else (None, 0)
		
	except Exception as e:
		return None, 0


class CollaborativePlanner:
	"""
	一个用于无人机（UAV）和地面站（GS）协同区域覆盖规划的类。

	该类负责接收任务区域、无人机参数和地面站信息，然后执行区域分解、
	路径规划、可行性分析和覆盖率计算。
	"""

	def __init__(self, geojson_path: str, uavs_params: list, ground_station_params: dict = None):
		if not os.path.exists(geojson_path):
			raise FileNotFoundError(f"GeoJSON文件未找到: {geojson_path}")
		self.uavs = uavs_params
		self.num_uavs = len(uavs_params)
		self.ground_station_params = ground_station_params if ground_station_params else {}

		self.area_gdf_latlon = gpd.read_file(geojson_path).to_crs("EPSG:4326")
		self.original_crs = self.area_gdf_latlon.crs
		self.utm_crs = get_utm_crs(self.area_gdf_latlon)

		self.area_gdf_utm = self.area_gdf_latlon.to_crs(self.utm_crs)
		self.total_area_shape_utm = self.area_gdf_utm.unary_union

		self.ground_station_coverage_utm = None
		self.processed_stations = []
		self._initialize_ground_station()

		if self.ground_station_coverage_utm:
			self.uav_target_area_utm = self.total_area_shape_utm.difference(self.ground_station_coverage_utm)
		else:
			self.uav_target_area_utm = self.total_area_shape_utm

		self.results = []
		self.coverage_percentage = 0.0

	def _initialize_ground_station(self):
		if not self.ground_station_params:
			return
		all_coverage_polygons = []
		try:
			for station_id, details in self.ground_station_params.items():
				lon, lat = details['location']['longitude'], details['location']['latitude']
				radius_m = details['observation_range_km'] * 1000
				gs_point_utm = gpd.GeoSeries([Point(lon, lat)], crs=self.original_crs).to_crs(self.utm_crs).iloc[0]
				all_coverage_polygons.append(gs_point_utm.buffer(radius_m))
				self.processed_stations.append({'id': station_id, 'geom_utm': gs_point_utm, 'radius_m': radius_m})
		except (KeyError, TypeError) as e:
			return
		if all_coverage_polygons:
			self.ground_station_coverage_utm = unary_union(all_coverage_polygons)

	def pre_check_feasibility(self) -> bool:
		uav_area_needed = self.uav_target_area_utm.area
		total_max_coverage_capability = sum(uav['speed'] * uav['flight_time'] * uav['scan_width_m'] for uav in self.uavs)
		if total_max_coverage_capability < uav_area_needed:
			return False
		return True

	def decompose_area_and_assign(self, n_points_per_sq_km: int = 5):
		if self.uav_target_area_utm.is_empty:
			self.results = [{"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": Polygon()} for uav in self.uavs]
			return

		area_sq_km = self.uav_target_area_utm.area / 1_000_000
		max_points = min(1000, max(self.num_uavs * 20, int(area_sq_km * n_points_per_sq_km)))
		n_points = max(self.num_uavs * 10, max_points)
		
		min_x, min_y, max_x, max_y = self.uav_target_area_utm.bounds

		points_inside = []
		max_attempts = n_points * 10
		attempts = 0
		
		while len(points_inside) < n_points and attempts < max_attempts:
			batch_size = min(n_points - len(points_inside), 100)
			rand_points = np.random.rand(batch_size, 2)
			rand_points[:, 0] = rand_points[:, 0] * (max_x - min_x) + min_x
			rand_points[:, 1] = rand_points[:, 1] * (max_y - min_y) + min_y
			
			for p in rand_points:
				if len(points_inside) >= n_points:
					break
				if self.uav_target_area_utm.contains(Point(p)):
					points_inside.append(p)
			
			attempts += batch_size
		
		if len(points_inside) < self.num_uavs:
			boundary_points = []
			try:
				boundary_coords = list(self.uav_target_area_utm.exterior.coords)
				for i in range(0, len(boundary_coords), max(1, len(boundary_coords) // self.num_uavs)):
					boundary_points.append(boundary_coords[i])
				points_inside.extend(boundary_points[:self.num_uavs - len(points_inside)])
			except:
				pass

		try:
			kmeans = KMeans(
				n_clusters=self.num_uavs, 
				random_state=42, 
				n_init=5,
				max_iter=100
			).fit(np.array(points_inside))
			
			centers = MultiPoint(kmeans.cluster_centers_)
			
			voronoi_cells = voronoi_diagram(centers, envelope=self.uav_target_area_utm)

			self.results = []
			for i, center_point in enumerate(centers.geoms):
				uav = self.uavs[i]
				assigned_cell = next((cell for cell in voronoi_cells.geoms if cell.contains(center_point)), None)
				
				if assigned_cell:
					try:
						sub_area_utm = self.uav_target_area_utm.intersection(assigned_cell)
						if hasattr(sub_area_utm, 'geoms') and len(sub_area_utm.geoms) > 10:
							sub_area_utm = sub_area_utm.simplify(tolerance=1.0)
					except Exception as e:
						sub_area_utm = Polygon()
				else:
					sub_area_utm = Polygon()
				
				self.results.append({"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": sub_area_utm})
			
		except Exception as e:
			self._fallback_area_assignment()
	
	def _fallback_area_assignment(self):
		"""备用的简单区域分配方法，当K-Means失败时使用"""
		if self.uav_target_area_utm.is_empty:
			self.results = [{"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": Polygon()} for uav in self.uavs]
			return
		
		min_x, min_y, max_x, max_y = self.uav_target_area_utm.bounds
		width = max_x - min_x
		height = max_y - min_y
		
		grid_cols = int(np.ceil(np.sqrt(self.num_uavs)))
		grid_rows = int(np.ceil(self.num_uavs / grid_cols))
		
		cell_width = width / grid_cols
		cell_height = height / grid_rows
		
		self.results = []
		uav_index = 0
		
		for row in range(grid_rows):
			for col in range(grid_cols):
				if uav_index >= self.num_uavs:
					break
					
				uav = self.uavs[uav_index]
				cell_bounds = [
					min_x + col * cell_width,
					min_y + row * cell_height,
					min_x + (col + 1) * cell_width,
					min_y + (row + 1) * cell_height
				]
				
				cell_polygon = Polygon([
					(cell_bounds[0], cell_bounds[1]),
					(cell_bounds[2], cell_bounds[1]),
					(cell_bounds[2], cell_bounds[3]),
					(cell_bounds[0], cell_bounds[3])
				])
				
				try:
					sub_area_utm = self.uav_target_area_utm.intersection(cell_polygon)
				except:
					sub_area_utm = Polygon()
				
				self.results.append({"uav_id": uav['id'], "uav_params": uav, "sub_area_utm": sub_area_utm})
				uav_index += 1

	def plan_paths_for_all(self):
		for i, result in enumerate(self.results):
			uav = result['uav_params']
			sub_area_utm = result['sub_area_utm']
			
			if sub_area_utm.is_empty:
				result.update({'path_utm': None, 'path_length': 0, 'flight_duration_needed': 0, 'is_feasible': True})
				continue

			try:
				import threading
				import time
				
				path_utm = None
				path_length = 0
				timeout_occurred = False
				
				def path_planning_worker():
					nonlocal path_utm, path_length
					try:
						path_utm, path_length = generate_s_path_in_polygon(sub_area_utm, uav['scan_width_m'])
					except Exception as e:
						pass
				
				worker_thread = threading.Thread(target=path_planning_worker)
				worker_thread.daemon = True
				worker_thread.start()
				worker_thread.join(timeout=30)
				
				if worker_thread.is_alive():
					path_utm, path_length = self._generate_simple_path(sub_area_utm, uav['scan_width_m'])
				elif path_utm is None:
					path_utm, path_length = self._generate_simple_path(sub_area_utm, uav['scan_width_m'])
				
				duration = (path_length / uav['speed']) if path_length and uav['speed'] > 0 else 0

				result.update({
					'path_utm': path_utm,
					'path_length': path_length or 0,
					'flight_duration_needed': duration,
					'is_feasible': duration <= uav['flight_time']
				})
				
			except Exception as e:
				result.update({
					'path_utm': None, 'path_length': 0, 'flight_duration_needed': 0, 'is_feasible': False
				})
	
	def _generate_simple_path(self, area_utm, swath_width):
		"""生成简单的直线路径作为备选方案"""
		try:
			if area_utm.is_empty:
				return None, 0
			
			min_x, min_y, max_x, max_y = area_utm.bounds
			center_x = (min_x + max_x) / 2
			center_y = (min_y + max_y) / 2
			
			horizontal_line = LineString([(min_x - 10, center_y), (max_x + 10, center_y)])
			vertical_line = LineString([(center_x, min_y - 10), (center_x, max_y + 10)])
			
			horizontal_path = area_utm.intersection(horizontal_line)
			vertical_path = area_utm.intersection(vertical_line)
			
			paths = []
			if not horizontal_path.is_empty:
				paths.append(horizontal_path)
			if not vertical_path.is_empty:
				paths.append(vertical_path)
			
			if paths:
				combined_path = unary_union(paths)
				return combined_path, combined_path.length
			else:
				return None, 0
				
		except Exception as e:
			return None, 0

	def calculate_coverage(self):
		all_coverage_polygons_utm = [self.ground_station_coverage_utm] if self.ground_station_coverage_utm else []
		
		for i, result in enumerate(self.results):
			if result.get('path_utm') and not result['path_utm'].is_empty:
				uav = result['uav_params']
				try:
					buffer_polygon = result['path_utm'].buffer(uav['scan_width_m'] / 2, cap_style=2)
					
					if hasattr(buffer_polygon, 'geoms') and len(buffer_polygon.geoms) > 20:
						buffer_polygon = buffer_polygon.simplify(tolerance=1.0)
					elif buffer_polygon.geom_type == 'Polygon' and len(buffer_polygon.exterior.coords) > 200:
						buffer_polygon = buffer_polygon.simplify(tolerance=1.0)
					
					all_coverage_polygons_utm.append(buffer_polygon)
					
				except Exception as e:
					continue

		if not all_coverage_polygons_utm or self.total_area_shape_utm.area == 0:
			self.coverage_percentage = 0.0
			return

		try:
			if len(all_coverage_polygons_utm) > 10:
				batch_size = 5
				total_coverage_union_utm = None
				
				for i in range(0, len(all_coverage_polygons_utm), batch_size):
					batch = all_coverage_polygons_utm[i:i+batch_size]
					
					batch_union = unary_union(batch)
					if total_coverage_union_utm is None:
						total_coverage_union_utm = batch_union
					else:
						total_coverage_union_utm = total_coverage_union_utm.union(batch_union)
			else:
				total_coverage_union_utm = unary_union(all_coverage_polygons_utm)
			
			if total_coverage_union_utm.geom_type == 'Polygon' and len(total_coverage_union_utm.exterior.coords) > 500:
				total_coverage_union_utm = total_coverage_union_utm.simplify(tolerance=2.0)
			
			effective_coverage_utm = self.total_area_shape_utm.intersection(total_coverage_union_utm)
			self.coverage_percentage = (effective_coverage_utm.area / self.total_area_shape_utm.area) * 100
			
		except Exception as e:
			try:
				total_bounds_area = 0
				for poly in all_coverage_polygons_utm:
					if not poly.is_empty:
						total_bounds_area += poly.bounds[2] * poly.bounds[3] - poly.bounds[0] * poly.bounds[1]
				
				approximate_coverage = min(100.0, (total_bounds_area / self.total_area_shape_utm.area) * 100)
				self.coverage_percentage = approximate_coverage
				
			except Exception as e2:
				self.coverage_percentage = 0.0

	def visualize_plan(self, output_path: str):
		"""将规划结果可视化并保存为HTML文件。"""
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
				coverage_poly_utm = path_utm.buffer(uav['scan_width_m'] / 2, cap_style=2)
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

	def get_results_as_json(self) -> dict:
		"""将规划结果编译为结构化的字典（用于JSON序列化）。"""
		summary = {"total_area_sqm": float(self.total_area_shape_utm.area),
		           "final_collaborative_coverage_percentage": float(self.coverage_percentage),
		           "ground_station_contribution": {}, "uav_results": []}

		if self.processed_stations and self.ground_station_coverage_utm:
			gs_coverage_in_area = self.total_area_shape_utm.intersection(self.ground_station_coverage_utm)
			summary["ground_station_contribution"] = {
				"station_count": len(self.processed_stations),
				"stations_details": [{
					'id': s['id'],
					'radius_m': float(s['radius_m']),
					'coords_latlon':
						gpd.GeoSeries([s['geom_utm']], crs=self.utm_crs).to_crs(self.original_crs).iloc[0].coords[0]
				} for s in self.processed_stations],
				"total_covered_area_sqm": float(gs_coverage_in_area.area)
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
				coverage_poly_utm = path_utm.buffer(uav_p['scan_width_m'] / 2, cap_style=2)
				coverage_latlon_geom = \
				gpd.GeoSeries([coverage_poly_utm], crs=self.utm_crs).to_crs(self.original_crs).iloc[
					0].__geo_interface__

			serializable_uav_params = {
				'id': int(uav_p['id']),
				'speed': float(uav_p['speed']),
				'flight_time': int(uav_p['flight_time']),
				'scan_width_m': float(uav_p['scan_width_m'])
			}

			summary["uav_results"].append({
				"uav_id": int(res['uav_id']),
				"uav_params": serializable_uav_params,
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
		try:
			if not self.pre_check_feasibility():
				return False

			try:
				self.decompose_area_and_assign(n_points_per_sq_km=n_points_per_sq_km)
			except Exception as e:
				self._fallback_area_assignment()

			try:
				self.plan_paths_for_all()
			except Exception as e:
				pass

			try:
				self.calculate_coverage()
			except Exception as e:
				self.coverage_percentage = 0.0

			return True
			
		except Exception as e:
			return False


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
	try:
		os.makedirs(output_dir, exist_ok=True)

		try:
			area_gdf = gpd.read_file(geojson_path)
			area_utm_crs = get_utm_crs(area_gdf)
			area_sq_km = area_gdf.to_crs(area_utm_crs).unary_union.area / 1_000_000
		except Exception as e:
			return None

		try:
			uav_fleet_dict = find_drone_combination(area_sq_km, UAV_db_path)

			UAV_FLEET = []
			if uav_fleet_dict:
				for i, (uav_id, details) in enumerate(uav_fleet_dict.items()):
					UAV_FLEET.append({'id': i + 1, 'speed': details['average_speed_mps'],
					                  'flight_time': details['flight_duration_s'], 'scan_width_m': details['scan_width_m']})
			else:
				return None
		except Exception as e:
			return None

		try:
			all_ground_stations = find_stations(geojson_path, stations_db_path)
		except Exception as e:
			all_ground_stations = {}

		try:
			planner = CollaborativePlanner(
				geojson_path=geojson_path,
				uavs_params=UAV_FLEET,
				ground_station_params=all_ground_stations
			)
		except Exception as e:
			return None

		if not planner.execute_planning():
			return None

		try:
			results_data = planner.get_results_as_json()
			json_output_path = os.path.join(output_dir, "collaborative_planning_results.json")
			with open(json_output_path, 'w', encoding='utf-8') as f:
				json.dump(results_data, f, ensure_ascii=False, indent=4)
		except Exception as e:
			return None

		if create_map:
			try:
				map_output_path = os.path.join(output_dir, "collaborative_coverage_map.html")
				planner.visualize_plan(map_output_path)
			except Exception as e:
				pass

		if verbose:
			try:
				summary_report = planner.get_summary_report()
			except Exception as e:
				pass

		return results_data
		
	except Exception as e:
		return None


if __name__ == '__main__':
	GEOJSON_FILE = "D:\GeoSensingAPI\data\Wuhan.geojson"
	OUTPUT_DIRECTORY = "planning_output_wuhan"

	planning_results = run_planning_scenario(
		geojson_path=GEOJSON_FILE,
		output_dir=OUTPUT_DIRECTORY,
		create_map=True,
		verbose=False,
		UAV_db_path="D:/GeoSensingAPI/data/UAV_data.db",
		stations_db_path="D:/GeoSensingAPI/data/Stations_data.db"
	)

	if planning_results:
		pass
	else:
		pass