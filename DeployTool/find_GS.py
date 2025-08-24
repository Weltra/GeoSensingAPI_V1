# -*- coding: utf-8 -*-
import sqlite3
import json
from shapely.geometry import Point, shape


def find_stations(geojson_path: str, db_path: str) -> dict:
	"""
    在GeoJSON文件定义的区域内查找地面站，并返回一个嵌套字典。

    Args:
        geojson_path (str): 一个包含观测区域多边形的标准GeoJSON文件的路径。
        db_path (str): 地面站数据库文件路径。

    Returns:
        一个以 wigos_id 为键的字典。每个值是包含该站点详细信息的
        另一个字典，其中的地理位置信息也由字典构成。
        例如: {'station_id': {'location': {'longitude': lon, 'latitude': lat}, ...}}
        如果找不到站点或发生错误，则返回一个空字典。
    """
	try:
		# 从文件路径加载GeoJSON数据
		with open(geojson_path, 'r', encoding='utf-8') as f:
			geojson_area = json.load(f)

		# 从加载的GeoJSON字典中提取几何形状
		if geojson_area.get('type') == 'FeatureCollection':
			search_polygon = shape(geojson_area['features'][0]['geometry'])
		elif geojson_area.get('type') == 'Feature':
			search_polygon = shape(geojson_area['geometry'])
		elif 'coordinates' in geojson_area:
			search_polygon = shape(geojson_area)
		else:
			raise ValueError("不正确的GeoJSON格式：缺少'features'或'geometry'键。")

	except FileNotFoundError:
		raise FileNotFoundError(f"错误：找不到GeoJSON文件路径 '{geojson_path}'")
	except json.JSONDecodeError:
		raise ValueError(f"错误：无法解析GeoJSON文件 '{geojson_path}'，请检查文件格式。")
	except (IndexError, KeyError, TypeError) as e:
		raise ValueError(f"解析GeoJSON时出错: {e}")

	stations_nested = {}
	conn = None

	try:
		conn = sqlite3.connect(db_path)
		cursor = conn.cursor()
		query = "SELECT wigos_id, longitude, latitude, observation_range_km FROM station_observations"
		cursor.execute(query)
		all_stations = cursor.fetchall()

		for wigos_id, lon, lat, range_km in all_stations:
			if lon is not None and lat is not None:
				if search_polygon.contains(Point(lon, lat)):
					# 构建完全嵌套的字典结构
					station_details = {
						"location": {
							"longitude": lon,
							"latitude": lat
						},
						"observation_range_km": range_km
					}
					stations_nested[wigos_id] = station_details

	except sqlite3.Error as e:
		print(f"数据库查询时发生错误: {e}")
		return {}
	finally:
		if conn:
			conn.close()

	return stations_nested


# --- 使用示例 ---
if __name__ == '__main__':
	# 1. 定义武汉区域的GeoJSON数据

	# 3. 调用修改后的函数，传入文件路径
	print("\n--- 开始查询 ---")
	found_stations_nested = find_stations(geojson_path="D:\GeoSensingAPI\data\Wuhan.geojson", db_path="D:\GeoSensingAPI\data\Stations_data.db")

	if found_stations_nested:
		print(f"在指定区域内找到了 {len(found_stations_nested)} 个地面站:")

		# 遍历并展示如何访问嵌套的数据
		print("\n遍历并访问嵌套字典中的数据:")
		for station_id, details in found_stations_nested.items():
			# 访问经纬度
			longitude = details['location']['longitude']
			latitude = details['location']['latitude']
			# 访问观测范围
			obs_range = details['observation_range_km']

			print(f"  ID: {station_id}")
			print(f"    - Longitude: {longitude}")
			print(f"    - Latitude: {latitude}")
			print(f"    - Range (km): {obs_range}")

		# 打印其中一个站点的完整结构以供参考
		first_station_id = list(found_stations_nested.keys())[0]
		print(f"\n站点 '{first_station_id}' 的完整嵌套字典结构:")
		print(json.dumps(found_stations_nested[first_station_id], indent=4))

	else:
		print("在指定区域内没有找到任何地面站。")
