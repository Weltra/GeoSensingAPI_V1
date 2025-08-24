import json
import os
from pyproj import Proj, Transformer
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import unary_union, transform
from shapely.validation import make_valid
from shapely.geometry import mapping
from datetime import datetime, timedelta
from satelliteTool.get_observation_lace import get_coverage_lace


def split_antimeridian(geom):
	"""
    分割跨越180度经线（国际日期变更线）的几何图形。
    """
	if not isinstance(geom, Polygon) or geom.bounds[2] - geom.bounds[0] < 180:
		return geom

	cutter = Polygon([(-180, -90), (-180, 90), (0, 90), (0, -90), (-180, -90)])
	parts = []
	intersected = geom.intersection(cutter)
	if not intersected.is_empty:
		parts.append(intersected)

	diffed = geom.difference(cutter)
	if not diffed.is_empty:
		shifted_part = transform(lambda x, y, z=None: (x - 360, y), diffed)
		parts.append(shifted_part)

	return MultiPolygon(parts)


def get_observation_overlap(
		tle_dict: dict,
		start_time_str: str,
		end_time_str: str,
		target_geojson_path: str,
		fov: float = 10.0,
		interval_seconds: int = 300,
		output_dir: str = 'intersection_results'  # <--- MODIFICATION: 新增输出目录参数
) -> dict:
	"""
    计算卫星观测与目标区域的重叠率，并将相交足迹保存到文件后返回路径。
    """
	# 1. 调用函数获取所有卫星的覆盖足迹文件路径
	coverage_paths_dict = get_coverage_lace(
		tle_dict=tle_dict,
		start_time_str=start_time_str,
		end_time_str=end_time_str,
		fov=fov,
		interval_seconds=interval_seconds
	)

	# 2. 准备目标区域和坐标投影
	try:
		with open(target_geojson_path, 'r', encoding='utf-8') as f:
			target_geojson = json.load(f)
	except FileNotFoundError:
		print(f"错误: 目标区域GeoJSON文件未找到: {target_geojson_path}")
		return {}
	except json.JSONDecodeError:
		print(f"错误: 无法解析目标区域GeoJSON文件: {target_geojson_path}")
		return {}

	try:
		target_polygon = shape(target_geojson["features"][0]["geometry"])
		if not target_polygon.is_valid:
			target_polygon = make_valid(target_polygon)
	except (IndexError, KeyError):
		print("错误: 无效的目标区域GeoJSON格式。")
		return {}

	wgs84_proj = Proj('epsg:4326')
	equal_area_proj = Proj('+proj=moll')
	to_aea_transformer = Transformer.from_proj(wgs84_proj, equal_area_proj, always_xy=True).transform
	projected_target_geom = transform(to_aea_transformer, target_polygon)
	target_area = projected_target_geom.area

	if target_area == 0:
		return {}

	# --- MODIFICATION: 确保输出目录存在 ---
	os.makedirs(output_dir, exist_ok=True)

	# 3. 逐个卫星进行处理
	overlap_results = {}
	for satellite_name, coverage_path in coverage_paths_dict.items():
		if not coverage_path or not os.path.exists(coverage_path):
			print(f"警告: 未找到卫星 '{satellite_name}' 的覆盖文件，跳过。路径: {coverage_path}")
			continue

		try:
			with open(coverage_path, 'r', encoding='utf-8') as f:
				satellite_geojson = json.load(f)
		except Exception as e:
			print(f"错误: 无法加载或解析卫星 '{satellite_name}' 的覆盖文件 '{coverage_path}'。原因: {e}")
			continue

		if not satellite_geojson.get('features'):
			continue

		intersections = []
		intersecting_footprints_features = []

		# 4. 对每个足迹单独求交集
		for feature in satellite_geojson['features']:
			if not feature.get('geometry'): continue
			try:
				footprint_geom = shape(feature['geometry'])
				if not footprint_geom.is_valid: footprint_geom = make_valid(footprint_geom)
				footprint_geom = split_antimeridian(footprint_geom)
				if footprint_geom.is_empty: continue

				intersection = footprint_geom.intersection(target_polygon)
				if not intersection.is_empty:
					intersections.append(intersection)
					intersection_feature = {
						'type': 'Feature', 'geometry': mapping(intersection),
						'properties': {'satellite': satellite_name, 'timestamp': feature['properties']['timestamp']}
					}
					intersecting_footprints_features.append(intersection_feature)
			except Exception as e:
				print(f"跳过卫星 {satellite_name} 的一个足迹，原因: {e}")
				continue

		# 5. 合并、计算并将结果保存到文件
		if intersections:
			total_intersection_geom = unary_union(intersections)
			projected_intersection = transform(to_aea_transformer, total_intersection_geom)
			intersection_area = projected_intersection.area
			coverage_ratio = min(1.0, intersection_area / target_area)

			if coverage_ratio > 0:
				# --- MODIFICATION START: 将相交足迹写入文件并返回路径 ---
				safe_name = "".join(c for c in satellite_name if c.isalnum() or c in (' ', '-')).rstrip().replace(' ',
				                                                                                                  '_')
				output_filename = f"{safe_name}_intersection.json"
				output_path = os.path.join(output_dir, output_filename)

				intersecting_geojson_content = {
					"type": "FeatureCollection",
					"features": intersecting_footprints_features
				}
				with open(output_path, 'w', encoding='utf-8') as f:
					json.dump(intersecting_geojson_content, f, indent=2, ensure_ascii=False)

				overlap_results[satellite_name] = {
					'coverage_ratio': coverage_ratio,
					'intersection_footprints_path': output_path
				}
		# --- MODIFICATION END ---
	return overlap_results


