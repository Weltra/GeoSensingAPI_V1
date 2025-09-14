import os
from typing import Union, List, Dict

import geopandas as gpd


def get_projection_crs(gdf: gpd.GeoDataFrame) -> str:
	"""为给定的GeoDataFrame计算合适的UTM坐标参考系。"""
	if gdf.empty:
		return "EPSG:3857"  # Fallback CRS
	try:
		# 使用 unary_union 来正确处理包含多个要素的 GDF
		centroid = gdf.unary_union.centroid
		lon, lat = centroid.x, centroid.y
		utm_band = str(int((lon + 180) // 6 + 1))
		epsg_code = '326' + utm_band.zfill(2) if lat >= 0 else '327' + utm_band.zfill(2)
		return f"EPSG:{epsg_code}"
	except Exception:
		# 如果出现任何异常，返回一个通用的投影坐标系
		return "EPSG:3857"


def difference(geojson_names: Union[str, List[str]], clip_geojson_name: str) -> Dict[str, str]:
	"""
   计算一个或多个 GeoJSON 文件与另一个 GeoJSON 文件的差集，并精确过滤每一个细碎多边形后保存。

   Args:
      geojson_names (Union[str, List[str]]):
         - 单个 GeoJSON 文件名（不含路径和扩展名）
         - 或多个文件名组成的列表
      clip_geojson_name (str): 用于裁剪的 GeoJSON 文件名 (要移除的对象)

   Returns:
      Dict[str, str]:
         - 始终返回字典，键为输入文件名，值为对应输出文件名。
   """
	names = [geojson_names] if isinstance(geojson_names, str) else geojson_names
	results = {}

	try:
		clip_path = os.path.join("geojson", f"{clip_geojson_name}.geojson")
		clip_gdf = gpd.read_file(clip_path)
	except Exception as e:
		print(f"ERROR: 无法读取裁剪文件 {clip_geojson_name}.geojson: {e}")
		for name in names:
			results[name] = f"Error: Failed to read clip file {clip_geojson_name}.geojson"
		return results

	for name in names:
		input_path = os.path.join("geojson", f"{name}.geojson")
		output_name = f"{name}_difference_filtered"
		output_path = os.path.join("geojson", f"{output_name}.geojson")

		try:
			source_gdf = gpd.read_file(input_path)
			if source_gdf.empty:
				print(f"INFO: 源文件 {name} 为空，跳过处理。")
				results[name] = output_name
				gpd.GeoDataFrame(geometry=[], crs="EPSG:4326").to_file(output_path, driver='GeoJSON')
				continue

			# 1. 确定并转换到合适的UTM坐标系
			projected_crs = get_projection_crs(source_gdf)
			print(f"INFO: 为 {name} 自动选择UTM坐标系: {projected_crs}")
			source_gdf_proj = source_gdf.to_crs(projected_crs)
			clip_gdf_proj = clip_gdf.to_crs(projected_crs)

			# 2. 在投影坐标系下执行差集运算
			clip_union_proj = clip_gdf_proj.unary_union
			source_gdf_proj['geometry'] = source_gdf_proj.geometry.difference(clip_union_proj)

			# 3. 几何清理
			source_gdf_proj['geometry'] = source_gdf_proj.geometry.buffer(0)
			source_gdf_proj = source_gdf_proj[~source_gdf_proj.geometry.is_empty]

			if source_gdf_proj.empty:
				print(f"INFO: 为 {name} 计算差集和清理后，没有剩余的有效区域。")
				results[name] = output_name
				gpd.GeoDataFrame(geometry=[], crs="EPSG:4326").to_file(output_path, driver='GeoJSON')
				continue

			# --- 【核心修正】---
			# 4. 使用 explode 分解 MultiPolygon，确保对每个独立多边形进行过滤
			# index_parts=False 可以确保索引不重复
			exploded_gdf_proj = source_gdf_proj.explode(index_parts=False)

			# 5. 自动阈值计算与过滤
			initial_count = len(exploded_gdf_proj)

			# 5.1. 自动计算面积过滤阈值
			areas = exploded_gdf_proj.area
			significant_areas = areas[areas > 1.0]

			if not significant_areas.empty:
				area_quantile = significant_areas.quantile(0.10)
				min_area_threshold_m2 = max(200.0, min(area_quantile, 10000.0))
			else:
				min_area_threshold_m2 = 200.0

			print(f"INFO: 为 {name} 自动计算的过滤阈值为 {min_area_threshold_m2:.2f} m²")

			# 5.2. 在分解后的数据上进行过滤
			filtered_gdf_proj = exploded_gdf_proj[exploded_gdf_proj.geometry.area >= min_area_threshold_m2]

			final_count = len(filtered_gdf_proj)
			print(f"INFO: 过滤前有 {initial_count} 个独立区域，过滤后保留 {final_count} 个。")

			if filtered_gdf_proj.empty:
				print(f"INFO: 为 {name} 过滤后没有剩余区域。")
				results[name] = output_name
				gpd.GeoDataFrame(geometry=[], crs="EPSG:4326").to_file(output_path, driver='GeoJSON')
				continue

			# 6. 转换回 WGS84 并保存结果
			final_gdf_wgs84 = filtered_gdf_proj.to_crs("EPSG:4326")
			final_gdf_wgs84.to_file(output_path, driver='GeoJSON')

			results[name] = output_name
			print(f"✅ 成功处理 {name}，结果保存至 {output_name}.geojson")

		except Exception as e:
			print(f"ERROR: 处理 {name} 时发生错误: {e}")
			results[name] = f"Error: {str(e)}"

	return results
