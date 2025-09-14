# DOCI.py

import json
import numpy as np
from typing import Dict
from EvaluationTool.query_sensors import query_sensors
from satelliteTool.get_observation_overlap import get_observation_overlap


def get_theme_relevance_from_oscar(sensor_name, task_theme, mission_themes_str):
	"""根据数据库中的任务主题模拟查询相关性。"""
	try:
		if not isinstance(mission_themes_str, str): return 'medium'
		themes = json.loads(mission_themes_str.replace("'", "\""))
		if any(task_theme.lower() in t.lower() for t in themes):
			return 'high'
		else:
			return 'medium'
	except (json.JSONDecodeError, TypeError):
		return 'medium'


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
	return np.sum(B * grades)


def calculate_doci_for_task(sensor_properties: Dict, task_requirements: Dict, all_sensors: Dict) -> Dict:
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
	Ra = calculate_radiation(task_requirements['cloudiness_forecast'])
	if Co <= 0 or Th == 0 or Ra == 0:
		return {'Co': Co, 'Th': Th, 'Ra': Ra, 'ST': 0, 'Ac': 0, 'DOCI': 0}
	ST = calculate_spacetime(sensor_properties, task_requirements['requirements'], task_requirements['ahp_weights'])
	all_quantization_levels = [s['quantization_level'] for s in all_sensors.values() if
	                           s.get('quantization_level') is not None]
	max_q = max(all_quantization_levels) if all_quantization_levels else sensor_properties['quantization_level']
	Ac = calculate_accuracy(sensor_properties['quantization_level'], max_q)
	doci_value = 0.25 * ((Co + ST) + (Th + Ra) * Ac)
	return {'Co': Co, 'Th': Th, 'Ra': Ra, 'ST': ST, 'Ac': Ac, 'DOCI': doci_value}


def calculate_doci_for_all_sensors(sensors_data, task_requirements):
	results = {}
	for sensor_name, sensor_props in sensors_data.items():
		try:
			results[sensor_name] = calculate_doci_for_task(sensor_props, task_requirements, sensors_data)
		except Exception as e:
			print(f"计算传感器 '{sensor_name}' 的DOCI时出错: {e}")
			results[sensor_name] = {'Co': 0, 'Th': 0, 'Ra': 0, 'ST': 0, 'Ac': 0, 'DOCI': 0}
	return results


def calculate_doci(sensors_data: dict, scenario_config: dict) -> str:
	"""
	根据传入的传感器数据字典和场景配置执行DOCI评估。
	"""
	try:
		doci_config = scenario_config['models']['doci']
		task_reqs = {
			'start_time': scenario_config['time_window']['start'],
			'end_time': scenario_config['time_window']['end'],
			'geojson_path': scenario_config['target_area_geojson_path'],
			'cloudiness_forecast': scenario_config['environment']['cloudiness_forecast'],
			'theme': doci_config['theme'], 'requirements': doci_config['requirements'],
			'ahp_weights': doci_config['ahp_weights']
		}

		sensors_data_formatted = {}
		for name, params in sensors_data.items():
			# 确保所有需要的键都存在，否则跳过此传感器
			required_keys = ['tle', 'spatial_resolution_m', 'temporal_resolution_days', 'quantization_bits', 'fov_deg',
			                 'mission_themes']
			if not all(key in params and params[key] is not None for key in required_keys):
				continue
			sensors_data_formatted[name] = {
				'name': name, 'tle_str': params['tle'], 'spatial_res': params['spatial_resolution_m'],
				'temporal_res': params['temporal_resolution_days'], 'quantization_level': params['quantization_bits'],
				'fov': params['fov_deg'], 'mission_themes': params['mission_themes']
			}

		results = calculate_doci_for_all_sensors(sensors_data_formatted, task_reqs)
		sorted_results = sorted(results.items(), key=lambda x: x[1]['DOCI'], reverse=True)
		positive_results = [item for item in sorted_results if item[1]["DOCI"] > 0]

		ranked_sensors = [{"rank": r + 1, "name": name, "components": res} for r, (name, res) in
		                  enumerate(positive_results)]

		return json.dumps({
			"status": "success", "scenario": scenario_config.get('description'), "model": "DOCI",
			"description": doci_config.get('description', ''), "results": ranked_sensors
		}, indent=4, ensure_ascii=False)

	except Exception as e:
		return json.dumps({"status": "error", "model": "DOCI", "message": str(e)}, indent=4, ensure_ascii=False)


if __name__ == '__main__':
	db_file_path = "D:\\GeoSensingAPI\\data\\sensors_enriched.db"
	doci_scenario_config = {
		"description": "DOCI评估", "time_window": {"start": "2025-08-1 00:00:00.000", "end": "2025-08-1 23:59:59.000"},
		"target_area_geojson_path": "D:\\GeoSensingAPI\\data\\Wuhan.geojson",
		"environment": {"cloudiness_forecast": 0.45},
		"models": {"doci": {
			"description": "DOCI模型", "theme": "Disaster Monitoring",
			"requirements": {"spatial_res": [50, 20, 5], "temporal_res": [5, 2, 1]},
			"ahp_weights": [0.7, 0.3]
		}}
	}

	print("--- 步骤1: 使用通用查询函数按任务主题 'Cloud' 过滤并获取数据 ---")
	sensors_for_doci = query_sensors(db_path=db_file_path, mission_theme="Cloud")
	print(f"成功查询到 {len(sensors_for_doci)} 条与 'Cloud' 相关的传感器数据。")

	print("\n--- 步骤2: 执行DOCI核心计算 ---")
	json_output = calculate_doci(sensors_data=sensors_for_doci, scenario_config=doci_scenario_config)
	print(json_output)