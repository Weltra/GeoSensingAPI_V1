from typing import List, Dict, Optional, Tuple, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from DeployTool.UAV_GS_planner import run_planning_scenario
# 修复导入错误 - 只导入实际存在的类
from DeployTool.advanced_sensor_optimization import (
	GeneticAlgorithmOptimizer,
	SimulatedAnnealingOptimizer,
	Satellite,
	GroundSensor,
	ResourceConstraints
)
# 修复后的DeployTool imports
from DeployTool.find_GS import find_stations
from DeployTool.find_UAV_combination import find_drone_combination
from DeployTool.ground_sensor_from_scratch import GroundSensorFromScratchSolver
from DeployTool.ground_sensor_position_optimize import GroundSensorPositionOptimizer
from DeployTool.mclp_observation_station import MCLPObservationStationSolver
# 修复导入 - 使用实际存在的类
from DeployTool.satellite_observation_planner import plan_satellite_combination
from DeployTool.sensor_relationship_analyzer import SensorRelationshipAnalyzer

# 创建FastAPI应用
app = FastAPI(title="DeployTool API", description="传感器部署工具API")


# ==================== 基础查询工具 ====================

class FindStationsRequest(BaseModel):
	geojson_path: str = Field(..., description="包含观测区域多边形的GeoJSON文件路径")
	db_path: str = Field(..., description="地面站数据库文件路径")


@app.post("/find_stations")
def find_stations_api(req: FindStationsRequest):
	"""
    在GeoJSON文件定义的区域内查找地面站
    """
	try:
		result = find_stations(req.geojson_path, req.db_path)
		return {"success": True, "data": result}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


class FindDroneCombinationRequest(BaseModel):
	required_area_sq_km: float = Field(..., description="需要观测的总面积，单位为平方公里")
	db_path: str = Field("data/UAV_data.db", description="无人机数据库文件路径")


@app.post("/find_drone_combination")
def find_drone_combination_api(req: FindDroneCombinationRequest):
	"""
    根据需要观测的面积，从无人机数据库中查询能满足要求的无人机组合
    """
	try:
		result = find_drone_combination(req.required_area_sq_km, req.db_path)
		return {"success": True, "data": result}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


# ==================== 地面传感器优化工具 ====================

class GroundSensorFromScratchRequest(BaseModel):
	target_area_coords: List[Tuple[float, float]] = Field(..., description="目标区域坐标点列表")
	coverage_ratio: float = Field(0.95, description="目标覆盖率")
	sensor_radius: float = Field(0.05, description="传感器覆盖半径")
	grid_resolution: float = Field(0.01, description="网格分辨率")
	create_visualization: bool = Field(True, description="是否创建可视化")


@app.post("/ground_sensor_from_scratch")
def ground_sensor_from_scratch_api(req: GroundSensorFromScratchRequest):
	"""
    地面传感器从零布设优化
    """
	try:
		solver = GroundSensorFromScratchSolver(
			target_area_coords=req.target_area_coords,
			coverage_ratio=req.coverage_ratio,
			sensor_radius=req.sensor_radius,
			grid_resolution=req.grid_resolution
		)
		result = solver.solve()
		if req.create_visualization:
			solver.visualize()
		return {"success": True, "data": result}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


class GroundSensorPositionOptimizeRequest(BaseModel):
	target_area_coords: List[Tuple[float, float]] = Field(..., description="目标区域坐标点列表")
	sensor_radius: float = Field(0.05, description="传感器覆盖半径")
	grid_resolution: float = Field(0.01, description="网格分辨率")
	create_visualization: bool = Field(True, description="是否创建可视化")


@app.post("/ground_sensor_position_optimize")
def ground_sensor_position_optimize_api(req: GroundSensorPositionOptimizeRequest):
	"""
    地面传感器位置优化
    """
	try:
		optimizer = GroundSensorPositionOptimizer(
			target_area_coords=req.target_area_coords,
			sensor_radius=req.sensor_radius,
			grid_resolution=req.grid_resolution
		)
		result = optimizer.optimize()
		if req.create_visualization:
			optimizer.visualize()
		return {"success": True, "data": result}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


# 规划卫星方案 API
class SatellitePlanningRequest(BaseModel):
	coverage_results: Dict = Field(..., description="覆盖率计算结果")
	target_geojson_path: str = Field(..., description="目标区域GeoJSON文件路径")
	target_coverage: float = Field(0.99, description="目标覆盖率")


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
			target_coverage=request.target_coverage
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


# UAV+地面站规划方案 API
class UAVPlanningRequest(BaseModel):
	geojson_path: str = Field(..., description="目标区域GeoJSON文件路径")
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


# ==================== 高级传感器优化工具 ====================

class AdvancedSensorOptimizationRequest(BaseModel):
	target_area_coords: List[Tuple[float, float]] = Field(..., description="目标区域坐标点列表")
	satellite_data: List[Dict] = Field(..., description="卫星数据列表")
	ground_sensor_data: List[Dict] = Field(..., description="地面传感器数据列表")
	algorithm: Literal["GA", "SA"] = Field("GA", description="优化算法：GA(遗传算法)或SA(模拟退火)")
	target_coverage_ratio: float = Field(0.95, description="目标覆盖率")
	max_iterations: int = Field(1000, description="最大迭代次数")
	population_size: int = Field(50, description="种群大小(仅GA算法)")
	mutation_rate: float = Field(0.1, description="变异率(仅GA算法)")
	crossover_rate: float = Field(0.8, description="交叉率(仅GA算法)")
	initial_temp: float = Field(1000.0, description="初始温度(仅SA算法)")
	cooling_rate: float = Field(0.95, description="冷却率(仅SA算法)")
	create_visualization: bool = Field(True, description="是否创建可视化")


