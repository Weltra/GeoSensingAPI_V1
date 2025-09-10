# query_utils.py

import sqlite3
import pandas as pd
from typing import Dict, Any


def query_sensors(db_path: str, sensor_name: str = None, mission_theme: str = None, sensor_type: str = None) -> Dict[
	str, Dict]:
	"""
	一个通用的、支持多种条件过滤的传感器数据查询函数。
	函数总是返回所有模型可能需要的全部参数列。

	:param db_path: SQLite数据库文件的路径。
	:param sensor_name: (可选) 传感器/卫星的名称，将进行模糊搜索。
	:param mission_theme: (可选) 任务主题关键词，将在 mission_themes 字段中进行模糊搜索。
	:param sensor_type: (可选) 传感器的具体类型, 例如 'Optical Sensor'。
	:return: 一个以传感器名称为键，包含其所有参数的字典为值的嵌套字典。
	"""
	# 定义所有模型可能需要的列的超集
	ALL_COLUMNS = [
		'name', 'type', 'tle', 'spatial_resolution_m', 'swath_width_km', 'fov_deg',
		'temporal_resolution_days', 'quantization_bits', 'snr', 'band_count',
		'data_rate_mbps', 'design_life_yrs', 'polarization', 'mission_themes'
	]

	columns_str = ", ".join(f'"{c}"' for c in ALL_COLUMNS)
	base_query = f"SELECT {columns_str} FROM sensors"

	conditions = []
	params = []

	if sensor_name:
		conditions.append("name LIKE ?")
		params.append(f'%{sensor_name}%')

	if mission_theme:
		conditions.append("mission_themes LIKE ?")
		params.append(f'%{mission_theme}%')

	if sensor_type:
		conditions.append("type = ?")
		params.append(sensor_type)

	if conditions:
		final_query = base_query + " WHERE " + " AND ".join(conditions)
	else:
		final_query = base_query

	try:
		con = sqlite3.connect(db_path)
		df_sensors = pd.read_sql_query(final_query, con, params=params)
		con.close()

		# 关键修复：移除重复的传感器名称，只保留第一个出现的条目
		df_sensors.drop_duplicates(subset=['name'], keep='first', inplace=True)

		# 移除任何在核心参数列中包含空值的行
		core_cols = ['name', 'tle', 'type', 'spatial_resolution_m', 'temporal_resolution_days', 'quantization_bits']
		df_sensors.dropna(subset=core_cols, inplace=True)

		if df_sensors.empty:
			return {}

		df_sensors.set_index('name', inplace=True)
		return df_sensors.to_dict('index')

	except Exception as e:
		print(f"数据库查询失败: {e}")
		return {}


if __name__ == '__main__':
	db_file = 'D:\\GeoSensingAPI\\data\\sensors_enriched.db'

	print("--- 示例1: 无筛选条件，返回所有传感器 ---")
	all_data = query_sensors(db_path=db_file)
	print(f"成功查询到 {len(all_data)} 条数据。")
	if all_data:
		print("第一条数据示例:", list(all_data.keys())[0])

	print("\n--- 示例2: 按任务主题 'Land cover' 查询 ---")
	land_cover_data = query_sensors(db_path=db_file, mission_theme='Land cover')
	print(f"成功查询到 {len(land_cover_data)} 条 'Land cover' 相关数据。")
	if land_cover_data:
		print("返回的传感器:", list(land_cover_data.keys()))

	print("\n--- 示例3: 按传感器类型 'Microwave Sensor' 查询 ---")
	microwave_data = query_sensors(db_path=db_file, sensor_type='Microwave Sensor')
	print(f"成功查询到 {len(microwave_data)} 条 'Microwave Sensor' 类型数据。")
	if microwave_data:
		print("返回的传感器:", list(microwave_data.keys())[:5])  # 打印前5个

	print("\n--- 示例4: 按名称 'Scatterometer' 查询 ---")
	scatterometer_data = query_sensors(db_path=db_file, sensor_name='Scatterometer')
	print(f"成功查询到 {len(scatterometer_data)} 条名称中包含 'Scatterometer' 的数据。")
	if scatterometer_data:
		print("返回的传感器:", list(scatterometer_data.keys()))