# --- [修改后的 difference 函数 v4 - 支持批处理] ---
# 替换原有的 difference 函数

import geopandas as gpd
import json
import os
import traceback
from typing import List, Dict
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

def difference(tasks: List[Dict[str, str]], output_directory: str = "geojson_results") -> Dict[str, str]:
    """
    计算多个差集任务（批处理）。

    参数:
        tasks (List[Dict[str, str]]): 任务列表。每个字典代表一个任务，包含源文件和裁剪文件路径。
            示例: [
                {"source": "path/to/area1.geojson", "clip": "path/to/coverage1.geojson"},
                {"source": "path/to/area2.geojson", "clip": "path/to/coverage2.geojson"}
            ]
        output_directory (str): 用于存储生成的差集文件的目录。

    返回:
        Dict[str, str]: 聚合结果字典。键为组合文件名，值为生成的 GeoJSON 文件的完整路径。
                       包含一个特殊的 "errors" 键来记录失败的任务详情。
    """
    aggregated_results = {}
    error_log = []

    for i, task in enumerate(tasks):
        source_path = task.get("source")
        clip_path = task.get("clip")
        task_id_str = f"任务 {i+1} (Source: {os.path.basename(source_path)}, Clip: {os.path.basename(clip_path)})"

        if not source_path or not clip_path:
            message = f"{task_id_str}: 失败 - 输入字典缺少 'source' 或 'clip' 键。"
            print(message)
            error_log.append(message)
            continue

        try:
            # 1. 加载并计算几何体差集 (与上一版本相同)
            with open(source_path, "r", encoding="utf-8") as f:
                source_data = json.load(f)
            source_geometries = [shape(feature["geometry"]) for feature in source_data.get("features", []) if feature.get("geometry")]
            source_union = unary_union(source_geometries)

            with open(clip_path, "r", encoding="utf-8") as f:
                clip_data = json.load(f)
            clip_geometries = [shape(feature["geometry"]) for feature in clip_data.get("features", []) if feature.get("geometry")]
            clip_union = unary_union(clip_geometries)

            result_geometry = source_union.difference(clip_union)

            # 2. 准备输出文件路径和字典键名
            source_basename = os.path.splitext(os.path.basename(source_path))[0]
            clip_basename = os.path.splitext(os.path.basename(clip_path))[0]
            output_key = f"{source_basename}_difference_{clip_basename}"
            output_filename = f"{output_key}.geojson"

            os.makedirs(output_directory, exist_ok=True)
            output_filepath = os.path.join(output_directory, output_filename)

            # 3. 将结果保存为 GeoJSON 文件
            result_features = []
            if not result_geometry.is_empty:
                if hasattr(result_geometry, 'geoms'): # MultiPolygon or GeometryCollection
                    result_features = [{"type": "Feature", "geometry": mapping(g), "properties": {}} for g in result_geometry.geoms]
                else: # Single Polygon
                    result_features = [{"type": "Feature", "geometry": mapping(result_geometry), "properties": {}}]

            result_geojson = {"type": "FeatureCollection", "features": result_features}

            with open(output_filepath, "w", encoding="utf-8") as f:
                json.dump(result_geojson, f, ensure_ascii=False, indent=2)

            # 4. 存入聚合结果字典
            aggregated_results[output_key] = output_filepath
            print(f"{task_id_str}: 成功完成。")

        except Exception as e:
            message = f"{task_id_str}: 计算时发生意外错误: {e}"
            print(message)
            traceback.print_exc()
            error_log.append(message)

    if error_log:
        aggregated_results["errors"] = error_log

    return aggregated_results
