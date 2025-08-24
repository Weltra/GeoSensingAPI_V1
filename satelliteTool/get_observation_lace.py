import json

import geojson
from skyfield.api import EarthSatellite, Loader
from datetime import datetime, timedelta
import math
import os
from shapely.geometry import Point, mapping
from shapely.ops import transform
from pyproj import Proj, Transformer
from pytz import utc
from satelliteTool.find_Satellite import get_valid_satellite_tle_as_dict

def get_coverage_lace(
		tle_dict: dict,
		start_time_str: str,
		end_time_str: str,
		fov: float = 10.0,
		interval_seconds: int = 300
) -> dict:
	"""
	计算多个卫星在指定时间段内的地面覆盖轨迹，并将每个卫星的结果保存到单独的GeoJSON文件中。

	:param tle_dict: 字典，键是卫星名称(str)，值是两行的TLE字符串(str)。
	:param start_time_str: 观测开始时间的字符串 (例如 "2025-08-01 00:00:00.000")。
	:param end_time_str: 观测结束时间的字符串 (例如 "2025-08-01 23:59:59.000")。
	:param fov: 卫星的视场角 (Field of View)，单位是度。默认为 10.0。
	:param interval_seconds: 计算轨迹点的时间间隔，单位是秒。默认为 300 (5分钟)。
	:return: 字典，键为卫星名称，值为对应的GeoJSON文件路径。
	"""
	load = Loader('~/skyfield-data', verbose=False)
	ts = load.timescale()

	# --- MODIFICATION START: 定义输出目录并确保它存在 ---
	output_dir = 'geojson'
	os.makedirs(output_dir, exist_ok=True)
	satellite_paths = {}  # 用于存储返回的文件路径
	# --- MODIFICATION END ---

	for name, tle_lines_str in tle_dict.items():
		print(f"---> 正在处理卫星: {name}")
		features_for_satellite = []
		output_path = None  # 初始化路径变量

		try:
			try:
				tle_line1, tle_line2 = tle_lines_str.strip().split('\n')
			except ValueError:
				raise ValueError("TLE 格式无效，必须是包含换行符的两行字符串。")

			satellite = EarthSatellite(tle_line1.strip(), tle_line2.strip(), name, ts)

			if satellite.model.error != 0:
				raise ValueError(f"TLE数据显示轨道根数错误或已衰退: {satellite.model.error_message}")

			start_dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=utc)
			end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=utc)

			time_points = []
			current_dt = start_dt
			while current_dt <= end_dt:
				time_points.append(current_dt)
				current_dt += timedelta(seconds=interval_seconds)

			if not time_points:
				print(f"!!! 警告: '{name}' 的时间范围无效，跳过。")
				continue

			t_skyfield = ts.from_datetimes(time_points)
			geocentric = satellite.at(t_skyfield)
			subpoint = geocentric.subpoint()

			for i in range(len(time_points)):
				lon = subpoint.longitude.degrees[i]
				lat = subpoint.latitude.degrees[i]
				alt_km = subpoint.elevation.km[i]

				if alt_km <= 0:
					continue

				coverage_radius_km = alt_km * math.tan(math.radians(fov / 2))
				local_proj = Proj(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
				wgs84_proj = Proj('epsg:4326')
				to_local_transformer = Transformer.from_proj(wgs84_proj, local_proj, always_xy=True)
				from_local_transformer = Transformer.from_proj(local_proj, wgs84_proj, always_xy=True)

				center_point_local = transform(to_local_transformer.transform, Point(lon, lat))
				buffer_local = center_point_local.buffer(coverage_radius_km * 1000)
				footprint_polygon_geom = transform(from_local_transformer.transform, buffer_local)

				feature = geojson.Feature(
					geometry=mapping(footprint_polygon_geom),
					properties={"satellite": name, "timestamp": time_points[i].isoformat()}
				)
				features_for_satellite.append(feature)

		except Exception as e:
			print(f"!!! 错误: 处理 '{name}' 时失败: {e}")

		finally:
			# --- MODIFICATION START: 将结果写入文件并保存路径 ---
			# 清理卫星名称以用作文件名
			safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-')).rstrip().replace(' ', '_')
			file_name = f"{safe_name}_coverage.json"
			output_path = os.path.join(output_dir, file_name)

			# 即使处理失败，也会创建一个（可能为空的）文件
			feature_collection = geojson.FeatureCollection(features_for_satellite)
			try:
				with open(output_path, 'w', encoding='utf-8') as f:
					geojson.dump(feature_collection, f, indent=2)
				satellite_paths[name] = output_path
				if features_for_satellite:
					print(f"     ✅ 成功生成 {len(features_for_satellite)} 个足迹，已保存到: {output_path}")
			except Exception as e:
				print(f"!!! 错误: 保存文件 '{output_path}' 时失败: {e}")
				satellite_paths[name] = None  # 表示保存失败
		# --- MODIFICATION END ---

	return satellite_paths


if __name__ == '__main__':
	# --- 1. 定义包含所有卫星TLE的字典 ---
	database_file = 'D:\\GeoSensingAPI\\data\\satellite_data.db'
	tle_data_dict = get_valid_satellite_tle_as_dict(database_file)

	start_time = "2025-08-24 00:00:00.000"
	end_time = "2025-08-24 23:59:59.000"
	field_of_view = 10.0
	time_interval = 600

	print(f"--- 开始计算 {len(tle_data_dict)} 颗卫星的覆盖范围 ---")
	print(f"时间范围: {start_time} to {end_time}")

	coverage_paths_dict = get_coverage_lace(
		tle_dict=tle_data_dict,
		start_time_str=start_time,
		end_time_str=end_time,
		fov=field_of_view,
		interval_seconds=time_interval
	)

	# --- MODIFICATION START: 更新完成后的打印信息 ---
	successful_files = [p for p in coverage_paths_dict.values() if p is not None]
	print(f"\n--- 计算完成，总共为 {len(coverage_paths_dict)} 颗卫星生成了结果。 ---")
	print(f"--- 成功保存了 {len(successful_files)} 个文件到 'geojson' 目录中。 ---")

	print("\n返回的路径字典:")
	print(json.dumps(coverage_paths_dict, indent=2))