@app.post("/advanced_sensor_optimization")
def advanced_sensor_optimization_api(req: AdvancedSensorOptimizationRequest):
	"""
    高级传感器优化算法
    """
	try:
		from shapely.geometry import Polygon
		import numpy as np

		# 创建目标区域多边形
		target_area = Polygon(req.target_area_coords)

		# 转换卫星数据
		satellites = []
		for sat_data in req.satellite_data:
			satellite = Satellite(
				id=sat_data.get('id', 0),
				center_x=sat_data.get('center_x', 0),
				center_y=sat_data.get('center_y', 0),
				width=sat_data.get('width', 1),
				height=sat_data.get('height', 1),
				cost=sat_data.get('cost', 100),
				bandwidth=sat_data.get('bandwidth', 10)
			)
			satellites.append(satellite)

		# 转换地面传感器数据
		ground_sensors = []
		for sensor_data in req.ground_sensor_data:
			sensor = GroundSensor(
				id=sensor_data.get('id', 0),
				x=sensor_data.get('x', 0),
				y=sensor_data.get('y', 0),
				radius=sensor_data.get('radius', 0.1),
				cost=sensor_data.get('cost', 50),
				bandwidth=sensor_data.get('bandwidth', 5),
				mobile=sensor_data.get('mobile', False)
			)
			ground_sensors.append(sensor)

		# 创建资源约束
		constraints = ResourceConstraints(
			max_satellites=len(satellites),
			max_ground_sensors=len(ground_sensors),
			max_total_cost=sum(s.cost for s in satellites) + sum(s.cost for s in ground_sensors),
			max_bandwidth=sum(s.bandwidth for s in satellites) + sum(s.bandwidth for s in ground_sensors),
			target_coverage_ratio=req.target_coverage_ratio
		)

		# 根据算法选择优化器
		if req.algorithm == "GA":
			optimizer = GeneticAlgorithmOptimizer(
				target_area=target_area,
				satellites=satellites,
				ground_sensors=ground_sensors,
				constraints=constraints,
				population_size=req.population_size,
				generations=req.max_iterations,
				mutation_rate=req.mutation_rate,
				crossover_rate=req.crossover_rate
			)
		else:  # SA
			optimizer = SimulatedAnnealingOptimizer(
				target_area=target_area,
				satellites=satellites,
				ground_sensors=ground_sensors,
				constraints=constraints,
				initial_temperature=req.initial_temp,
				cooling_rate=req.cooling_rate,
				max_iterations=req.max_iterations
			)

		result = optimizer.optimize()

		if req.create_visualization:
			optimizer.visualize_solution(result)

		return {
			"success": True,
			"data": {
				"best_solution": result,
				"coverage_ratio": result.coverage_ratio,
				"total_cost": result.total_cost,
				"selected_satellites": result.selected_satellites,
				"selected_ground_sensors": result.selected_ground_sensors
			}
		}
	except Exception as e:
		raise HTTPException(status_code=400, detail=f"高级传感器优化失败: {str(e)}")


# ==================== 传感器分析工具 ====================

class SensorRelationshipAnalyzerRequest(BaseModel):
	sensor_data: List[Dict] = Field(..., description="传感器数据列表")
	time_tolerance: float = Field(0.1, description="时间重叠容忍度")
	space_tolerance: float = Field(0.1, description="空间重叠容忍度")
	create_visualization: bool = Field(True, description="是否创建可视化")


@app.post("/sensor_relationship_analyzer")
def sensor_relationship_analyzer_api(req: SensorRelationshipAnalyzerRequest):
	"""
    传感器关系分析器
    """
	try:
		analyzer = SensorRelationshipAnalyzer(
			time_tolerance=req.time_tolerance,
			space_tolerance=req.space_tolerance
		)
		result = analyzer.analyze_sensor_network(req.sensor_data)
		if req.create_visualization:
			analyzer.visualize_analysis()
		return {"success": True, "data": result}
	except Exception as e:
		raise HTTPException(status_code=400, detail=f"传感器关系分析失败: {str(e)}")


# ==================== MCLP观测站工具 ====================

class MCLPObservationStationRequest(BaseModel):
	target_area_coords: List[Tuple[float, float]] = Field(..., description="目标区域坐标点列表")
	coverage_ratio: float = Field(0.95, description="目标覆盖率")
	sensor_radius: float = Field(0.05, description="传感器覆盖半径")
	grid_resolution: float = Field(0.01, description="网格分辨率")
	create_visualization: bool = Field(True, description="是否创建可视化")


@app.post("/mclp_observation_station")
def mclp_observation_station_api(req: MCLPObservationStationRequest):
	"""
    MCLP观测站求解器
    """
	try:
		solver = MCLPObservationStationSolver(
			target_area_coords=req.target_area_coords,
			coverage_ratio=req.coverage_ratio,
			sensor_radius=req.sensor_radius,
			grid_resolution=req.grid_resolution
		)
		result = solver.solve()
		if req.create_visualization:
			solver.visualize()
		return {"success": True, "data": result}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
	import uvicorn
	uvicorn.run(app, host="0.0.0.0", port=8001)
