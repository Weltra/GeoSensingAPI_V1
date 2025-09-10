# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI 
FILE_NAME: filter_sliver_polygons 
AUTHOR: welt 
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-09-08 
"""


import geopandas as gpd
import json
import os
import traceback
from typing import List, Dict
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

def get_projection_crs_for_filtering(gdf: gpd.GeoDataFrame) -> str:
    """为给定的GeoDataFrame计算合适的UTM坐标参考系。"""
    try:
        # 计算整个GeoDataFrame的中心点以确定最佳UTM区域
        centroid = gdf.unary_union.centroid
        lon, lat = centroid.x, centroid.y
        utm_band = str(int((lon + 180) // 6 + 1))
        # 根据南北半球选择EPSG代码
        epsg_code = '326' + utm_band.zfill(2) if lat >= 0 else '327' + utm_band.zfill(2)
        return f"EPSG:{epsg_code}"
    except Exception:
        return "EPSG:3857" # 回退选项

def filter_sliver_polygons(input_files_dict: Dict[str, str],
                           output_directory: str,
                           min_area_threshold_m2: float = 100.0) -> Dict[str, str]:
    """
    对输入的GeoJSON文件进行面积过滤，移除面积过小的碎片多边形。

    参数:
        input_files_dict (Dict[str, str]): 输入字典。键是任务标识符，值是需要过滤的GeoJSON文件路径。
                                           通常这是 difference 函数的输出。
        output_directory (str): 用于存储过滤后的干净文件的目录。
        min_area_threshold_m2 (float): 最小面积阈值（平方米）。小于此面积的多边形将被移除。

    返回:
        Dict[str, str]: 包含过滤后文件路径的结果字典。
    """
    cleaned_results = {}
    error_log = []
    os.makedirs(output_directory, exist_ok=True)

    print(f"开始过滤碎片多边形 (阈值: {min_area_threshold_m2} m²)...")

    for task_key, input_filepath in input_files_dict.items():
        if task_key == "errors":  # 忽略上一步的错误日志条目
            continue

        try:
            # --- 步骤 1: 加载数据 ---
            gdf = gpd.read_file(input_filepath)
            if gdf.empty:
                print(f"任务 {task_key}: 输入文件 {input_filepath} 为空，跳过过滤。")
                continue

            # --- 步骤 2: 投影以进行精确面积计算 ---
            projected_crs = get_projection_crs_for_filtering(gdf)
            gdf_proj = gdf.to_crs(projected_crs)

            # --- 步骤 3: 面积过滤 ---
            filtered_geometries_proj = []
            # 迭代所有几何图形进行检查
            for geom in gdf_proj.geometry:
                if geom.area > min_area_threshold_m2:
                    filtered_geometries_proj.append(geom)

            # --- 步骤 4: 重组几何体并转换回原始坐标系 ---
            if not filtered_geometries_proj:
                final_result_geometry_wgs84 = shape({"type": "GeometryCollection", "geometries": []})
            else:
                filtered_union_proj = unary_union(filtered_geometries_proj)
                final_result_gdf = gpd.GeoSeries([filtered_union_proj], crs=projected_crs)
                final_result_geometry_wgs84 = final_result_gdf.to_crs(gdf.crs).unary_union

            # --- 步骤 5: 保存过滤后的文件 ---
            output_filename = f"{task_key}_filtered.geojson"
            output_filepath = os.path.join(output_directory, output_filename)

            result_features = []
            if not final_result_geometry_wgs84.is_empty:
                geoms_to_save = final_result_geometry_wgs84.geoms if hasattr(final_result_geometry_wgs84, 'geoms') else [final_result_geometry_wgs84]
                for g in geoms_to_save:
                    result_features.append({"type": "Feature", "geometry": mapping(g), "properties": {}})

            result_geojson = {"type": "FeatureCollection", "features": result_features}
            with open(output_filepath, "w", encoding="utf-8") as f:
                json.dump(result_geojson, f, ensure_ascii=False, indent=2)

            cleaned_results[task_key] = output_filepath

        except Exception as e:
            message = f"任务 {task_key}: 过滤文件 {input_filepath} 时出错: {e}"
            print(message)
            traceback.print_exc()
            error_log.append(message)

    if error_log:
        cleaned_results["errors"] = error_log

    return cleaned_results