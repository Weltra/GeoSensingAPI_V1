# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: OCEM_from
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-23
REVISION_NOTES: 重构为从外部数据库和场景文件读取数据。
                修改 calculate_ocem_from_database 函数，使其返回JSON而不是打印。
                新增逻辑，只返回得分大于0的结果。
                修复了当 mission_themes 字段为NULL时导致的 'NoneType' 错误。
                修改函数签名，直接接收场景配置字典。
                修改主程序测试块，使用明文（字典）输入代替文件加载。
"""

import numpy as np
import json
import sqlite3
import pandas as pd
import random
from typing import List, Dict, Any


class OCEM_Evaluator:
	"""
	根据论文 "Observation Capability Evaluation Model for Flood-Observation-Oriented
	Satellite Sensor Selection" (Appl. Sci. 2023, 13, 12482) 复现并封装OCEM算法。
	"""

	def __init__(self, alpha: float = 0.2):
		self.alpha = alpha
		self.RI = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
		self.THCO_RELEVANCE_MAP = {"primary": 1.0, "high": 0.8, "medium": 0.6, "useful": 0.4, "marginal": 0.2}
		self.POL_CONFORMITY_MAP = {"VV": 0.2, "VV/VH": 0.4, "HV": 0.4, "VH": 0.4, "HH": 0.6, "HH/VV": 0.6, "HH/HV": 0.8,
		                           "HH/HV/VV/VH": 1.0}

	def _calculate_spco(self, s_cover: float, s_task: float) -> float:
		return s_cover / s_task if s_task > 0 else 0

	def _calculate_tico(self, t_cover: float, t_task: float) -> float:
		return t_cover / t_task if t_task > 0 else 0

	def _calculate_thco(self, observation_params: List[str]) -> float:
		if not observation_params: return 0
		total_relevance = sum(self.THCO_RELEVANCE_MAP.get(str(p).lower(), 0) for p in observation_params)
		return total_relevance / len(observation_params)

	def _calculate_reti(self, t_start: float, t_end: float, t_respond: float) -> float:
		denominator = t_end - t_start
		return (t_end - t_respond) / denominator if denominator > 0 else 0

	def _calculate_refc(self, rf_i: int, all_rf_values: List[int]) -> float:
		sum_of_squares = sum(rf ** 2 for rf in all_rf_values)
		return rf_i / np.sqrt(sum_of_squares) if sum_of_squares > 0 else 0

	def _calculate_spares(self, spa_i: float, spa_task: float) -> float:
		if spa_i < spa_task: return 1.0
		return spa_task / spa_i if spa_i > 0 else 0

	def _calculate_radres(self, rad_i: int, rad_task: int) -> float:
		if rad_i >= rad_task: return 1.0
		return rad_i / rad_task if rad_task > 0 else 0

	def _calculate_speres(self, r_sensor: Dict, r_task: Dict) -> float:
		r_sensor_min, r_sensor_max = r_sensor.get('range', (0, 0))
		r_task_min, r_task_max = r_task.get('range', (0, 0))
		spe_least = r_task.get('least', 0)
		intersection_min = max(r_sensor_min, r_task_min)
		intersection_max = min(r_sensor_max, r_task_max)
		delta_intersection = intersection_max - intersection_min
		if delta_intersection <= 0: return 0.0
		if delta_intersection < spe_least: return 1.0
		return spe_least / delta_intersection

	def _calculate_pol(self, polarization_mode: str) -> float:
		return self.POL_CONFORMITY_MAP.get(str(polarization_mode), 0)

	def _calculate_enim(self, cloud_cover: float, sensor_type: str) -> float:
		sensor_type_lower = str(sensor_type).lower()
		if 'microwave' in sensor_type_lower or 'sar' in sensor_type_lower: return 1.0
		if 'optical' in sensor_type_lower: return 1.0 - cloud_cover
		return 0.0

	def calculate_ahp_weights(self, matrix: np.ndarray, check_consistency: bool = True) -> np.ndarray:
		n = matrix.shape[0]
		eigenvalues, eigenvectors = np.linalg.eig(matrix)
		max_eigenvalue = np.max(eigenvalues.real)
		max_eigenvector = eigenvectors[:, np.argmax(eigenvalues.real)].real
		weights = max_eigenvector / np.sum(max_eigenvector)
		if check_consistency:
			ci = (max_eigenvalue - n) / (n - 1) if n > 1 else 0
			ri = self.RI.get(n)
			if ri is None or ri == 0:
				cr = float('inf') if ci > 0 else 0
			else:
				cr = ci / ri
			if cr > 0.1:
				raise ValueError(f"AHP矩阵未通过一致性检验 (CR = {cr:.4f} > 0.1)。")
		return weights

	def evaluate_sensor_ranking(self, sensors_data: List[Dict[str, Any]], task_params: Dict[str, Any],
	                            ahp_matrix: np.ndarray) -> List[Dict[str, Any]]:
		weights = self.calculate_ahp_weights(ahp_matrix)
		weight_map = {'ReTi': weights[0], 'TiCo': weights[1], 'ReFc': weights[2], 'SpaRes': weights[3],
		              'SpeRes/Pol': weights[4], 'RadRes': weights[5]}
		all_rf_values = [s.get('revisit_freq', 0) for s in sensors_data]
		results = []
		for sensor in sensors_data:
			factors = {}
			factors['SpCo'] = self._calculate_spco(sensor.get('s_cover', 0), task_params.get('s_task', 1))
			factors['TiCo'] = self._calculate_tico(sensor.get('t_cover', 0), task_params.get('t_task', 1))
			factors['ThCo'] = self._calculate_thco(sensor.get('observation_params', []))
			factors['ReTi'] = self._calculate_reti(task_params.get('t_start', 0), task_params.get('t_end', 1),
			                                       sensor.get('respond_time', 0))
			factors['ReFc'] = self._calculate_refc(sensor.get('revisit_freq', 0), all_rf_values)
			factors['SpaRes'] = self._calculate_spares(sensor.get('spatial_res', float('inf')),
			                                           task_params.get('req_spatial_res', 1))
			factors['RadRes'] = self._calculate_radres(sensor.get('rad_res', 0), task_params.get('req_rad_res', 1))
			sensor_type = sensor.get('type', 'optical').lower()
			factors['EnIm'] = self._calculate_enim(sensor.get('cloud_cover', 0), sensor_type)
			if 'optical' in sensor_type:
				factors['SpeRes/Pol'] = self._calculate_speres(sensor.get('wavelength_info', {}),
				                                               task_params.get('req_wavelength_info', {}))
			elif 'microwave' in sensor_type or 'sar' in sensor_type:
				factors['SpeRes/Pol'] = self._calculate_pol(sensor.get('polarization', ''))
			else:
				factors['SpeRes/Pol'] = 0
			if factors['SpCo'] <= 0 or factors['ThCo'] <= 0 or factors['EnIm'] <= 0:
				ocem_score = 0.0
			else:
				linear_sum = (weight_map['ReTi'] * factors['ReTi'] +
				              weight_map['TiCo'] * factors['TiCo'] +
				              weight_map['ReFc'] * factors['ReFc'] +
				              weight_map['SpaRes'] * factors['SpaRes'] +
				              weight_map['SpeRes/Pol'] * factors['SpeRes/Pol'] +
				              weight_map['RadRes'] * factors['RadRes'])
				if linear_sum <= 0:
					ocem_score = 0.0
				else:
					ocem_score = (np.exp(1 + self.alpha * factors['SpCo']) *
					              np.exp(1 + self.alpha * factors['ThCo']) *
					              np.exp(1 + self.alpha * factors['EnIm']) *
					              np.exp(1 + self.alpha * linear_sum))
			results.append({'name': sensor['name'], 'ocem_score': ocem_score})
		max_score = max(r['ocem_score'] for r in results) if results else 1
		if max_score == 0: max_score = 1
		for r in results:
			r['normalized_score'] = r['ocem_score'] / max_score
		return sorted(results, key=lambda x: x['ocem_score'], reverse=True)


def calculate_ocem_from_database(db_path: str, scenario_config: dict) -> str:
	"""
	从数据库加载数据，根据传入的场景配置执行OCEM评估，并以JSON格式返回结果。
	"""
	try:
		# 1. 直接使用传入的场景配置字典
		ocem_config = scenario_config['models']['ocem']
		task_params = ocem_config['requirements']
		task_params.update({
			't_start': pd.to_datetime(scenario_config['time_window']['start']).timestamp(),
			't_end': pd.to_datetime(scenario_config['time_window']['end']).timestamp()
		})
		ahp_matrix = np.array(ocem_config['ahp_matrix'])
		cloud_cover = scenario_config['environment']['cloudiness_forecast']

		# 2. 从数据库查询传感器静态数据
		con = sqlite3.connect(db_path)
		df_sensors = pd.read_sql_query(
			"SELECT name, type, spatial_resolution_m, quantization_bits, temporal_resolution_days, polarization, mission_themes FROM sensors",
			con)
		con.close()
		sensors_data = df_sensors.to_dict('records')

		# 3. 补充动态/模拟的参数
		thco_opts = ["primary", "high", "medium", "useful", "marginal"]
		for sensor in sensors_data:
			sensor['s_cover'] = random.uniform(0.1, 0.8)
			sensor['t_cover'] = random.uniform(0.1, 0.8)

			try:
				themes_str = sensor.get('mission_themes')
				if themes_str and isinstance(themes_str, str):
					themes = json.loads(themes_str.replace("'", "\""))
					sensor['observation_params'] = random.sample(list(themes), k=1) if themes else ['medium']
				else:
					sensor['observation_params'] = [random.choice(thco_opts)]
			except (json.JSONDecodeError, TypeError):
				sensor['observation_params'] = [random.choice(thco_opts)]

			sensor['respond_time'] = task_params['t_start'] + random.uniform(1, 24 * 3) * 3600
			sensor['revisit_freq'] = sensor['temporal_resolution_days']
			sensor['spatial_res'] = sensor['spatial_resolution_m']
			sensor['rad_res'] = sensor['quantization_bits']
			sensor['cloud_cover'] = cloud_cover

		# 4. 初始化评估器并执行计算
		evaluator = OCEM_Evaluator(alpha=0.2)
		ranked_sensors = evaluator.evaluate_sensor_ranking(
			sensors_data,
			task_params,
			ahp_matrix
		)

		# 5. 过滤并重新排名
		positive_sensors = [sensor for sensor in ranked_sensors if sensor["normalized_score"] > 0]
		for rank, sensor in enumerate(positive_sensors):
			sensor["rank"] = rank + 1

		result_json = {
			"status": "success",
			"scenario": scenario_config.get('description', 'Custom Scenario'),
			"model": "OCEM",
			"description": ocem_config.get('description', ''),
			"results": positive_sensors
		}
		return json.dumps(result_json, indent=4, ensure_ascii=False)

	except Exception as e:
		error_json = {
			"status": "error",
			"scenario": scenario_config.get('description', 'Custom Scenario'),
			"model": "OCEM",
			"message": str(e)
		}
		return json.dumps(error_json, indent=4, ensure_ascii=False)


if __name__ == '__main__':
	# --- 主程序测试块 ---
	db_file_path = "D:\\GeoSensingAPI\\data\\sensors_enriched.db"

	# 直接在此处定义场景配置字典
	ocem_scenario_config = {
		"description": "评估在多云条件下，各传感器对武汉市洪灾的快速响应和持续观测能力。",
		"time_window": {
			"start": "2025-08-01 00:00:00.000",
			"end": "2025-08-01 23:59:59.000"
		},
		"environment": {
			"cloudiness_forecast": 0.45
		},
		"models": {
			"ocem": {
				"description": "OCEM模型综合评估时间、空间、主题、辐射等多维度能力，尤其适合应急响应场景。",
				"requirements": {
					"s_task": 15000,
					"t_task": 7,
					"req_spatial_res": 15,
					"req_rad_res": 10,
					"req_wavelength_info": {
						"range": [400, 900],
						"least": 50
					}
				},
				"ahp_matrix": [
					[1, 2, 3, 4, 5, 6],
					[0.5, 1, 2, 3, 4, 5],
					[0.333, 0.5, 1, 2, 3, 4],
					[0.25, 0.333, 0.5, 1, 2, 3],
					[0.2, 0.25, 0.333, 0.5, 1, 2],
					[0.167, 0.2, 0.25, 0.333, 0.5, 1]
				]
			}
		}
	}

	json_output = calculate_ocem_from_database(db_path=db_file_path, scenario_config=ocem_scenario_config)
	print(json_output)