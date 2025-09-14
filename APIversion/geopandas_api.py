import json
import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Union, Dict, Optional, Tuple, Literal

# GeoPandasTool imports
from GeoPandasTool.area import area
from GeoPandasTool.boundary import boundary
from GeoPandasTool.bounds import bounds
from GeoPandasTool.buffer import buffer
from GeoPandasTool.centroid import centroid
from GeoPandasTool.clean_geometries import clean_geometries
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

app = FastAPI(title="GeoPandasTool API", description="GeoPandas几何处理工具API")

# === GeoPandasTool APIs ===

class AreaRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/area")
def compute_area(req: AreaRequest):
    """
    计算一个或多个 GeoJSON 文件中 Polygon/MultiPolygon 的总面积（平方米）
    """
    try:
        result = area(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class BoundaryRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/boundary")
def compute_boundary(req: BoundaryRequest):
    """
    计算一个或多个 GeoJSON 文件的边界并保存为文件
    """
    try:
        result = boundary(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class BoundsRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/bounds")
def compute_bounds(req: BoundsRequest):
    """
    计算一个或多个 GeoJSON 文件的边界包围盒并保存为文件
    """
    try:
        result = bounds(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class BufferRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    distance: float

@app.post("/buffer")
def compute_buffer(req: BufferRequest):
    """
    计算一个或多个 GeoJSON 文件的缓冲区并保存为文件
    """
    try:
        result = buffer(req.geojson_names, req.distance)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class CleanGeometriesRequest(BaseModel):
    geojson_input: Union[str, Dict] = Field(..., description="输入的GeoJSON数据（字符串或字典）")
    repair_invalid: bool = Field(True, description="是否尝试修复无效几何图形")
    remove_empty: bool = Field(True, description="是否移除空的几何图形")
    remove_duplicates: bool = Field(True, description="是否移除重复的几何图形")
    simplify_tolerance: float = Field(0.0, description="几何简化容差，0表示不简化")

@app.post("/clean_geometries")
def clean_geometries_api(req: CleanGeometriesRequest):
    """
    清理和修复GeoJSON中的无效几何图形
    """
    try:
        result = clean_geometries(
            req.geojson_input,
            repair_invalid=req.repair_invalid,
            remove_empty=req.remove_empty,
            remove_duplicates=req.remove_duplicates,
            simplify_tolerance=req.simplify_tolerance
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 

class CentroidRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/centroid")
def compute_centroid(req: CentroidRequest):
    """
    计算一个或多个 GeoJSON 文件的质心并保存为文件
    """
    try:
        result = centroid(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ClipRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    xmin: float = Field(..., description="矩形裁剪框左边界")
    ymin: float = Field(..., description="矩形裁剪框下边界")
    xmax: float = Field(..., description="矩形裁剪框右边界")
    ymax: float = Field(..., description="矩形裁剪框上边界")

@app.post("/clip_by_rect")
def clip_geojson(req: ClipRequest):
    """
    裁剪一个或多个 GeoJSON 文件，使其只保留指定矩形区域内的部分
    """
    try:
        result = clip_by_rect(req.geojson_names, req.xmin, req.ymin, req.xmax, req.ymax)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConcaveHullRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    alpha: float = Field(0.05, description="影响凹壳形状的参数，越小越精细，越大越简洁")

@app.post("/concave_hull")
def compute_concave_hull(req: ConcaveHullRequest):
    """
    计算一个或多个 GeoJSON 文件的凹壳（目前代码实际上为凸壳）
    """
    try:
        result = concave_hull(req.geojson_names, req.alpha)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ContainsRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/contains")
def check_contains(req: ContainsRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否包含另一个 GeoJSON 文件中的几何对象
    """
    try:
        result = contains(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ContainsProperlyRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/contains-properly")
def check_contains_properly(req: ContainsProperlyRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否正确包含另一个 GeoJSON 文件中的几何对象
    """
    try:
        result = contains_properly(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConvexHullRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/convex-hull")
def compute_convex_hull(req: ConvexHullRequest):
    """
    计算一个或多个 GeoJSON 文件的凸包并保存为文件
    """
    try:
        result = convex_hull(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CoveredByRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/covered-by")
def check_covered_by(req: CoveredByRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否被另一个 GeoJSON 文件中的几何对象覆盖
    """
    try:
        result = covered_by(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CoversRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/covers")
def check_covers(req: CoversRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否覆盖另一个 GeoJSON 文件中的几何对象
    """
    try:
        result = covers(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class CrossesRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/crosses")
def check_crosses(req: CrossesRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象相交
    """
    try:
        result = crosses(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DifferenceRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    clip_geojson_name: str  # 用于裁剪的GeoJSON文件名（不含路径和扩展名）

@app.post("/difference")
def compute_difference(req: DifferenceRequest):
    """
    计算一个或多个 GeoJSON 文件与另一个 GeoJSON 文件的差集
    """
    try:
        result = difference(req.geojson_names, req.clip_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DisjointRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/disjoint")
def check_disjoint(req: DisjointRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象不相交
    """
    try:
        result = disjoint(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DistanceRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/distance")
def compute_distance(req: DistanceRequest):
    """
    计算一个或多个 GeoJSON 文件中的几何对象与另一个 GeoJSON 文件中的几何对象的距离
    """
    try:
        result = distance(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DWithinRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名
    distance: float  # 距离阈值（单位取决于坐标系）

@app.post("/dwithin")
def dwithin_api(req: DWithinRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象在指定距离内
    """
    try:
        result = dwithin(req.geojson_names, req.other_geojson_name, req.distance)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class EnvelopeRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/envelope")
def envelope_api(req: EnvelopeRequest):
    """
    计算一个或多个 GeoJSON 文件的外包络矩形并保存为文件
    """
    try:
        result = envelope(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ExteriorRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/exterior")
def exterior_api(req: ExteriorRequest):
    """
    提取一个或多个 GeoJSON 文件中Polygon/MultiPolygon几何的外边界
    """
    try:
        result = exterior(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class GeomAlmostEqualRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名
    tolerance: Optional[float] = 1e-9  # 容差（可选）

@app.post("/geom_almost_equal")
def geom_almost_equal_api(req: GeomAlmostEqualRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象几乎相等
    """
    try:
        result = geom_almost_equal(req.geojson_names, req.other_geojson_name, req.tolerance or 1e-9)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class GeomEqualsRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/geom_equals")
def geom_equals_api(req: GeomEqualsRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象相等
    """
    try:
        result = geom_equals(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class GeomEqualsExactRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名
    tolerance: Optional[float] = 1e-9  # 容差，默认值为 1e-9

@app.post("/geom_equals_exact")
def geom_equals_exact_api(req: GeomEqualsExactRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象精确相等
    """
    try:
        result = geom_equals_exact(req.geojson_names, req.other_geojson_name, req.tolerance or 1e-9)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IntersectionRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    clip_geojson_name: str  # 用于计算交集的GeoJSON文件名

@app.post("/intersection")
def intersection_api(req: IntersectionRequest):
    """
    计算一个或多个 GeoJSON 文件与另一个 GeoJSON 文件的交集并保存为文件
    """
    try:
        result = intersection(req.geojson_names, req.clip_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IntersectsRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/intersects")
def intersects_api(req: IntersectsRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象相交
    """
    try:
        result = intersects(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsCCWRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_ccw")
def is_ccw_api(req: IsCCWRequest):
    """
    判断一个或多个 GeoJSON 文件中几何对象的外环顶点是否为逆时针方向（CCW）
    """
    try:
        result = is_ccw(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsClosedRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_closed")
def is_closed_api(req: IsClosedRequest):
    """
    判断一个或多个 GeoJSON 文件中几何对象是否闭合
    """
    try:
        result = is_closed(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsEmptyRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_empty")
def is_empty_api(req: IsEmptyRequest):
    """
    判断一个或多个 GeoJSON 文件中几何对象是否为空
    """
    try:
        result = is_empty(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsRingRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_ring")
def is_ring_api(req: IsRingRequest):
    """
    判断一个或多个 GeoJSON 文件中LineString几何对象是否是ring（闭合且简单）
    """
    try:
        result = is_ring(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsSimpleRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_simple")
def is_simple_api(req: IsSimpleRequest):
    """
    判断一个或多个 GeoJSON 文件中几何对象是否为simple（即不自交）
    """
    try:
        result = is_simple(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsValidRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_valid")
def is_valid_api(req: IsValidRequest):
    """
    判断一个或多个 GeoJSON 文件中几何对象是否是有效的合法几何
    """
    try:
        result = is_valid(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class IsValidReasonRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/is_valid_reason")
def is_valid_reason_api(req: IsValidReasonRequest):
    """
    返回一个或多个 GeoJSON 文件中几何对象合法性检查的原因说明
    """
    try:
        result = is_valid_reason(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class LengthRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/length")
def length_api(req: LengthRequest):
    """
    计算一个或多个 GeoJSON 文件中每个几何对象的长度
    """
    try:
        result = length(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class LineMergeRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/line_merge")
def line_merge_api(req: LineMergeRequest):
    """
    合并一个或多个 GeoJSON 数据中的LineString线段并保存为文件
    """
    try:
        result = line_merge(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class MBRRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）

@app.post("/minimum_bounding_radius")
def minimum_bounding_radius_api(req: MBRRequest):
    """
    计算一个或多个 GeoJSON 文件中几何对象的最小外接圆半径
    """
    try:
        result = minimum_bounding_radius(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class OffsetCurveRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")
    distance: float = Field(..., description="偏移距离")
    side: Optional[Literal['left', 'right']] = Field('right', description="偏移方向，left 或 right，默认 right")
    resolution: Optional[int] = Field(16, description="圆弧分割精度，默认16")
    join_style: Optional[int] = Field(1, description="连接样式，1=round, 2=mitre, 3=bevel，默认1")
    mitre_limit: Optional[float] = Field(5.0, description="miter连接样式时的限制，默认5.0")

@app.post("/offset_curve")
def offset_curve_api(req: OffsetCurveRequest):
    """
    生成一个或多个 GeoJSON 文件中LineString/MultiLineString的offset curve并保存为文件
    """
    try:
        result = offset_curve(
            req.geojson_names,
            distance=req.distance,
            side=req.side or 'right',
            resolution=req.resolution or 16,
            join_style=req.join_style or 1,
            mitre_limit=req.mitre_limit or 5.0
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class OverlapsRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/overlaps")
def overlaps_api(req: OverlapsRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象重叠
    """
    try:
        result = overlaps(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class RemoveRepeatedPointsRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")

@app.post("/remove_repeated_points")
def remove_repeated_points_api(req: RemoveRepeatedPointsRequest):
    """
    移除一个或多个 GeoJSON 数据中的重复点并保存为文件
    """
    try:
        result = remove_repeated_points(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ReverseRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")

@app.post("/reverse")
def reverse_api(req: ReverseRequest):
    """
    反转一个或多个 GeoJSON 中几何对象的坐标顺序并保存为文件
    """
    try:
        result = reverse(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class RotateRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")
    angle: float = Field(..., description="旋转角度（默认为度，use_radians=True 时为弧度）")
    origin: Union[str, Tuple[float, float]] = Field('centroid', description="旋转中心，可为 'centroid'、'center' 或指定坐标 (x, y)")
    use_radians: bool = Field(False, description="是否使用弧度进行旋转")

@app.post("/rotate")
def rotate_api(req: RotateRequest):
    """
    旋转一个或多个 GeoJSON 中几何对象并保存为文件
    """
    try:
        result = rotate(req.geojson_names, angle=req.angle, origin=str(req.origin), use_radians=req.use_radians)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ScaleRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")
    xfact: float = Field(1.0, description="x 方向的缩放因子")
    yfact: float = Field(1.0, description="y 方向的缩放因子")
    origin: Union[str, Tuple[float, float]] = Field("center", description="缩放中心，可为 'center', 'centroid', 或 (x, y) 坐标")

@app.post("/scale")
def scale_api(req: ScaleRequest):
    """
    缩放一个或多个 GeoJSON 中几何对象并保存为文件
    """
    try:
        result = scale(req.geojson_names, xfact=req.xfact, yfact=req.yfact, origin=str(req.origin))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ShortestLineRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/shortest_line_between_two")
def shortest_line_api(req: ShortestLineRequest):
    """
    计算一个或多个 GeoJSON 文件中的几何对象与另一个 GeoJSON 文件中的几何对象之间的最短连接线并保存为文件
    """
    try:
        result = shortest_line_between_two(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SimplifyRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")
    tolerance: Optional[float] = Field(0.01, description="简化程度，值越大简化越明显")
    preserve_topology: Optional[bool] = Field(True, description="是否保持拓扑结构")

@app.post("/simplify")
def simplify_api(req: SimplifyRequest):
    """
    简化一个或多个 GeoJSON 中几何对象并保存为文件
    """
    try:
        result = simplify(req.geojson_names, tolerance=req.tolerance or 0.01, preserve_topology=req.preserve_topology or True)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SymmetricDifferenceRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/symmetric_difference")
def symmetric_difference_api(req: SymmetricDifferenceRequest):
    """
    计算一个或多个 GeoJSON 文件与另一个 GeoJSON 文件的对称差并保存为文件
    """
    try:
        result = symmetric_difference(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class TouchesRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/touches")
def touches_api(req: TouchesRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否与另一个 GeoJSON 文件中的几何对象接触
    """
    try:
        result = touches(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UnionRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/union")
def union_api(req: UnionRequest):
    """
    计算一个或多个 GeoJSON 文件与另一个 GeoJSON 文件的并集并保存为文件
    """
    try:
        result = union(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class WithinRequest(BaseModel):
    geojson_names: Union[str, List[str]]  # 单个或多个GeoJSON文件名（不含路径和扩展名）
    other_geojson_name: str  # 目标GeoJSON文件名

@app.post("/within")
def within_api(req: WithinRequest):
    """
    判断一个或多个 GeoJSON 文件中的几何对象是否在另一个 GeoJSON 文件中的几何对象内部
    """
    try:
        result = within(req.geojson_names, req.other_geojson_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class TranslateRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")
    xoff: float = Field(0.0, description="x 方向的偏移量")
    yoff: float = Field(0.0, description="y 方向的偏移量")

@app.post("/translate")
def translate_api(req: TranslateRequest):
    """
    平移一个或多个 GeoJSON 中几何对象并保存为文件
    """
    try:
        result = translate(req.geojson_names, xoff=req.xoff, yoff=req.yoff)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class TotalBoundsRequest(BaseModel):
    geojson_names: Union[str, List[str]] = Field(..., description="单个或多个GeoJSON文件名（不含路径和扩展名）")

@app.post("/total_bounds")
def total_bounds_api(req: TotalBoundsRequest):
    """
    计算一个或多个 GeoJSON 中所有geometry的整体包围盒
    """
    try:
        result = total_bounds(req.geojson_names)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
