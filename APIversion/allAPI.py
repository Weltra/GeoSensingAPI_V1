import json
import traceback

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Union, Dict, Optional, Tuple, Literal
import geopandas as gpd
from shapely.ops import unary_union
from shapely.geometry import shape,mapping

from GeoPandasTool.area import area
from GeoPandasTool.boundary import boundary
from GeoPandasTool.bounds import bounds
from GeoPandasTool.buffer import buffer
from GeoPandasTool.centroid import centroid
from GeoPandasTool.clip_by_rect import clip_by_rect
from GeoPandasTool.concave_hull import concave_hull
from GeoPandasTool.contains import contains
from GeoPandasTool.contains_properly import contains_properly
from GeoPandasTool.convex_hull import convex_hull
from GeoPandasTool.covered_by import covered_by
from GeoPandasTool.covers import covers
from GeoPandasTool.crosses import crosses
from GeoPandasTool.difference import difference
from GeoPandasTool.disjoint import disjoint
from GeoPandasTool.distance import distance
from GeoPandasTool.dwithin import dwithin
from GeoPandasTool.envelope import envelope
from GeoPandasTool.exterior import exterior
from GeoPandasTool.filter_sliver_polygons import filter_sliver_polygons
from GeoPandasTool.geom_almost_equal import geom_almost_equal
from GeoPandasTool.geom_equals import geom_equals
from GeoPandasTool.geom_equals_exact import geom_equals_exact
from GeoPandasTool.intersection import intersection
from GeoPandasTool.intersects import intersects
from GeoPandasTool.is_ccw import is_ccw
from GeoPandasTool.is_closed import is_closed
from GeoPandasTool.is_empty import is_empty
from GeoPandasTool.is_ring import is_ring
from GeoPandasTool.is_simple import is_simple
from GeoPandasTool.is_valid import is_valid
from GeoPandasTool.is_valid_reason import is_valid_reason
from GeoPandasTool.length import length
from GeoPandasTool.line_merge import line_merge
from GeoPandasTool.minimum_bounding_radius import minimum_bounding_radius
from GeoPandasTool.offset_curve import offset_curve
from GeoPandasTool.overlaps import overlaps
from GeoPandasTool.remove_repeated_points import remove_repeated_points
from GeoPandasTool.reverse import reverse
from GeoPandasTool.rotate import rotate
from GeoPandasTool.scale import scale
from GeoPandasTool.shortest_line import shortest_line_between_two
from GeoPandasTool.simplify import simplify
from GeoPandasTool.symmetric_difference import symmetric_difference
from GeoPandasTool.total_bounds import total_bounds
from GeoPandasTool.touches import touches
from GeoPandasTool.union import union
from GeoPandasTool.within import within
from GeoPandasTool.translate import translate
from satelliteTool.getPlaceBoundary import get_boundary
from satelliteTool.get_orbit_radius import get_orbit_radius
from satelliteTool.get_orbit_velocity import calculate_velocity
from satelliteTool.find_Satellite import get_valid_satellite_tle_as_dict
from satelliteTool.get_observation_overlap import get_observation_overlap
from DeployTool.satellite_observation_planner import plan_satellite_combination
from DeployTool.UAV_GS_planner import run_planning_scenario

app = FastAPI()


# === 获取TLE  ===
class TLERequest(BaseModel):
    satellite_names: Union[str, List[str]]


class TLEResponse(BaseModel):
    data: Dict[str, str]


@app.post("/get_tle", response_model=TLEResponse)
def fetch_tle(request: TLERequest):
    """
    通过卫星名称获取 TLE 数据。
    支持单个名称（字符串）或多个名称（列表）。
    """
    tle_data = get_tle(request.satellite_names)
    return {"data": tle_data}


# === 获取 GeoJSON 边界 ===
class BoundaryRequest(BaseModel):
    place_names: Union[str, List[str]]


class BoundaryResponse(BaseModel):
    data: Dict[str, str]


