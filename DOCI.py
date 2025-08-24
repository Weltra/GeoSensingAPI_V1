# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: DOCI
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-23
REVISION_NOTES: 重构为从外部数据库和场景文件读取数据。
                修改 calculate_doci_from_database 函数，使其返回JSON而不是打印。
                新增逻辑，只返回得分大于0的结果。
                修改函数签名，直接接收场景配置字典。
                修改GeoJSON加载方式，从路径读取。
                修改主程序测试块，使用明文（字典）输入代替文件加载。
"""

import json
import numpy as np
import sqlite3
import pandas as pd
from typing import Dict, Any


# 假设 satelliteTool 已安装或在PYTHONPATH中
from satelliteTool.get_observation_overlap import get_observation_overlap

# =============================================================================
# PART 1: DOCI SUB-CAPABILITIES FRAMEWORK
# =============================================================================

def get_theme_relevance_from_oscar(sensor_name, task_theme, mission_themes_str):
	"""根据数据库中的任务主题模拟查询相关性。"""
	try:
		# 确保正确处理可能存在的None或非字符串类型
		if not isinstance(mission_themes_str, str):
			return 'medium'
		themes = json.loads(mission_themes_str.replace("'", "\""))
		if any(task_theme.lower() in t.lower() for t in themes):
			return 'high'
		else:
			return 'medium'
	except (json.JSONDecodeError, TypeError):
		return 'medium'  # 默认值


def calculate_theme(relevance):
	theme_map = {'primary': 1.0, 'high': 0.8, 'medium': 0.6, 'useful': 0.4, 'marginal': 0.2}
	return theme_map.get(relevance.lower(), 0.0)


def calculate_radiation(cloudiness):
	return 1.0 - cloudiness


def calculate_accuracy(sensor_quantization, max_quantization):
	if max_quantization == 0: return 0
	return sensor_quantization / max_quantization


def calculate_spacetime(sensor_attrs, task_reqs, weights):
	indicators = ['spatial_res', 'temporal_res']
	grades = np.array([1.0, 0.5, 0.1])
	R = np.zeros((2, 3))
	for i, indicator in enumerate(indicators):
		x = sensor_attrs[indicator]
		t, b, g = task_reqs[indicator]
		is_inverse = "res" in indicator
		_x, _t, _b, _g = (-x, -t, -b, -g) if is_inverse else (x, t, b, g)
		if _x >= _g:
			mu1 = 1.0
		elif _g > _x >= _b:
			mu1 = (_x - _b) / (_g - _b)
		else:
			mu1 = 0.0
		if _b > _x >= _t:
			mu2 = (_x - _t) / (_b - _t)
		elif _g > _x >= _b:
			mu2 = (_g - _x) / (_g - _b)
		else:
			mu2 = 0.0
		if _x < _t:
			mu3 = 1.0
		elif _b > _x >= _t:
			mu3 = (_b - _x) / (_b - _t)
		else:
			mu3 = 0.0
		R[i, :] = [mu1, mu2, mu3]
	W = np.array(weights)
	B = W @ R
	space_time_value = np.sum(B * grades)
	return space_time_value


# =============================================================================
# PART 2: MAIN DOCI CALCULATION ORCHESTRATOR
# =============================================================================
def calculate_doci_for_task(sensor_properties: Dict, task_requirements: Dict, all_sensors: Dict) -> Dict:
	"""为单个传感器和单个任务计算完整的DOCI及其所有子能力。"""
	name = sensor_properties['name']

	tle_dict = {name: sensor_properties['tle_str']}

	overlap_results = get_observation_overlap(
		tle_dict=tle_dict,
		start_time_str=task_requirements['start_time'],
		end_time_str=task_requirements['end_time'],
		target_geojson_path=task_requirements['geojson_path'],
		fov=sensor_properties['fov'],
		interval_seconds=600
	)

	Co = overlap_results.get(name, {}).get('coverage_ratio', 0.0)

	relevance = get_theme_relevance_from_oscar(name, task_requirements['theme'],
	                                           sensor_properties.get('mission_themes', ''))
	Th = calculate_theme(relevance)

	cloudiness = task_requirements['cloudiness_forecast']
	Ra = calculate_radiation(cloudiness)

	if Co <= 0 or Th == 0 or Ra == 0:
		return {'Co': Co, 'Th': Th, 'Ra': Ra, 'ST': 0, 'Ac': 0, 'DOCI': 0}

	ST = calculate_spacetime(sensor_properties, task_requirements['requirements'], task_requirements['ahp_weights'])

	max_q = max(s['quantization_level'] for s in all_sensors.values() if 'quantization_level' in s) if all_sensors else \
		sensor_properties['quantization_level']
	Ac = calculate_accuracy(sensor_properties['quantization_level'], max_q)

	doci_value = 0.25 * ((Co + ST) + (Th + Ra) * Ac)
	results = {'Co': Co, 'Th': Th, 'Ra': Ra, 'ST': ST, 'Ac': Ac, 'DOCI': doci_value}
	return results


def calculate_doci_for_all_sensors(sensors_data, task_requirements):
	"""为所有传感器计算DOCI值"""
	results = {}
	for sensor_name, sensor_props in sensors_data.items():
		try:
			result = calculate_doci_for_task(sensor_props, task_requirements, sensors_data)
			results[sensor_name] = result
		except Exception as e:
			print(f"计算传感器 '{sensor_name}' 的DOCI时出错: {e}")
			results[sensor_name] = {'Co': 0, 'Th': 0, 'Ra': 0, 'ST': 0, 'Ac': 0, 'DOCI': 0}
	return results


# =============================================================================
# PART 3: MAIN EXECUTION
# =============================================================================

def calculate_doci_from_database(db_path: str, scenario_config: dict) -> str:
	"""
	从数据库加载数据，根据传入的场景配置执行DOCI评估，并以JSON格式返回结果。
	"""
	try:
		# 1. 直接使用传入的场景配置字典
		doci_config = scenario_config['models']['doci']

		# 从文件路径加载GeoJSON
		geojson_path = scenario_config['target_area_geojson_path']

		task_reqs = {
			'description': scenario_config['description'],
			'theme': doci_config['theme'],
			'start_time': scenario_config['time_window']['start'],
			'end_time': scenario_config['time_window']['end'],
			'geojson_path': geojson_path,  # 使用加载的GeoJSON数据
			'cloudiness_forecast': scenario_config['environment']['cloudiness_forecast'],
			'requirements': doci_config['requirements'],
			'ahp_weights': doci_config['ahp_weights']
		}

		# 2. 从数据库查询传感器数据
		con = sqlite3.connect(db_path)
		df_sensors = pd.read_sql_query(
			"SELECT name, tle, spatial_resolution_m, temporal_resolution_days, quantization_bits, fov_deg, mission_themes FROM sensors",
			con)
		con.close()

		df_sensors.dropna(subset=['tle', 'quantization_bits', 'fov_deg'], inplace=True)

		sensors_data = {}
		for _, row in df_sensors.iterrows():
			sensors_data[row['name']] = {
				'name': row['name'],
				'tle_str': row['tle'],
				'spatial_res': row['spatial_resolution_m'],
				'temporal_res': row['temporal_resolution_days'],
				'quantization_level': row['quantization_bits'],
				'fov': row['fov_deg'],
				'mission_themes': row['mission_themes']
			}

		# 3. 执行计算
		results = calculate_doci_for_all_sensors(sensors_data, task_reqs)

		# 4. 排序并格式化为JSON
		if not results:
			raise ValueError("未能计算出任何有效结果。")

		sorted_results = sorted(results.items(), key=lambda x: x[1]['DOCI'], reverse=True)

		# 5. 过滤并重新排名
		positive_results = [item for item in sorted_results if item[1]["DOCI"] > 0]

		ranked_sensors = []
		for rank, (sensor_name, result) in enumerate(positive_results):
			result_data = {
				"rank": rank + 1,
				"name": sensor_name,
				"components": result
			}
			ranked_sensors.append(result_data)

		result_json = {
			"status": "success",
			"scenario": scenario_config.get('description', 'Custom Scenario'),
			"model": "DOCI",
			"description": doci_config.get('description', ''),
			"results": ranked_sensors
		}
		return json.dumps(result_json, indent=4, ensure_ascii=False)

	except Exception as e:
		error_json = {
			"status": "error",
			"scenario": scenario_config.get('description', 'Custom Scenario'),
			"model": "DOCI",
			"message": str(e)
		}
		return json.dumps(error_json, indent=4, ensure_ascii=False)


if __name__ == '__main__':
	# --- 主程序测试块 ---
	db_file_path = "D:\\GeoSensingAPI\\data\\sensors_enriched.db"

	# 直接在此处定义场景配置字典
	doci_scenario_config = {
		"description": "针对武汉市汛期灾害的遥感监测需求，重点评估传感器的水体识别与覆盖能力。",
		"time_window": {
			"start": "2025-08-01 00:00:00.000",
			"end": "2025-08-01 23:59:59.000"
		},
		"target_area_geojson_path": "D:\\GeoSensingAPI\\data\\Wuhan.geojson",
		"environment": {
			"cloudiness_forecast": 0.45
		},
		"models": {
			"doci": {
				"description": "DOCI模型侧重于时空覆盖、主题相关性、辐射质量和精度。",
				"theme": "Disaster Monitoring",
				"requirements": {
					"spatial_res": [50, 20, 5],
					"temporal_res": [5, 2, 1]
				},
				"ahp_weights": [0.7, 0.3]
			}
		}
	}

	json_output = calculate_doci_from_database(db_path=db_file_path,
	                                           scenario_config=doci_scenario_config)
	print(json_output)