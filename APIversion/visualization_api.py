# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI 
FILE_NAME: visualization_api.py
AUTHOR: welt 
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-01-27 
DESCRIPTION: 通用地理空间可视化API，支持卫星、无人机、地面站等多种要素的综合可视化
"""

import json
import os
import random
import traceback
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

import matplotlib.pyplot as plt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 尝试导入可视化库
try:
    import folium
    import geopandas as gpd
    VISUALIZATION_ENABLED = True
except ImportError:
    VISUALIZATION_ENABLED = False
    folium = None
    gpd = None

app = FastAPI(title="VisualizationTool API", description="通用地理空间可视化API")

# === 数据模型定义 ===

class MapConfig(BaseModel):
    """地图配置"""
    tiles: str = Field(default="CartoDB positron", description="地图瓦片类型")
    zoom_start: int = Field(default=10, description="初始缩放级别")
    auto_fit_bounds: bool = Field(default=True, description="是否自动缩放到目标区域")

class SatelliteConfig(BaseModel):
    """卫星配置"""
    name: str = Field(description="卫星名称")
    geojson_path: Optional[str] = Field(default=None, description="卫星覆盖GeoJSON文件路径")
    color: Optional[str] = Field(default=None, description="自定义颜色")
    opacity: float = Field(default=0.35, description="填充透明度")

class UAVConfig(BaseModel):
    """无人机配置"""
    uav_id: str = Field(description="无人机ID")
    assigned_area_path: Optional[str] = Field(default=None, description="分配区域GeoJSON路径")
    flight_path_path: Optional[str] = Field(default=None, description="飞行路径GeoJSON路径")
    coverage_area_path: Optional[str] = Field(default=None, description="覆盖区域GeoJSON路径")
    color: Optional[str] = Field(default=None, description="自定义颜色")

class GroundStationConfig(BaseModel):
    """地面站配置"""
    station_id: str = Field(description="地面站ID")
    coords_latlon: List[float] = Field(description="坐标 [经度, 纬度]")
    radius_m: float = Field(default=5000, description="覆盖半径(米)")
    color: str = Field(default="red", description="颜色")

class VisualizationRequest(BaseModel):
    """可视化请求"""
    # 基础配置
    target_geojson_path: str = Field(description="目标区域GeoJSON文件路径")
    output_html_path: str = Field(description="输出HTML文件路径")
    map_config: MapConfig = Field(default_factory=MapConfig, description="地图配置")
    
    # 卫星数据
    satellite_plan: Optional[Dict[str, Any]] = Field(default=None, description="卫星规划数据")
    satellite_configs: Optional[List[SatelliteConfig]] = Field(default=None, description="卫星配置列表")
    satellite_geojson_dir: str = Field(default="geojson", description="卫星GeoJSON文件目录")
    
    # 无人机数据
    uav_results: Optional[Dict[str, Any]] = Field(default=None, description="无人机规划结果")
    uav_configs: Optional[List[UAVConfig]] = Field(default=None, description="无人机配置列表")
    planning_summary_path: Optional[str] = Field(default=None, description="规划摘要文件路径")
    
    # 地面站数据
    ground_station_configs: Optional[List[GroundStationConfig]] = Field(default=None, description="地面站配置列表")
    
    # 其他图层
    uncovered_geojson_path: Optional[str] = Field(default=None, description="未覆盖区域GeoJSON路径")
    additional_layers: Optional[List[Dict[str, Any]]] = Field(default=None, description="额外图层配置")
    
    # 显示选项
    show_boundary: bool = Field(default=True, description="是否显示目标区域边界")
    show_satellites: bool = Field(default=True, description="是否显示卫星覆盖")
    show_uavs: bool = Field(default=True, description="是否显示无人机")
    show_ground_stations: bool = Field(default=True, description="是否显示地面站")
    show_uncovered: bool = Field(default=True, description="是否显示未覆盖区域")

class VisualizationResponse(BaseModel):
    """可视化响应"""
    success: bool
    message: str
    output_path: Optional[str] = None
    error_details: Optional[str] = None

# === 辅助函数 ===

def get_random_color():
    """生成一个随机的十六进制颜色代码"""
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))

def find_satellite_geojson(satellite_name: str, geojson_dir: str) -> Optional[str]:
    """查找卫星GeoJSON文件"""
    safe_name = "".join(c for c in satellite_name if c.isalnum() or c in (' ', '-')).rstrip().replace(' ', '_')
    
    possible_paths = [
        os.path.join(geojson_dir, f"{safe_name}_overlap.geojson"),
        os.path.join(geojson_dir, f"{satellite_name}_overlap.geojson"),
        os.path.join(geojson_dir, f"intersection_{satellite_name}.geojson"),
        os.path.join(geojson_dir, f"{satellite_name}_intersection.geojson"),
        os.path.join(geojson_dir, f"{satellite_name}_coverage.geojson"),
        os.path.join(geojson_dir, f"{satellite_name}.geojson"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def extract_satellites_from_plan(satellite_plan: Dict[str, Any]) -> List[str]:
    """从卫星规划中提取卫星名称列表"""
    satellites = []
    
    # 尝试不同的卫星数据结构
    if 'satellites' in satellite_plan:
        satellites = satellite_plan['satellites']
    elif 'selected_satellites' in satellite_plan:
        satellites = satellite_plan['selected_satellites']
    elif 'satellite_list' in satellite_plan:
        satellites = satellite_plan['satellite_list']
    
    # 处理不同的卫星数据格式
    satellite_names = []
    for i, sat_info in enumerate(satellites):
        if isinstance(sat_info, str):
            satellite_names.append(sat_info)
        elif isinstance(sat_info, dict):
            name = sat_info.get('name', sat_info.get('satellite_name', f"Satellite_{i}"))
            satellite_names.append(name)
        else:
            satellite_names.append(f"Satellite_{i}")
    
    return satellite_names

# === API端点 ===

@app.post("/create_comprehensive_visualization", response_model=VisualizationResponse)
def create_comprehensive_visualization(request: VisualizationRequest):
    """
    创建综合可视化地图，支持卫星、无人机、地面站等多种要素
    
    这个API将原有的create_comprehensive_visualization函数封装为通用的API接口，
    支持灵活配置各种可视化要素和样式。
    """
    
    if not VISUALIZATION_ENABLED:
        return VisualizationResponse(
            success=False,
            message="可视化功能不可用：缺少 folium 或 geopandas 库。请运行 'pip install folium geopandas' 安装。"
        )
    
    try:
        # 验证输入文件
        if not os.path.exists(request.target_geojson_path):
            raise HTTPException(status_code=400, detail=f"目标区域文件不存在: {request.target_geojson_path}")
        
        # 确保输出目录存在
        output_dir = os.path.dirname(request.output_html_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 1. 初始化地图
        target_gdf = gpd.read_file(request.target_geojson_path, encoding='utf-8')
        center_y, center_x = target_gdf.union_all().centroid.xy
        map_center = [center_y[0], center_x[0]]
        
        # 计算边界范围
        bounds = target_gdf.total_bounds  # [minx, miny, maxx, maxy]
        
        # 创建地图
        m = folium.Map(
            location=map_center, 
            zoom_start=request.map_config.zoom_start, 
            tiles=request.map_config.tiles
        )
        
        # 2. 添加目标区域边界
        if request.show_boundary:
            folium.GeoJson(
                target_gdf,
                name='目标区域边界',
                style_function=lambda x: {'color': 'black', 'weight': 2.5, 'fillOpacity': 0.05}
            ).add_to(m)
        
        # 3. 添加卫星覆盖范围
        if request.show_satellites:
            satellite_colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0']
            
            # 从卫星规划中提取卫星信息
            if request.satellite_plan:
                satellite_names = extract_satellites_from_plan(request.satellite_plan)
                
                for i, sat_name in enumerate(satellite_names):
                    sat_geojson_path = find_satellite_geojson(sat_name, request.satellite_geojson_dir)
                    
                    if sat_geojson_path:
                        color = satellite_colors[i % len(satellite_colors)]
                        folium.GeoJson(
                            sat_geojson_path,
                            name=f"{sat_name}",
                            style_function=lambda x, c=color: {
                                'weight': 0, 'fillColor': c, 'fillOpacity': 0.35
                            },
                            tooltip=f"<b>{sat_name}</b><br>卫星覆盖区域"
                        ).add_to(m)
            
            # 从配置中添加卫星
            if request.satellite_configs:
                for i, sat_config in enumerate(request.satellite_configs):
                    if sat_config.geojson_path and os.path.exists(sat_config.geojson_path):
                        color = sat_config.color or satellite_colors[i % len(satellite_colors)]
                        folium.GeoJson(
                            sat_config.geojson_path,
                            name=sat_config.name,
                            style_function=lambda x, c=color, o=sat_config.opacity: {
                                'weight': 0, 'fillColor': c, 'fillOpacity': o
                            },
                            tooltip=f"<b>{sat_config.name}</b><br>卫星覆盖区域"
                        ).add_to(m)
        
        # 4. 添加无人机相关图层
        if request.show_uavs and request.uav_results and request.uav_results.get('success'):
            # 从规划摘要文件中读取详细信息
            planning_summary_path = request.planning_summary_path or os.path.join("geojson", "Wuhan_difference_filtered_planning_summary.json")
            
            if os.path.exists(planning_summary_path):
                with open(planning_summary_path, 'r', encoding='utf-8') as f:
                    planning_data = json.load(f)
                
                uav_results_list = planning_data.get('uav_results', [])
                colors = plt.cm.get_cmap('viridis', len(uav_results_list))
                
                for i, uav_info in enumerate(uav_results_list):
                    uav_id = uav_info.get('uav_id', 'Unknown')
                    color_hex = plt.cm.colors.to_hex(colors(i))
                    
                    # 创建无人机图层组
                    uav_group = folium.FeatureGroup(name=f"无人机{uav_id}(DJI Matrice 400)", show=True).add_to(m)
                    
                    # 添加分配区域
                    assigned_area_path = uav_info.get('assigned_area_geojson_path', '')
                    if assigned_area_path and os.path.exists(assigned_area_path):
                        assigned_gdf = gpd.read_file(assigned_area_path, encoding='utf-8')
                        folium.GeoJson(
                            assigned_gdf,
                            style_function=lambda x, c=color_hex: {
                                'color': c, 'weight': 1.5, 'fillColor': c, 'fillOpacity': 0.25
                            },
                            tooltip=f'无人机 {uav_id} 分配区域'
                        ).add_to(uav_group)
                    
                    # 添加飞行路径
                    flight_path_path = uav_info.get('flight_path_geojson_path', '')
                    if flight_path_path and os.path.exists(flight_path_path):
                        flight_gdf = gpd.read_file(flight_path_path, encoding='utf-8')
                        folium.GeoJson(
                            flight_gdf,
                            style_function=lambda x, c=color_hex: {
                                'color': c, 'weight': 2.5
                            },
                            tooltip=f"无人机 {uav_id} 飞行路径"
                        ).add_to(uav_group)
                    
                    # 添加覆盖区域
                    coverage_path = uav_info.get('coverage_area_geojson_path', '')
                    if coverage_path and os.path.exists(coverage_path):
                        coverage_gdf = gpd.read_file(coverage_path, encoding='utf-8')
                        folium.GeoJson(
                            coverage_gdf,
                            style_function=lambda x, c=color_hex: {
                                'fillColor': c, 'fillOpacity': 0.4, 'color': 'transparent'
                            },
                            tooltip=f'无人机 {uav_id} 覆盖范围'
                        ).add_to(uav_group)
            
            # 从配置中添加无人机
            if request.uav_configs:
                for i, uav_config in enumerate(request.uav_configs):
                    color = uav_config.color or get_random_color()
                    uav_group = folium.FeatureGroup(name=f"无人机{uav_config.uav_id}", show=True).add_to(m)
                    
                    # 添加分配区域
                    if uav_config.assigned_area_path and os.path.exists(uav_config.assigned_area_path):
                        assigned_gdf = gpd.read_file(uav_config.assigned_area_path, encoding='utf-8')
                        folium.GeoJson(
                            assigned_gdf,
                            style_function=lambda x, c=color: {
                                'color': c, 'weight': 1.5, 'fillColor': c, 'fillOpacity': 0.25
                            },
                            tooltip=f'无人机 {uav_config.uav_id} 分配区域'
                        ).add_to(uav_group)
                    
                    # 添加飞行路径
                    if uav_config.flight_path_path and os.path.exists(uav_config.flight_path_path):
                        flight_gdf = gpd.read_file(uav_config.flight_path_path, encoding='utf-8')
                        folium.GeoJson(
                            flight_gdf,
                            style_function=lambda x, c=color: {
                                'color': c, 'weight': 2.5
                            },
                            tooltip=f"无人机 {uav_config.uav_id} 飞行路径"
                        ).add_to(uav_group)
                    
                    # 添加覆盖区域
                    if uav_config.coverage_area_path and os.path.exists(uav_config.coverage_area_path):
                        coverage_gdf = gpd.read_file(uav_config.coverage_area_path, encoding='utf-8')
                        folium.GeoJson(
                            coverage_gdf,
                            style_function=lambda x, c=color: {
                                'fillColor': c, 'fillOpacity': 0.4, 'color': 'transparent'
                            },
                            tooltip=f'无人机 {uav_config.uav_id} 覆盖范围'
                        ).add_to(uav_group)
        
        # 5. 添加地面站
        if request.show_ground_stations:
            # 从规划摘要中添加地面站
            if request.uav_results and request.uav_results.get('success'):
                planning_summary_path = request.planning_summary_path or os.path.join("geojson", "Wuhan_difference_filtered_planning_summary.json")
                
                if os.path.exists(planning_summary_path):
                    with open(planning_summary_path, 'r', encoding='utf-8') as f:
                        planning_data = json.load(f)
                    
                    ground_station_info = planning_data.get('ground_station_contribution', {})
                    if ground_station_info:
                        stations_details = ground_station_info.get('stations_details', [])
                        
                        gs_group = folium.FeatureGroup(name="地面站", show=True).add_to(m)
                        
                        for station in stations_details:
                            coords = station.get('coords_latlon', [])
                            if len(coords) >= 2:
                                lat, lon = coords[1], coords[0]  # 转换为[纬度, 经度]
                                radius = station.get('radius_m', 0)
                                
                                folium.Marker(
                                    location=[lat, lon],
                                    popup=f"地面站ID: {station.get('id', 'Unknown')}<br>半径: {radius} m",
                                    icon=folium.Icon(color='red', icon='broadcast-tower', prefix='fa')
                                ).add_to(gs_group)
                                
                                folium.Circle(
                                    location=[lat, lon],
                                    radius=radius,
                                    color='red',
                                    fill=True,
                                    fillColor='red',
                                    fillOpacity=0.3,
                                    weight=2,
                                    tooltip=f"地面站覆盖范围<br>半径: {radius/1000:.1f} km"
                                ).add_to(gs_group)
            
            # 从配置中添加地面站
            if request.ground_station_configs:
                gs_group = folium.FeatureGroup(name="地面站", show=True).add_to(m)
                
                for gs_config in request.ground_station_configs:
                    if len(gs_config.coords_latlon) >= 2:
                        lat, lon = gs_config.coords_latlon[1], gs_config.coords_latlon[0]  # 转换为[纬度, 经度]
                        
                        folium.Marker(
                            location=[lat, lon],
                            popup=f"地面站ID: {gs_config.station_id}<br>半径: {gs_config.radius_m} m",
                            icon=folium.Icon(color=gs_config.color, icon='broadcast-tower', prefix='fa')
                        ).add_to(gs_group)
                        
                        folium.Circle(
                            location=[lat, lon],
                            radius=gs_config.radius_m,
                            color=gs_config.color,
                            fill=True,
                            fillColor=gs_config.color,
                            fillOpacity=0.3,
                            weight=2,
                            tooltip=f"地面站覆盖范围<br>半径: {gs_config.radius_m/1000:.1f} km"
                        ).add_to(gs_group)
        
        # 6. 添加未覆盖区域
        if request.show_uncovered and request.uncovered_geojson_path and os.path.exists(request.uncovered_geojson_path):
            with open(request.uncovered_geojson_path, 'r', encoding='utf-8') as f:
                uncovered_data = json.load(f)
            folium.GeoJson(
                uncovered_data,
                name='未覆盖区域',
                style_function=lambda x: {'color': 'red', 'weight': 2, 'dashArray': '5, 5', 'fillOpacity': 0.0},
                tooltip="未覆盖区域<br>需要补全的区域"
            ).add_to(m)
        
        # 7. 添加额外图层
        if request.additional_layers:
            for layer_config in request.additional_layers:
                layer_name = layer_config.get('name', '额外图层')
                geojson_path = layer_config.get('geojson_path')
                style_config = layer_config.get('style', {})
                
                if geojson_path and os.path.exists(geojson_path):
                    folium.GeoJson(
                        geojson_path,
                        name=layer_name,
                        style_function=lambda x, style=style_config: style,
                        tooltip=layer_config.get('tooltip', layer_name)
                    ).add_to(m)
        
        # 8. 自动缩放和保存
        if request.map_config.auto_fit_bounds:
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])  # [[min_lat, min_lon], [max_lat, max_lon]]
        
        folium.LayerControl(collapsed=False).add_to(m)
        m.save(request.output_html_path)
        
        return VisualizationResponse(
            success=True,
            message="综合可视化地图生成成功",
            output_path=request.output_html_path
        )
        
    except Exception as e:
        error_msg = f"生成可视化地图时发生错误: {str(e)}"
        traceback.print_exc()
        return VisualizationResponse(
            success=False,
            message=error_msg,
            error_details=traceback.format_exc()
        )

@app.post("/create_simple_visualization", response_model=VisualizationResponse)
def create_simple_visualization(
    target_geojson_path: str,
    output_html_path: str,
    additional_geojson_paths: Optional[List[str]] = None,
    layer_names: Optional[List[str]] = None,
    colors: Optional[List[str]] = None
):
    """
    创建简单的可视化地图，只需要目标区域和可选的额外GeoJSON文件
    
    这是一个简化版本的可视化API，适用于快速创建基础地图。
    """
    
    if not VISUALIZATION_ENABLED:
        return VisualizationResponse(
            success=False,
            message="可视化功能不可用：缺少 folium 或 geopandas 库。请运行 'pip install folium geopandas' 安装。"
        )
    
    try:
        # 验证输入文件
        if not os.path.exists(target_geojson_path):
            raise HTTPException(status_code=400, detail=f"目标区域文件不存在: {target_geojson_path}")
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_html_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 初始化地图
        target_gdf = gpd.read_file(target_geojson_path, encoding='utf-8')
        center_y, center_x = target_gdf.union_all().centroid.xy
        map_center = [center_y[0], center_x[0]]
        bounds = target_gdf.total_bounds
        
        m = folium.Map(location=map_center, zoom_start=10, tiles="CartoDB positron")
        
        # 添加目标区域
        folium.GeoJson(
            target_gdf,
            name='目标区域',
            style_function=lambda x: {'color': 'black', 'weight': 2.5, 'fillOpacity': 0.05}
        ).add_to(m)
        
        # 添加额外图层
        if additional_geojson_paths:
            default_colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#46f0f0']
            
            for i, geojson_path in enumerate(additional_geojson_paths):
                if os.path.exists(geojson_path):
                    layer_name = layer_names[i] if layer_names and i < len(layer_names) else f"图层{i+1}"
                    color = colors[i] if colors and i < len(colors) else default_colors[i % len(default_colors)]
                    
                    folium.GeoJson(
                        geojson_path,
                        name=layer_name,
                        style_function=lambda x, c=color: {
                            'weight': 0, 'fillColor': c, 'fillOpacity': 0.35
                        },
                        tooltip=layer_name
                    ).add_to(m)
        
        # 自动缩放和保存
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
        folium.LayerControl(collapsed=False).add_to(m)
        m.save(output_html_path)
        
        return VisualizationResponse(
            success=True,
            message="简单可视化地图生成成功",
            output_path=output_html_path
        )
        
    except Exception as e:
        error_msg = f"生成简单可视化地图时发生错误: {str(e)}"
        return VisualizationResponse(
            success=False,
            message=error_msg,
            error_details=traceback.format_exc()
        )

@app.get("/check_visualization_dependencies")
def check_visualization_dependencies():
    """检查可视化依赖库是否可用"""
    return {
        "visualization_enabled": VISUALIZATION_ENABLED,
        "folium_available": folium is not None,
        "geopandas_available": gpd is not None,
        "message": "可视化功能可用" if VISUALIZATION_ENABLED else "缺少可视化依赖库"
    }

if __name__ == "__main__":
    import uvicorn
    print("启动可视化API服务，请访问 http://127.0.0.1:8001")
    print("API文档地址: http://127.0.0.1:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001)