@app.post("/get_boundary", response_model=BoundaryResponse)
def fetch_boundary(request: BoundaryRequest):
    """
    通过地名获取行政边界 GeoJSON 文件路径。
    支持单个名称（字符串）或多个名称（列表）。
    """
    boundary_data = get_boundary(request.place_names)
    return {"data": boundary_data}


class VelocityRequest(BaseModel):
    tle_dict: Dict[str, str]

# 返回体，字典形式：{name: velocity}
class VelocityResponse(BaseModel):
    velocities: Dict[str, float]

@app.post("/calculate_velocity", response_model=VelocityResponse)
def velocity_api(req: VelocityRequest):
    try:
        result = calculate_velocity(req.tle_dict)
        # 过滤掉解析失败的None，抛出异常或者改为0，根据需要调整
        if any(v is None for v in result.values()):
            raise ValueError("部分 TLE 数据无效或解析失败。")
        return {"velocities": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 定义请求体和响应体
class OrbitRadiusRequest(BaseModel):
    tle_dict: Dict[str, str]

class OrbitRadiusResponse(BaseModel):
    orbit_radii: Dict[str, float]


# 注册接口
@app.post("/calculate_orbit_radius", response_model=OrbitRadiusResponse)
def orbit_radius_api(req: OrbitRadiusRequest):
    try:
        result = get_orbit_radius(req.tle_dict)
        # 判断是否有None，视需求决定是否抛错
        if any(v is None for v in result.values()):
            raise ValueError("部分 TLE 数据无效或解析失败。")
        return {"orbit_radii": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AreaRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/area")
def compute_area(req: AreaRequest):
    """
    接收地名-GeoJSON路径字典，计算每个地名对应文件中 Polygon / MultiPolygon 的总面积（平方米）
    """
    try:
        # 提取路径列表
        paths = list(req.place_geojson_dict.values())
        # 调用原函数
        result = area(paths)
        # 将结果转换为地名-结果的字典
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            if geojson_path in result:
                place_result_dict[place_name] = result[geojson_path]
            else:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class BoundaryRequest_1(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径
    multiInvocation: bool = False      # 是否多输入处理

@app.post("/boundary")
def compute_boundary(req: BoundaryRequest_1):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的边界线集合（boundary）
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = boundary(geojson_str, multiInvocation=req.multiInvocation, times=1)

                # 结果为 GeoSeries，统一转为 GeoJSON
                result_geojson = json.loads(gpd.GeoSeries(result).to_json())
                place_result_dict[place_name] = result_geojson
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class BoundsRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径
    multiInvocation: bool = False      # 是否处理多个输入

@app.post("/bounds")
def compute_bounds(req: BoundsRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的边界包围盒坐标（minx, miny, maxx, maxy）
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = bounds(geojson_str, multiInvocation=req.multiInvocation, times=1)

                # pandas.DataFrame → dict 格式化
                if isinstance(result, list):
                    serialized = result
                else:
                    serialized = result.to_dict(orient="records")

                place_result_dict[place_name] = serialized
            except Exception as e:
                place_result_dict[place_name] = None

        return place_result_dict

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class BufferRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径
    distance: float

@app.post("/buffer")
def compute_buffer(req: BufferRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的缓冲区，并返回缓冲后的 GeoJSON 字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = buffer(geojson_str, req.distance)
                place_result_dict[place_name] = json.loads(result)
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CentroidRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/centroid")
def compute_centroid(req: CentroidRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的质心（centroid）
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = centroid(geojson_str)
                place_result_dict[place_name] = json.loads(result)
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ClipRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径
    xmin: float = Field(..., description="矩形裁剪框左边界")
    ymin: float = Field(..., description="矩形裁剪框下边界")
    xmax: float = Field(..., description="矩形裁剪框右边界")
    ymax: float = Field(..., description="矩形裁剪框上边界")

@app.post("/clip_by_rect")
def clip_geojson(req: ClipRequest):
    """
    裁剪地名-GeoJSON路径字典中每个地名对应的几何对象，使其只保留指定矩形区域内的部分
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = clip_by_rect(geojson_str, req.xmin, req.ymin, req.xmax, req.ymax)
                place_result_dict[place_name] = json.loads(result)
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConcaveHullRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径
    alpha: float = Field(0.05, description="影响凹壳形状的参数，越小越精细，越大越简洁")

@app.post("/concave_hull")
def compute_concave_hull(req: ConcaveHullRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的凹壳（目前代码实际上为凸壳）
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = concave_hull(geojson_str, req.alpha)
                place_result_dict[place_name] = json.loads(result)
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ContainsRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/contains")
def check_contains(req: ContainsRequest):
    """
    判断列表中每对地名对应几何对象的包含关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = contains(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                # 如果字典元素不是2个键值对，跳过
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ContainsProperlyRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/contains-properly")
def check_contains_properly(req: ContainsProperlyRequest):
    """
    判断列表中每对地名对应几何对象的正确包含关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = contains_properly(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConvexHullRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/convex-hull")
def compute_convex_hull(req: ConvexHullRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的凸包，并返回 GeoJSON 格式的结果
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = convex_hull(geojson_str)
                place_result_dict[place_name] = json.loads(result)
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class CoveredByRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/covered-by")
def check_covered_by(req: CoveredByRequest):
    """
    判断列表中每对地名对应几何对象的被覆盖关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = covered_by(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class CoversRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/covers")
def check_covers(req: CoversRequest):
    """
    判断列表中每对地名对应几何对象的覆盖关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = covers(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CrossesRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/crosses")
def check_crosses(req: CrossesRequest):
    """
    判断列表中每对地名对应几何对象的相交关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = crosses(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class DifferenceRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/difference")
def compute_difference(req: DifferenceRequest):
    """
    计算列表中每对地名对应几何对象的差集
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        tasks = []
        for item in req.input_list:
            # 获取字典中的两个键值对
            keys = list(item.keys())
            if len(keys) >= 2:
                # 第一个作为source，第二个作为clip
                task = {
                    "source": item[keys[0]],
                    "clip": item[keys[1]]
                }
                tasks.append(task)
        
        result = difference(tasks)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DisjointRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/disjoint")
def check_disjoint(req: DisjointRequest):
    """
    判断列表中每对地名对应几何对象的不相交关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = disjoint(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class DistanceRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/distance")
def compute_distance(req: DistanceRequest):
    """
    计算列表中每对地名对应几何对象的距离
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    other_geojson = json.loads(geojson_str2)
                    # 提取目标 geometry（支持 FeatureCollection 或 Feature）
                    other_geom = None
                    if other_geojson.get("type") == "FeatureCollection":
                        geoms = [shape(f["geometry"]) for f in other_geojson["features"]]
                        other_geom = unary_union(geoms)
                    elif other_geojson.get("type") == "Feature":
                        other_geom = shape(other_geojson["geometry"])
                    else:
                        result_dict[f"{place1}-{place2}"] = None
                        continue
                    distances = distance(geojson_str1, other_geom)
                    result_dict[f"{place1}-{place2}"] = distances
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class DWithinRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径
    distance: float  # 距离阈值（单位取决于坐标系）

@app.post("/dwithin")
def dwithin_api(req: DWithinRequest):
    """
    判断列表中每对地名对应几何对象是否在指定距离内
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = dwithin(geojson_str1, geojson_str2, req.distance)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class EnvelopeRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/envelope")
def envelope_api(req: EnvelopeRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的外包络矩形。
    返回的是每个地名的最小外接矩形FeatureCollection。
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = envelope(geojson_str)
                place_result_dict[place_name] = json.loads(result)
            except Exception as e:
                place_result_dict[place_name] = None
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ExteriorRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/exterior")
def exterior_api(req: ExteriorRequest):
    """
    提取地名-GeoJSON路径字典中每个地名对应Polygon/MultiPolygon几何的外边界（exterior）。
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                result = exterior(geojson_str)
                serialized = []
                for item in result:
                    if item is None:
                        serialized.append(None)
                    elif isinstance(item, list):
                        serialized.append([json.loads(geom.__geo_interface__.to_json()) for geom in item])
                    else:
                        serialized.append(json.loads(item.__geo_interface__.to_json()))
                place_result_dict[place_name] = serialized
            except Exception as e:
                place_result_dict[place_name] = None
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class GeomAlmostEqualRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径
    tolerance: Optional[float] = 1e-9  # 容差（可选）

# 过滤碎片多边形 API
class FilterSliverPolygonsRequest(BaseModel):
    input_files_dict: Dict[str, str] = Field(..., description="输入字典，键是任务标识符，值是GeoJSON文件路径")
    output_directory: str = Field(..., description="输出目录路径")
    min_area_threshold_m2: float = Field(100.0, description="最小面积阈值（平方米），默认100.0")

class FilterSliverPolygonsResponse(BaseModel):
    success: bool
    cleaned_results: Optional[Dict[str, str]]
    message: str

@app.post("/filter_sliver_polygons", response_model=FilterSliverPolygonsResponse)
def filter_sliver_polygons_api(request: FilterSliverPolygonsRequest):
    """
    对输入的GeoJSON文件进行面积过滤，移除面积过小的碎片多边形。
    
    参数:
    - input_files_dict: 输入字典，键是任务标识符，值是GeoJSON文件路径
    - output_directory: 输出目录路径
    - min_area_threshold_m2: 最小面积阈值（平方米）
    
    返回:
    - success: 是否成功
    - cleaned_results: 过滤后的文件路径字典
    - message: 处理结果消息
    """
    try:
        cleaned_results = filter_sliver_polygons(
            input_files_dict=request.input_files_dict,
            output_directory=request.output_directory,
            min_area_threshold_m2=request.min_area_threshold_m2
        )
        
        # 检查是否有错误
        has_errors = "errors" in cleaned_results
        
        if has_errors:
            return FilterSliverPolygonsResponse(
                success=False,
                cleaned_results=cleaned_results,
                message=f"处理完成，但有 {len(cleaned_results['errors'])} 个错误"
            )
        
        return FilterSliverPolygonsResponse(
            success=True,
            cleaned_results=cleaned_results,
            message=f"成功过滤 {len(cleaned_results)} 个文件"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/geom_almost_equal")
def geom_almost_equal_api(req: GeomAlmostEqualRequest):
    """
    判断列表中每对地名对应几何对象是否几乎相等
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = geom_almost_equal(geojson_str1, geojson_str2, req.tolerance or 1e-9)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class GeomEqualsRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/geom_equals")
def geom_equals_api(req: GeomEqualsRequest):
    """
    判断列表中每对地名对应几何对象是否相等
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = geom_equals(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class GeomEqualsExactRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径
    tolerance: Optional[float] = 1e-9  # 容差，默认值为 1e-9

@app.post("/geom_equals_exact")
def geom_equals_exact_api(req: GeomEqualsExactRequest):
    """
    判断列表中每对地名对应几何对象是否精确相等
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = geom_equals_exact(geojson_str1, geojson_str2, req.tolerance or 1e-9)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IntersectionRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/intersection")
def intersection_api(req: IntersectionRequest):
    """
    计算列表中每对地名对应几何对象的交集
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = intersection(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = json.loads(result)
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IntersectsRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/intersects")
def intersects_api(req: IntersectsRequest):
    """
    判断列表中每对地名对应几何对象是否相交
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = intersects(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsCCWRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_ccw")
def is_ccw_api(req: IsCCWRequest):
    """
    判断地名-GeoJSON路径字典中每个地名对应几何对象的外环顶点是否为逆时针方向（CCW）。

    请求体:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应是否逆时针的布尔值
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_ccw(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsClosedRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_closed")
def is_closed_api(req: IsClosedRequest):
    """
    判断地名-GeoJSON路径字典中每个地名对应几何对象是否闭合。

    请求体参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应是否闭合的布尔值
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_closed(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsEmptyRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_empty")
def is_empty_api(req: IsEmptyRequest):
    """
    判断地名-GeoJSON路径字典中每个地名对应几何对象是否为空。

    请求体参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应是否为空的布尔值
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_empty(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsRingRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_ring")
def is_ring_api(req: IsRingRequest):
    """
    判断地名-GeoJSON路径字典中每个地名对应LineString几何对象是否是ring（闭合且简单）。

    请求体参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应是否为ring的布尔值
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_ring(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsSimpleRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_simple")
def is_simple_api(req: IsSimpleRequest):
    """
    判断地名-GeoJSON路径字典中每个地名对应几何对象是否为simple（即不自交）

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应是否为simple的布尔值
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_simple(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsValidRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_valid")
def is_valid_api(req: IsValidRequest):
    """
    判断地名-GeoJSON路径字典中每个地名对应几何对象是否是有效的合法几何。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应是否有效的布尔值
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_valid(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class IsValidReasonRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/is_valid_reason")
def is_valid_reason_api(req: IsValidReasonRequest):
    """
    返回地名-GeoJSON路径字典中每个地名对应几何对象合法性检查的原因说明。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    - code: 状态码，0 表示成功
    - data: 地名-结果字典，每个地名对应合法性检查说明
    - message: 返回信息
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = is_valid_reason(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class LengthRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/length")
def length_api(req: LengthRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的长度。

    参数:
        place_geojson_dict: 地名-GeoJSON路径字典

    返回:
        地名-长度列表字典
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = length(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class LineMergeRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/line_merge")
def line_merge_api(req: LineMergeRequest):
    """
    合并地名-GeoJSON路径字典中每个地名对应GeoJSON数据中的LineString线段。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    地名-结果字典，每个地名对应合并后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = line_merge(geojson_str)
                
                # 直接返回字符串，不需要转换为dict
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class MBRRequest(BaseModel):
    place_geojson_dict: Dict[str, str]  # 键为地名，值为对应的GeoJSON路径

@app.post("/minimum_bounding_radius")
def minimum_bounding_radius_api(req: MBRRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应几何对象的最小外接圆半径。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    地名-半径列表字典，每个地名对应最小外接圆半径
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = minimum_bounding_radius(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class OffsetCurveRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")
    distance: float = Field(..., description="偏移距离")
    side: Optional[Literal['left', 'right']] = Field('right', description="偏移方向，left 或 right，默认 right")
    resolution: Optional[int] = Field(16, description="圆弧分割精度，默认16")
    join_style: Optional[int] = Field(1, description="连接样式，1=round, 2=mitre, 3=bevel，默认1")
    mitre_limit: Optional[float] = Field(5.0, description="miter连接样式时的限制，默认5.0")

@app.post("/offset_curve")
def offset_curve_api(req: OffsetCurveRequest):
    """
    生成地名-GeoJSON路径字典中每个地名对应LineString/MultiLineString的offset curve。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典
    - distance: 偏移距离
    - side: 偏移方向，left 或 right，默认 right
    - resolution: 圆弧分割精度，默认16
    - join_style: 连接样式，1=round, 2=mitre, 3=bevel，默认1
    - mitre_limit: miter连接限制，默认5.0

    返回:
    地名-结果字典，每个地名对应偏移后的geometry的WKT表达
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                try:
                    result = offset_curve(
                        geojson_str,
                        distance=req.distance,
                        side=req.side or 'right',
                        resolution=req.resolution or 16,
                        join_style=req.join_style or 1,
                        mitre_limit=req.mitre_limit or 5.0
                    )
                    place_result_dict[place_name] = result
                except ValueError as e:
                    # 如果是几何类型不支持的错误，返回None
                    if "只能用于 LineString 或 MultiLineString" in str(e):
                        place_result_dict[place_name] = None
                    else:
                        raise e
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class OverlapsRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/overlaps")
def overlaps_api(req: OverlapsRequest):
    """
    判断列表中每对地名对应几何对象是否重叠
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = overlaps(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class RemoveRepeatedPointsRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")

@app.post("/remove_repeated_points")
def remove_repeated_points_api(req: RemoveRepeatedPointsRequest):
    """
    移除地名-GeoJSON路径字典中每个地名对应GeoJSON数据中的重复点。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    地名-结果字典，每个地名对应去除重复点后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = remove_repeated_points(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"处理失败: {str(e)}")

class ReverseRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")

@app.post("/reverse")
def reverse_api(req: ReverseRequest):
    """
    反转地名-GeoJSON路径字典中每个地名对应GeoJSON中几何对象的坐标顺序。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    地名-结果字典，每个地名对应反转后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = reverse(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class RotateRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")
    angle: float = Field(..., description="旋转角度（默认为度，use_radians=True 时为弧度）")
    origin: Union[str, Tuple[float, float]] = Field('centroid', description="旋转中心，可为 'centroid'、'center' 或指定坐标 (x, y)")
    use_radians: bool = Field(False, description="是否使用弧度进行旋转")

@app.post("/rotate")
def rotate_api(req: RotateRequest):
    """
    旋转地名-GeoJSON路径字典中每个地名对应GeoJSON中几何对象。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典
    - angle: 旋转角度
    - origin: 旋转中心
    - use_radians: 是否使用弧度

    返回:
    地名-结果字典，每个地名对应旋转后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = rotate(geojson_str, angle=req.angle, origin=str(req.origin), use_radians=req.use_radians)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ScaleRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")
    xfact: float = Field(1.0, description="x 方向的缩放因子")
    yfact: float = Field(1.0, description="y 方向的缩放因子")
    origin: Union[str, Tuple[float, float]] = Field("center", description="缩放中心，可为 'center', 'centroid', 或 (x, y) 坐标")

@app.post("/scale")
def scale_api(req: ScaleRequest):
    """
    缩放地名-GeoJSON路径字典中每个地名对应GeoJSON中几何对象。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典
    - xfact: x 方向缩放因子
    - yfact: y 方向缩放因子
    - origin: 缩放中心

    返回:
    地名-结果字典，每个地名对应缩放后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = scale(geojson_str, xfact=req.xfact, yfact=req.yfact, origin=str(req.origin))
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ShortestLineRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/shortest_line_between_two")
def shortest_line_api(req: ShortestLineRequest):
    """
    计算列表中每对地名对应几何对象之间的最短连接线
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = shortest_line_between_two(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result  # 直接返回字符串
                except Exception as e:
                    print(f"shortest_line_between_two内部异常: {e}")
                    traceback.print_exc()
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        print(f"shortest_line_between_two接口异常: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

class SimplifyRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")
    tolerance: Optional[float] = Field(0.01, description="简化程度，值越大简化越明显")
    preserve_topology: Optional[bool] = Field(True, description="是否保持拓扑结构")

@app.post("/simplify")
def simplify_api(req: SimplifyRequest):
    """
    简化地名-GeoJSON路径字典中每个地名对应GeoJSON中几何对象。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典
    - tolerance: 简化容差
    - preserve_topology: 是否保持拓扑结构

    返回:
    地名-结果字典，每个地名对应简化后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = simplify(geojson_str, tolerance=req.tolerance or 0.01, preserve_topology=req.preserve_topology or True)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"简化失败: {str(e)}")

class SymmetricDifferenceRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/symmetric_difference")
def symmetric_difference_api(req: SymmetricDifferenceRequest):
    """
    计算列表中每对地名对应几何对象的对称差
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = symmetric_difference(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = json.loads(result)
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class TouchesRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/touches")
def touches_api(req: TouchesRequest):
    """
    判断列表中每对地名对应几何对象是否接触
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = touches(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class UnionRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/union")
def union_api(req: UnionRequest):
    """
    计算列表中每对地名对应几何对象的并集
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = union(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = json.loads(result)
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class WithinRequest(BaseModel):
    input_list: List[Dict[str, str]]  # 列表元素为字典，包含两个地名和对应的GeoJSON路径

@app.post("/within")
def within_api(req: WithinRequest):
    """
    判断列表中每对地名对应几何对象的内部关系
    输入格式：[{"place1": "geojson_path1", "place2": "geojson_path2"}, ...]
    输出格式：{"place1-place2": result, ...}
    """
    try:
        result_dict = {}
        for item in req.input_list:
            if len(item) == 2:
                place_names = list(item.keys())
                place1, place2 = place_names[0], place_names[1]
                geojson_path1, geojson_path2 = item[place1], item[place2]
                try:
                    # 读取GeoJSON文件内容
                    with open(geojson_path1, 'r', encoding='utf-8') as f:
                        geojson_str1 = f.read()
                    with open(geojson_path2, 'r', encoding='utf-8') as f:
                        geojson_str2 = f.read()
                    
                    result = within(geojson_str1, geojson_str2)
                    result_dict[f"{place1}-{place2}"] = result
                except Exception as e:
                    result_dict[f"{place1}-{place2}"] = None
            else:
                continue
        return result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class TranslateRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")
    xoff: float = Field(0.0, description="x 方向的偏移量")
    yoff: float = Field(0.0, description="y 方向的偏移量")

@app.post("/translate")
def translate_api(req: TranslateRequest):
    """
    平移地名-GeoJSON路径字典中每个地名对应GeoJSON中几何对象。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典
    - xoff: x 方向的偏移量
    - yoff: y 方向的偏移量

    返回:
    地名-结果字典，每个地名对应平移后的GeoJSON字符串
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = translate(geojson_str, xoff=req.xoff, yoff=req.yoff)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class TotalBoundsRequest(BaseModel):
    place_geojson_dict: Dict[str, str] = Field(..., description="地名-GeoJSON路径字典")

@app.post("/total_bounds")
def total_bounds_api(req: TotalBoundsRequest):
    """
    计算地名-GeoJSON路径字典中每个地名对应GeoJSON中所有geometry的整体包围盒。

    请求参数:
    - place_geojson_dict: 地名-GeoJSON路径字典

    返回:
    地名-结果字典，每个地名对应整体包围盒坐标 [minx, miny, maxx, maxy]
    """
    try:
        place_result_dict = {}
        for place_name, geojson_path in req.place_geojson_dict.items():
            try:
                # 读取GeoJSON文件内容
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    geojson_str = f.read()
                
                # 调用原函数
                result = total_bounds(geojson_str)
                place_result_dict[place_name] = result
            except Exception as e:
                place_result_dict[place_name] = None
        
        return place_result_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# 获取卫星TLE数据 API
class SatelliteTLERequest(BaseModel):
    satellite_db_path: str = Field(..., description="卫星数据库路径")
    mission_theme: str = Field("Land cover", description="任务主题")
    sensor_type: str = Field("Optical Sensor", description="传感器类型")

class SatelliteTLEResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, str]]
    message: str

@app.post("/get_satellite_tle", response_model=SatelliteTLEResponse)
def get_satellite_tle_api(request: SatelliteTLERequest):
    """
    从数据库获取符合条件的卫星TLE数据
    """
    try:
        tle_data = get_valid_satellite_tle_as_dict(
            satellite_db_path=request.satellite_db_path,
            mission_theme=request.mission_theme,
            sensor_type=request.sensor_type
        )
        
        if not tle_data:
            return SatelliteTLEResponse(
                success=False,
                data=None,
                message="未找到符合条件的卫星TLE数据"
            )
        
        return SatelliteTLEResponse(
            success=True,
            data=tle_data,
            message=f"成功获取 {len(tle_data)} 颗卫星的TLE数据"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 计算卫星观测重叠率 API
class ObservationOverlapRequest(BaseModel):
    tle_dict: Dict[str, str] = Field(..., description="卫星TLE数据字典")
    start_time_str: str = Field(..., description="开始时间字符串")
    end_time_str: str = Field(..., description="结束时间字符串")
    target_geojson_path: str = Field(..., description="目标区域GeoJSON文件路径")
    fov: float = Field(10.0, description="视场角度")
    interval_seconds: int = Field(600, description="时间间隔（秒）")
    output_dir: str = Field(..., description="输出目录")

class ObservationOverlapResponse(BaseModel):
    success: bool
    coverage_results: Optional[Dict]
    message: str

@app.post("/get_observation_overlap", response_model=ObservationOverlapResponse)
def get_observation_overlap_api(request: ObservationOverlapRequest):
    """
    计算卫星观测重叠率
    """
    try:
        coverage_results = get_observation_overlap(
            tle_dict=request.tle_dict,
            start_time_str=request.start_time_str,
            end_time_str=request.end_time_str,
            target_geojson_path=request.target_geojson_path,
            fov=request.fov,
            interval_seconds=request.interval_seconds,
            output_dir=request.output_dir
        )
        
        if not coverage_results:
            return ObservationOverlapResponse(
                success=False,
                coverage_results=None,
                message="在指定时间段内，没有卫星与目标区域发生重叠"
            )
        
        return ObservationOverlapResponse(
            success=True,
            coverage_results=coverage_results,
            message="成功计算卫星观测重叠率"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 规划卫星方案 API
class SatellitePlanningRequest(BaseModel):
    coverage_results: Dict = Field(..., description="覆盖率计算结果")
    target_geojson_path: str = Field(..., description="目标区域GeoJSON文件路径")
    target_coverage: float = Field(0.99, description="目标覆盖率")
    output_dir: str = Field(..., description="输出目录")

class SatellitePlanningResponse(BaseModel):
    success: bool
    report: Optional[Dict]
    intersection_path: Optional[str]
    map_path: Optional[str]
    message: str

@app.post("/plan_satellite_combination", response_model=SatellitePlanningResponse)
def plan_satellite_combination_api(request: SatellitePlanningRequest):
    """
    规划卫星方案并生成报告
    """
    try:
        sat_plan_results = plan_satellite_combination(
            coverage_results=request.coverage_results,
            target_geojson_path=request.target_geojson_path,
            target_coverage=request.target_coverage,
            output_dir=request.output_dir
        )
        
        return SatellitePlanningResponse(
            success=sat_plan_results.get('success', False),
            report=sat_plan_results.get('report'),
            intersection_path=sat_plan_results.get('intersection_path'),
            map_path=sat_plan_results.get('map_path'),
            message="卫星方案规划完成"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 无人机协同规划 API
class UAVPlanningRequest(BaseModel):
    geojson_path: str = Field(..., description="目标区域GeoJSON文件路径")
    output_dir: str = Field("planning_results", description="输出目录")
    create_map: bool = Field(True, description="是否创建地图")
    verbose: bool = Field(True, description="是否详细输出")
    UAV_db_path: str = Field("UAV_data.db", description="无人机数据库路径")
    stations_db_path: str = Field("Stations_data.db", description="地面站数据库路径")

class UAVPlanningResponse(BaseModel):
    success: bool
    results_data: Optional[Dict]
    message: str

@app.post("/run_UAV_GS_planning", response_model=UAVPlanningResponse)
def run_uav_planning_api(request: UAVPlanningRequest):
    """
    执行无人机和地面站协同规划
    """
    try:
        results_data = run_planning_scenario(
            geojson_path=request.geojson_path,
            output_dir=request.output_dir,
            create_map=request.create_map,
            verbose=request.verbose,
            UAV_db_path=request.UAV_db_path,
            stations_db_path=request.stations_db_path
        )
        
        if not results_data:
            return UAVPlanningResponse(
                success=False,
                results_data=None,
                message="无人机规划失败"
            )
        
        return UAVPlanningResponse(
            success=True,
            results_data=results_data,
            message="无人机协同规划完成"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))