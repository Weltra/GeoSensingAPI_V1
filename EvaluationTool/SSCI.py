# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: SSCI_from_db
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-23
"""
import numpy as np
import json
from sklearn.decomposition import PCA
from query_utils import query_sensors


class SSCI_Evaluator:
	def preprocess_data(self, raw_data: np.ndarray, reciprocal_cols: list = [],
	                    weights: np.ndarray = None) -> np.ndarray:
		processed_data = raw_data.astype(float)
		for col_idx in reciprocal_cols:
			non_zero_mask = processed_data[:, col_idx] != 0
			processed_data[non_zero_mask, col_idx] = np.reciprocal(processed_data[non_zero_mask, col_idx])
		max_vals = np.max(processed_data, axis=0)
		non_zero_max_mask = max_vals != 0
		processed_data[:, non_zero_max_mask] = np.divide(processed_data[:, non_zero_max_mask],
		                                                 max_vals[non_zero_max_mask])
		if weights is not None:
			if weights.shape[0] != processed_data.shape[1]: raise ValueError("权重数量必须与参数数量匹配。")
			processed_data = processed_data * weights
		return processed_data

	def calculate_ssci(self, raw_data: np.ndarray, reciprocal_cols: list, weights: np.ndarray,
	                   info_threshold: float = 0.90) -> tuple:
		preprocessed_matrix = self.preprocess_data(raw_data, reciprocal_cols, weights)
		pca = PCA()
		capability_vectors = pca.fit_transform(preprocessed_matrix)
		explained_variance_ratio = pca.explained_variance_ratio_
		cumulative_variance = np.cumsum(explained_variance_ratio)
		n_components = np.argmax(cumulative_variance >= info_threshold) + 1 if np.any(
			cumulative_variance >= info_threshold) else len(cumulative_variance)
		if n_components == 0 and len(cumulative_variance) > 0: n_components = 1
		capability_vectors_selected = capability_vectors[:, :n_components]
		explained_variance_ratio_selected = explained_variance_ratio[:n_components]
		sum_explained_variance = np.sum(explained_variance_ratio_selected)
		if sum_explained_variance == 0: return np.zeros(raw_data.shape[0]), capability_vectors_selected
		ssci_weights = explained_variance_ratio_selected / sum_explained_variance
		ssci_scores = np.sum(capability_vectors_selected * ssci_weights, axis=1)
		return ssci_scores, capability_vectors_selected


def calculate_ssci(sensors_data: dict, scenario_config: dict) -> str:
	try:
		ssci_config = scenario_config['models']['ssci']
		param_names_in_order = list(ssci_config['weights_by_name'].keys())

		if not sensors_data:
			raise ValueError("输入的传感器数据字典 'sensors_data' 为空。")

		# 过滤掉缺少SSCI所需参数的传感器
		valid_sensors = {name: params for name, params in sensors_data.items() if
		                 all(p in params and params[p] is not None for p in param_names_in_order)}
		if not valid_sensors:
			raise ValueError("数据中没有包含所有SSCI所需参数的有效传感器。")

		sensor_names = list(valid_sensors.keys())
		raw_data = np.array([[sensor[param] for param in param_names_in_order] for sensor in valid_sensors.values()])

		reciprocal_indices = [param_names_in_order.index(col) for col in ssci_config['reciprocal_cols_by_name']]
		task_weights = np.array(list(ssci_config['weights_by_name'].values()))

		evaluator = SSCI_Evaluator()
		ssci_results, _ = evaluator.calculate_ssci(
			raw_data=raw_data, reciprocal_cols=reciprocal_indices,
			weights=task_weights, info_threshold=0.95
		)

		sorted_indices = np.argsort(ssci_results)[::-1]
		all_ranked_sensors = [{"name": sensor_names[idx], "ssci_score": float(ssci_results[idx])} for idx in
		                      sorted_indices]

		positive_sensors = [s for s in all_ranked_sensors if s["ssci_score"] > 0]
		for rank, sensor in enumerate(positive_sensors): sensor["rank"] = rank + 1

		return json.dumps({
			"status": "success", "scenario": scenario_config.get('description'), "model": "SSCI",
			"description": ssci_config.get('description', ''), "results": positive_sensors
		}, indent=4, ensure_ascii=False)

	except Exception as e:
		return json.dumps({"status": "error", "model": "SSCI", "message": str(e)}, indent=4, ensure_ascii=False)


if __name__ == '__main__':
	db_file_path = "D:\\GeoSensingAPI\\data\\sensors_enriched.db"
	ssci_scenario_config = {
		"description": "SSCI评估", "models": {"ssci": {
			"description": "SSCI模型",
			"weights_by_name": {"swath_width_km": 0.8, "spatial_resolution_m": 1.2, "quantization_bits": 1.0,
			                    "temporal_resolution_days": 1.1, "design_life_yrs": 0.6, "data_rate_mbps": 0.5},
			"reciprocal_cols_by_name": ["spatial_resolution_m", "temporal_resolution_days"]
		}}
	}

	print("--- 步骤1: 使用通用查询函数获取所有传感器数据 ---")
	sensors_for_ssci = query_sensors(db_path=db_file_path)
	print(f"成功查询到 {len(sensors_for_ssci)} 条有效传感器数据。")

	print("\n--- 步骤2: 执行SSCI核心计算 ---")
	json_output = calculate_ssci(sensors_data=sensors_for_ssci, scenario_config=ssci_scenario_config)
	print(json_output)