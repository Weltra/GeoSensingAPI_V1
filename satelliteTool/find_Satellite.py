# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: find_Satellite
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-21 (Modified on 2025-08-22)
"""

import sqlite3


def get_valid_satellite_tle_as_dict(satellite_db_path, mission_theme=None, min_swath_width=None, max_resolution=None,
                                    sensor_type=None, spectral_range=None, satellite_name=None):
	"""
	查询指定的SQLite数据库文件，并返回一个包含卫星名称及其有效TLE的字典。
	此函数允许根据任务主题、最小扫描宽度、最大分辨率、传感器类型、光谱范围和卫星名称进行筛选。
	如果未提供任何筛选条件，则返回所有TLE不为空的卫星。

	Args:
		satellite_db_path (str): SQLite数据库文件的路径。
		mission_theme (str, optional): 任务主题关键词。将在任务目标描述中进行模糊搜索。默认为 None。
		min_swath_width (float, optional): 最小扫描宽度（公里）。将返回大于或等于此值的卫星。默认为 None。
		max_resolution (float, optional): 最大分辨率（米）。注意：数值越小代表分辨率越高。将返回小于或等于此值的卫星。默认为 None。
		sensor_type (str, optional): 传感器的具体类型, 例如 'Optical Sensor'。默认为 None。
		spectral_range (str, optional): 光谱范围的关键词，将进行模糊搜索。默认为 None。
		satellite_name (str, optional): 卫星的名称，将进行模糊搜索。默认为 None。

	Returns:
		dict: 一个以卫星名称为键，TLE为值的字典。
	"""
	conn = sqlite3.connect(satellite_db_path)
	cursor = conn.cursor()

	# --- 动态构建SQL查询 ---
	# 基础查询语句
	base_query = "SELECT satellite_name, TLE FROM satellites WHERE TLE IS NOT NULL AND TLE != ''"

	# 用于存放筛选条件的列表
	conditions = []
	# 用于存放查询参数的列表，防止SQL注入
	params = []

	# 1. 根据“任务主题”添加筛选条件
	if mission_theme:
		conditions.append("primary_mission_objectives LIKE ?")
		params.append(f'%{mission_theme}%')

	# 2. 根据“最小扫描宽度”添加筛选条件
	if min_swath_width is not None:
		conditions.append("swatch_width >= ?")
		params.append(min_swath_width)

	# 3. 根据“最大分辨率”添加筛选条件 (注意是 <=)
	if max_resolution is not None:
		conditions.append("best_resolution <= ?")
		params.append(max_resolution)

	# 4. 根据“传感器类型”添加筛选条件
	if sensor_type:
		conditions.append("type_of_sensor = ?")
		params.append(sensor_type)

	# 5. 根据“光谱范围”添加筛选条件 (新增)
	if spectral_range:
		conditions.append("spectral_type LIKE ?")
		params.append(f'%{spectral_range}%')

	# 6. 根据“卫星名称”添加筛选条件 (新增)
	if satellite_name:
		conditions.append("satellite_name LIKE ?")
		params.append(f'%{satellite_name}%')

	# 如果有筛选条件，则将其加入到基础查询语句中
	if conditions:
		final_query = base_query + " AND " + " AND ".join(conditions)
	else:
		final_query = base_query

	# --- 执行查询 ---
	cursor.execute(final_query, params)
	rows = cursor.fetchall()
	conn.close()

	# 将查询结果组织成字典
	satellite_tle_dict = {row[0]: row[1] for row in rows}
	return satellite_tle_dict


# --- 主程序入口和使用示例 ---
if __name__ == '__main__':
	database_file = 'D:\GeoSensingAPI\data\satellite_data.db'  # 请确保路径正确

	# 示例1: 无筛选条件，返回所有卫星 (原始功能)
	print("--- 示例1: 查询所有拥有有效TLE的卫星 ---")
	all_tle_data = get_valid_satellite_tle_as_dict(database_file)
	print(f"从 '{database_file}' 中总共查询到 {len(all_tle_data)} 颗拥有有效TLE的卫星。")

	# 示例2: 按最小扫描宽度查询
	print("\n--- 示例2: 查询扫描宽度 >= 500公里 的卫星 ---")
	wide_swath_sats = get_valid_satellite_tle_as_dict(satellite_db_path=database_file, min_swath_width=500)
	print(f"查询到 {len(wide_swath_sats)} 颗扫描宽度 >= 500km 的卫星。")
	# 打印前5个结果
	for i, satellite in enumerate(wide_swath_sats.keys()):
		if i >= 5: break
		print(f"- {satellite}")

	# 示例3: 按任务主题和传感器类型查询
	print("\n--- 示例3: 查询任务主题包含 'Land cover' 且为光学传感器的卫星 ---")
	land_cover_sats = get_valid_satellite_tle_as_dict(satellite_db_path=database_file,
	                                                  mission_theme='Land cover',
	                                                  sensor_type='Optical Sensor')
	print(f"查询到 {len(land_cover_sats)} 颗满足条件的卫星。")
	for i, satellite in enumerate(land_cover_sats.keys()):
		if i >= 5:
			break
		print(f"- {satellite}")

	# 示例4: 按最大分辨率查询
	print("\n--- 示例4: 查询分辨率优于1米 (<= 1.0) 的卫星 ---")
	high_res_sats = get_valid_satellite_tle_as_dict(satellite_db_path=database_file, max_resolution=1.0)
	print(f"查询到 {len(high_res_sats)} 颗分辨率优于1米的卫星。")
	for i, satellite in enumerate(high_res_sats.keys()):
		if i >= 5:
			break
		print(f"- {satellite}")

	# 示例5: 按卫星名称查询
	print("\n--- 示例5: 查询名称中包含 'Fengyun' 的卫星 ---")
	fengyun_sats = get_valid_satellite_tle_as_dict(satellite_db_path=database_file, satellite_name='Fengyun')
	print(f"查询到 {len(fengyun_sats)} 颗名称中带 'Fengyun' 的卫星。")
	for i, satellite in enumerate(fengyun_sats.keys()):
		if i >= 5:
			break
		print(f"- {satellite}")

	# 示例6: 按光谱范围查询
	print("\n--- 示例6: 查询光谱范围包含 'blue' 的卫星 ---")
	x_band_sats = get_valid_satellite_tle_as_dict(satellite_db_path=database_file, spectral_range='blue')
	print(f"查询到 {len(x_band_sats)} 颗光谱范围包含 'blue' 的卫星。")
	for i, satellite in enumerate(x_band_sats.keys()):
		if i >= 5:
			break
		print(f"- {satellite}")