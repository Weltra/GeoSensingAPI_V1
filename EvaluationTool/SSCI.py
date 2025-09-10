# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: SSCI_from_db
AUTHOR: welt
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-08-23
REVISION_NOTES: 重构为从外部数据库和场景文件读取数据。
                修改 calculate_ssci_from_database 函数，使其返回JSON而不是打印。
                新增逻辑，只返回得分大于0的结果。
                修改函数签名，直接接收场景配置字典。
                修改主程序测试块，使用明文（字典）输入代替文件加载。
"""

import numpy as np
import json
import sqlite3
import pandas as pd
from sklearn.decomposition import PCA


class SSCI_Evaluator:
	"""
	根据论文 "Spaceborne Earth-Observing Optical Sensor Static Capability Index
	for Clustering" (Chen et al., 2015) 复现并封装SSCI计算算法。

	该类实现了以下核心功能:
	1. 传感器静态能力参数的预处理（倒数转换、标准化、加权）。
	2. 应用主成分分析（PCA）提取关键能力成分。
	3. 计算每个传感器的最终静态能力指数（SSCI）。
	"""

	def preprocess_data(self,
	                    raw_data: np.ndarray,
	                    reciprocal_cols: list = [],
	                    weights: np.ndarray = None) -> np.ndarray:
		"""
		对原始静态能力参数矩阵进行预处理。

		Args:
		   raw_data (np.ndarray): 原始数据矩阵 (n_sensors, n_parameters)。
		   reciprocal_cols (list): 需要取倒数的列索引列表。
		   weights (np.ndarray): 施加于各参数的权重向量 (1, n_parameters)。

		Returns:
		   np.ndarray: 经过预处理（倒数、标准化、加权）后的数据矩阵。
		"""
		processed_data = raw_data.astype(float)

		# 步骤 1: 对指定列取倒数
		for col_idx in reciprocal_cols:
			# 避免除以零
			non_zero_mask = processed_data[:, col_idx] != 0
			processed_data[non_zero_mask, col_idx] = np.reciprocal(processed_data[non_zero_mask, col_idx])

		# 步骤 2: 标准化 - 除以每列的最大值
		max_vals = np.max(processed_data, axis=0)
		# 避免除以零
		non_zero_max_mask = max_vals != 0
		processed_data[:, non_zero_max_mask] = np.divide(processed_data[:, non_zero_max_mask],
		                                                 max_vals[non_zero_max_mask])

		# 步骤 3: 人为加权 - 乘以用户定义的权重
		if weights is not None:
			if weights.shape[0] != processed_data.shape[1]:
				raise ValueError("权重数量必须与参数数量匹配。")
			processed_data = processed_data * weights

		return processed_data

	def calculate_ssci(self,
	                   raw_data: np.ndarray,
	                   reciprocal_cols: list,
	                   weights: np.ndarray,
	                   info_threshold: float = 0.90) -> tuple:
		"""
		计算SSCI并返回能力得分向量。

		Args:
		   raw_data (np.ndarray): 原始数据矩阵 (n_sensors, n_parameters)。
		   reciprocal_cols (list): 需要取倒数的列索引。
		   weights (np.ndarray): 参数的权重向量。
		   info_threshold (float): PCA保留信息量的阈值。

		Returns:
		   tuple: 包含 ssci_scores 和 capability_vectors_selected 的元组。
		"""
		preprocessed_matrix = self.preprocess_data(raw_data, reciprocal_cols, weights)
		pca = PCA()
		capability_vectors = pca.fit_transform(preprocessed_matrix)
		explained_variance_ratio = pca.explained_variance_ratio_
		cumulative_variance = np.cumsum(explained_variance_ratio)

		# 确保至少选择一个主成分
		n_components = np.argmax(cumulative_variance >= info_threshold) + 1 if np.any(
			cumulative_variance >= info_threshold) else len(cumulative_variance)
		if n_components == 0 and len(cumulative_variance) > 0: n_components = 1

		capability_vectors_selected = capability_vectors[:, :n_components]
		explained_variance_ratio_selected = explained_variance_ratio[:n_components]

		# 避免除以零
		sum_explained_variance = np.sum(explained_variance_ratio_selected)
		if sum_explained_variance == 0: return np.zeros(raw_data.shape[0]), capability_vectors_selected

		ssci_weights = explained_variance_ratio_selected / sum_explained_variance
		ssci_scores = np.sum(capability_vectors_selected * ssci_weights, axis=1)

		return ssci_scores, capability_vectors_selected


def calculate_ssci_from_database(db_path: str, scenario_config: dict) -> str:
	"""
	从数据库加载数据，根据传入的场景配置执行SSCI评估，并以JSON格式返回结果。
	"""
	try:
		# 1. 直接使用传入的场景配置字典
		ssci_config = scenario_config['models']['ssci']

		# 2. 从数据库查询传感器数据
		param_names_in_order = list(ssci_config['weights_by_name'].keys())
		con = sqlite3.connect(db_path)
		query = f"SELECT name, {', '.join(param_names_in_order)} FROM sensors"
		df_sensors = pd.read_sql_query(query, con)
		con.close()
		df_sensors.dropna(inplace=True)

		if df_sensors.empty:
			raise ValueError("数据库中没有找到符合所有必需参数的有效传感器数据。")

		sensor_names = df_sensors['name'].tolist()
		raw_data = df_sensors[param_names_in_order].to_numpy()

		# 3. 准备评估参数
		reciprocal_indices = [param_names_in_order.index(col) for col in ssci_config['reciprocal_cols_by_name']]
		task_weights = np.array(list(ssci_config['weights_by_name'].values()))

		# 4. 初始化评估器并执行计算
		evaluator = SSCI_Evaluator()
		ssci_results, _ = evaluator.calculate_ssci(
			raw_data=raw_data,
			reciprocal_cols=reciprocal_indices,
			weights=task_weights,
			info_threshold=0.95
		)

		# 5. 格式化结果
		sorted_indices = np.argsort(ssci_results)[::-1]

		all_ranked_sensors = []
		for idx in sorted_indices:
			all_ranked_sensors.append({
				"name": sensor_names[idx],
				"ssci_score": float(ssci_results[idx])  # 确保是标准float类型
			})

		# 6. 过滤并重新排名
		positive_sensors = [sensor for sensor in all_ranked_sensors if sensor["ssci_score"] > 0]
		for rank, sensor in enumerate(positive_sensors):
			sensor["rank"] = rank + 1

		result_json = {
			"status": "success",
			"scenario": scenario_config.get('description', 'Custom Scenario'),
			"model": "SSCI",
			"description": ssci_config.get('description', ''),
			"results": positive_sensors
		}
		return json.dumps(result_json, indent=4, ensure_ascii=False)

	except Exception as e:
		error_json = {
			"status": "error",
			"scenario": scenario_config.get('description', 'Custom Scenario'),
			"model": "SSCI",
			"message": str(e)
		}
		return json.dumps(error_json, indent=4, ensure_ascii=False)


if __name__ == '__main__':
	# --- MODIFICATION START ---
	# 更新的调用方式：使用明文（Python字典）作为输入场景
	db_file_path = "D:\\GeoSensingAPI\\data\\sensors_enriched.db"

	# 直接在此处定义场景配置字典
	ssci_scenario_config = {
		"description": "基于传感器的静态技术参数，评估其在通用土地覆盖测绘任务中的综合潜力。",
		"models": {
			"ssci": {
				"description": "SSCI模型通过主成分分析，聚焦于传感器硬件的静态能力，如分辨率、幅宽、量化比特等。",
				"weights_by_name": {
					"swath_km": 0.8,
					"spatial_resolution_m": 1.2,
					"quantization_bits": 1.0,
					"temporal_resolution_days": 1.1,
					"onboard_storage_gb": 0.6,
					"power_w": 0.5
				},
				"reciprocal_cols_by_name": [
					"spatial_resolution_m",
					"temporal_resolution_days"
				]
			}
		}
	}

	json_output = calculate_ssci_from_database(db_path=db_file_path,
	                                           scenario_config=ssci_scenario_config)
	# --- MODIFICATION END ---
	print(json_output)