if __name__ == '__main__':
	tle_data_dict = {
		"GAOFEN 1-03": "1 43260U 18031B   25225.93764942  .00000729  00000-0  11133-3 0  9998\n2 43260  97.7673 284.6950 0004656 311.5203  48.5607 14.76597261397351",
		"SENTINEL 2A": "1 40697U 15028A   25225.66220237  .00000108  00000-0  57680-4 0  9995\n2 40697  98.5664 299.9242 0001176  96.3963 263.7354 14.30826489529757",
		"LANDSAT 9": "1 49260U 21088A   25225.90087331  .00000343  00000-0  86120-4 0  9998\n2 49260  98.2240 295.6621 0001152  92.7233 267.4097 14.57102349206250",
	}

	wuhan_geojson_path = 'wuhan_target.json'
	wuhan_target_content = {
		"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
			"type": "Polygon",
			"coordinates": [[[114.0, 30.0], [114.8, 30.0], [114.8, 30.8], [114.0, 30.8], [114.0, 30.0]]]
		}}]
	}
	with open(wuhan_geojson_path, 'w', encoding='utf-8') as f:
		json.dump(wuhan_target_content, f)

	start_time = "2025-08-24 00:00:00.000"
	end_time = "2025-08-24 01:00:00.000"
	field_of_view = 45.0
	time_interval = 600
	intersection_output_dir = 'intersection_results'  # 指定重叠结果的输出目录

	print("--- 开始计算卫星观测重叠率 ---")
	print(f"--- 卫星覆盖范围文件将生成在 'geojson' 目录 ---")
	print(f"--- 目标区域文件: {wuhan_geojson_path} ---")
	print(f"--- 重叠结果文件将生成在 '{intersection_output_dir}' 目录 ---")

	overlap_results = get_observation_overlap(
		tle_dict=tle_data_dict,
		start_time_str=start_time,
		end_time_str=end_time,
		target_geojson_path=wuhan_geojson_path,
		fov=field_of_view,
		interval_seconds=time_interval,
		output_dir=intersection_output_dir
	)

	print("\n" + "=" * 50)
	print("--- 计算结果 ---")
	if overlap_results:
		for satellite, data in overlap_results.items():
			coverage = data['coverage_ratio']
			# --- MODIFICATION: 打印文件路径而不是足迹数量 ---
			footprint_path = data['intersection_footprints_path']
			print(f"  - 卫星: {satellite:<15} | 覆盖率: {coverage:>7.2%} | 结果文件: {footprint_path}")

		print(f"\n✅ 重叠结果文件已在计算过程中生成于 '{intersection_output_dir}' 目录。")
	else:
		print("  在指定时间段内，没有卫星覆盖目标区域。")
	print("=" * 50)