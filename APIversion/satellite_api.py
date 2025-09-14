import json
import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Union, Dict, Optional, Tuple, Literal

# SatelliteTool imports
from satelliteTool.getPlaceBoundary import get_boundary
from satelliteTool.get_orbit_radius import get_orbit_radius
from satelliteTool.get_orbit_velocity import calculate_velocity
from satelliteTool.find_Satellite import get_valid_satellite_tle_as_dict
from satelliteTool.get_observation_overlap import get_observation_overlap
from satelliteTool.get_observation_lace import get_observation_lace
from satelliteTool.get_satellite_footprint import get_satellite_footprint
from satelliteTool.get_orbit_inclination import get_orbit_inclination
from satelliteTool.satellite_ground_position import satellite_ground_position

app = FastAPI(title="SatelliteTool API", description="卫星工具API")

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


# === SatelliteTool APIs ===

class ObservationLaceRequest(BaseModel):
    tle_dict: Dict[str, str] = Field(..., description="卫星TLE数据字典")
    start_time_str: str = Field(..., description="开始时间字符串")
    end_time_str: str = Field(..., description="结束时间字符串")
    target_geojson_path: str = Field(..., description="目标区域GeoJSON文件路径")
    fov: float = Field(10.0, description="视场角度")
    interval_seconds: int = Field(600, description="时间间隔（秒）")

@app.post("/get_observation_lace")
def get_observation_lace_api(req: ObservationLaceRequest):
    """
    计算多个卫星在指定时间段内的地面覆盖轨迹
    """
    try:
        result = get_observation_lace(
            tle_dict=req.tle_dict,
            start_time_str=req.start_time_str,
            end_time_str=req.end_time_str,
            target_geojson_path=req.target_geojson_path,
            fov=req.fov,
            interval_seconds=req.interval_seconds
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SatelliteFootprintRequest(BaseModel):
    tle_dict: Dict[str, str] = Field(..., description="卫星TLE数据字典，键为卫星名，值为TLE数据")
    start_time_str: str = Field(..., description="开始时间字符串")
    end_time_str: str = Field(..., description="结束时间字符串")
    fov: float = Field(10.0, description="视场角度")

class SatelliteFootprintResponse(BaseModel):
    success: bool
    file_paths: Optional[Dict[str, str]] = Field(None, description="卫星名到文件路径的映射")
    message: str

@app.post("/get_satellite_footprint", response_model=SatelliteFootprintResponse)
def get_satellite_footprint_api(req: SatelliteFootprintRequest):
    """
    计算多个卫星的足迹并保存到全局文件夹
    返回字典，键为卫星名，值为对应的文件路径
    """
    try:
        result_paths = get_satellite_footprint(
            tle_dict=req.tle_dict,
            start_time_str=req.start_time_str,
            end_time_str=req.end_time_str,
            fov=req.fov
        )
        
        # 检查是否有成功的处理结果
        successful_paths = {k: v for k, v in result_paths.items() if v is not None}
        failed_satellites = [k for k, v in result_paths.items() if v is None]
        
        if not successful_paths:
            return SatelliteFootprintResponse(
                success=False,
                file_paths=None,
                message="所有卫星的足迹计算都失败了"
            )
        
        message = f"成功计算 {len(successful_paths)} 颗卫星的足迹"
        if failed_satellites:
            message += f"，{len(failed_satellites)} 颗卫星处理失败: {', '.join(failed_satellites)}"
        
        return SatelliteFootprintResponse(
            success=True,
            file_paths=successful_paths,
            message=message
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class OrbitInclinationRequest(BaseModel):
    tle_data: str = Field(..., description="TLE数据")
    multiInvocation: bool = Field(False, description="是否多输入处理")
    times: int = Field(1, description="处理次数")

@app.post("/get_orbit_inclination")
def get_orbit_inclination_api(req: OrbitInclinationRequest):
    """
    计算卫星轨道倾角
    """
    try:
        result = get_orbit_inclination(
            req.tle_data,
            multiInvocation=req.multiInvocation,
            times=req.times
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SatelliteGroundPositionRequest(BaseModel):
    tle_data: str = Field(..., description="TLE数据")
    timestamp_str: str = Field(..., description="时间戳字符串")
    fov: float = Field(45.0, description="视场角度")

@app.post("/satellite_ground_position")
def satellite_ground_position_api(req: SatelliteGroundPositionRequest):
    """
    计算卫星地面位置
    """
    try:
        result = satellite_ground_position(
            tle_data=req.tle_data,
            timestamp_str=req.timestamp_str,
            fov=req.fov
        )
        return result
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
            interval_seconds=request.interval_seconds
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
