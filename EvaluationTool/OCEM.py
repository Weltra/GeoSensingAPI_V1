# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: OCEM_from
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-23
"""

import numpy as np
import json
import pandas as pd
import random
from typing import List, Dict, Any
from query_utils import query_sensors


class OCEM_Evaluator:
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
		return sum(self.THCO_RELEVANCE_MAP.get(str(p).lower(), 0) for p in observation_params) / len(observation_params)

	def _calculate_reti(self, t_start: float, t_end: float, t_respond: float) -> float:
		return (t_end - t_respond) / (t_end - t_start) if (t_end - t_start) > 0 else 0

	def _calculate_refc(self, rf_i: int, all_rf_values: List[int]) -> float:
		sum_sq = sum(rf ** 2 for rf in all_rf_values if rf is not None)
		return rf_i / np.sqrt(sum_sq) if sum_sq > 0 and rf_i is not None else 0

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
		delta = min(r_sensor_max, r_task_max) - max(r_sensor_min, r_task_min)
		if delta <= 0: return 0.0
		return 1.0 if delta < spe_least else spe_least / delta

	def _calculate_pol(self, polarization_mode: str) -> float:
		return self.POL_CONFORMITY_MAP.get(str(polarization_mode), 0)

	def _calculate_enim(self, cloud_cover: float, sensor_type: str) -> float:
		stype = str(sensor_type).lower()
		if 'microwave' in stype or 'sar' in stype: return 1.0
		return 1.0 - cloud_cover if 'optical' in stype else 0.0

	def calculate_ahp_weights(self, matrix: np.ndarray, check_consistency: bool = True) -> np.ndarray:
		n = matrix.shape[0]
		eigvals, eigvecs = np.linalg.eig(matrix)
		max_eigval = np.max(eigvals.real)
		weights = eigvecs[:, np.argmax(eigvals.real)].real
		weights /= np.sum(weights)
		if check_consistency:
			ci = (max_eigval - n) / (n - 1) if n > 1 else 0
			ri = self.RI.get(n)
			cr = ci / ri if ri else float('inf')
			if cr > 0.1: raise ValueError(f"AHP matrix failed consistency check (CR={cr:.4f}).")
		return weights

	def evaluate_sensor_ranking(self, sensors_data: List[Dict[str, Any]], task_params: Dict[str, Any],
	                            ahp_matrix: np.ndarray) -> List[Dict[str, Any]]:
		weights = self.calculate_ahp_weights(ahp_matrix)
		w_map = {'ReTi': weights[0], 'TiCo': weights[1], 'ReFc': weights[2], 'SpaRes': weights[3],
		         'SpeRes/Pol': weights[4], 'RadRes': weights[5]}
		all_rf = [s.get('revisit_freq', 0) for s in sensors_data]
		results = []
		for sensor in sensors_data:
			factors = {
				'SpCo': self._calculate_spco(sensor.get('s_cover', 0), task_params.get('s_task', 1)),
				'TiCo': self._calculate_tico(sensor.get('t_cover', 0), task_params.get('t_task', 1)),
				'ThCo': self._calculate_thco(sensor.get('observation_params', [])),
				'ReTi': self._calculate_reti(task_params['t_start'], task_params['t_end'],
				                             sensor.get('respond_time', 0)),
				'ReFc': self._calculate_refc(sensor.get('revisit_freq'), all_rf),
				'SpaRes': self._calculate_spares(sensor.get('spatial_res'), task_params['req_spatial_res']),
				'RadRes': self._calculate_radres(sensor.get('rad_res'), task_params['req_rad_res']),
				'EnIm': self._calculate_enim(sensor.get('cloud_cover', 0), sensor.get('type', 'optical')),
			}
			stype = sensor.get('type', 'optical').lower()
			if 'optical' in stype:
				factors['SpeRes/Pol'] = self._calculate_speres(sensor.get('wavelength_info', {}),
				                                               task_params['req_wavelength_info'])
			else:
				factors['SpeRes/Pol'] = self._calculate_pol(sensor.get('polarization', ''))

			if any(factors[k] <= 0 for k in ['SpCo', 'ThCo', 'EnIm']):
				ocem = 0.0
			else:
				linear_sum = sum(w_map[k] * factors[k] for k in w_map)
				ocem = (np.exp(1 + self.alpha * factors['SpCo']) * np.exp(1 + self.alpha * factors['ThCo']) * np.exp(
					1 + self.alpha * factors['EnIm']) * np.exp(1 + self.alpha * linear_sum)) if linear_sum > 0 else 0.0
			results.append({'name': sensor['name'], 'ocem_score': ocem})

		max_score = max(r['ocem_score'] for r in results) if results else 1
		if max_score == 0: max_score = 1
		for r in results: r['normalized_score'] = r['ocem_score'] / max_score
		return sorted(results, key=lambda x: x['ocem_score'], reverse=True)


def calculate_ocem(sensors_data: dict, scenario_config: dict) -> str:
	try:
		ocem_config = scenario_config['models']['ocem']
		task_params = ocem_config['requirements']
		task_params.update({
			't_start': pd.to_datetime(scenario_config['time_window']['start']).timestamp(),
			't_end': pd.to_datetime(scenario_config['time_window']['end']).timestamp()
		})
		ahp_matrix = np.array(ocem_config['ahp_matrix'])
		cloud_cover = scenario_config['environment']['cloudiness_forecast']

		sensors_list_for_eval = [{'name': name, **params} for name, params in sensors_data.items()]

		for sensor in sensors_list_for_eval:
			sensor['s_cover'] = random.uniform(0.1, 0.8)
			sensor['t_cover'] = random.uniform(0.1, 0.8)
			try:
				themes = json.loads(str(sensor.get('mission_themes')).replace("'", "\"")) if sensor.get(
					'mission_themes') else []
				sensor['observation_params'] = random.sample(themes, k=1) if themes else ['medium']
			except:
				sensor['observation_params'] = ['medium']
			sensor['respond_time'] = task_params['t_start'] + random.uniform(3600, 3 * 3600 * 24)
			sensor['revisit_freq'] = sensor['temporal_resolution_days']
			sensor['spatial_res'] = sensor['spatial_resolution_m']
			sensor['rad_res'] = sensor['quantization_bits']
			sensor['cloud_cover'] = cloud_cover

		evaluator = OCEM_Evaluator(alpha=0.2)
		ranked_sensors = evaluator.evaluate_sensor_ranking(sensors_list_for_eval, task_params, ahp_matrix)

		positive_sensors = [s for s in ranked_sensors if s["normalized_score"] > 0]
		for rank, sensor in enumerate(positive_sensors): sensor["rank"] = rank + 1

		return json.dumps({
			"status": "success", "scenario": scenario_config.get('description'), "model": "OCEM",
			"description": ocem_config.get('description', ''), "results": positive_sensors
		}, indent=4, ensure_ascii=False)

	except Exception as e:
		return json.dumps({"status": "error", "model": "OCEM", "message": str(e)}, indent=4, ensure_ascii=False)


if __name__ == '__main__':
	db_file_path = "D:\\GeoSensingAPI\\data\\sensors_enriched.db"
	ocem_scenario_config = {
		"description": "OCEM评估", "time_window": {"start": "2025-08-24T00:00:00Z", "end": "2025-08-24T23:59:59Z"},
		"environment": {"cloudiness_forecast": 0.45}, "models": {"ocem": {
			"description": "OCEM模型",
			"requirements": {"s_task": 15000, "t_task": 7, "req_spatial_res": 15, "req_rad_res": 10,
			                 "req_wavelength_info": {"range": [400, 900], "least": 50}},
			"ahp_matrix": [[1, 2, 3, 4, 5, 6], [0.5, 1, 2, 3, 4, 5], [0.333, 0.5, 1, 2, 3, 4],
			               [0.25, 0.333, 0.5, 1, 2, 3], [0.2, 0.25, 0.333, 0.5, 1, 2],
			               [0.167, 0.2, 0.25, 0.333, 0.5, 1]]
		}}
	}

	print("--- 步骤1: 使用通用查询函数获取所有传感器数据 ---")
	sensors_for_ocem = query_sensors(db_path=db_file_path)
	print(f"成功查询到 {len(sensors_for_ocem)} 条有效传感器数据。")

	print("\n--- 步骤2: 执行OCEM核心计算 ---")
	json_output = calculate_ocem(sensors_data=sensors_for_ocem, scenario_config=ocem_scenario_config)
	print(json_output)