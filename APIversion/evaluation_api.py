import json
from typing import List, Dict, Optional, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from EvaluationTool.DOCI import calculate_doci
from EvaluationTool.OCEM import calculate_ocem
# EvaluationTool imports
from EvaluationTool.SSCI import calculate_ssci
from EvaluationTool.query_sensors import query_sensors

# 创建FastAPI应用
app = FastAPI(title="EvaluationTool API", description="传感器评估工具API")

# ==================== 通用查询工具 ====================

class QuerySensorsRequest(BaseModel):
    db_path: str = Field(..., description="传感器数据库文件路径")
    sensor_name: Optional[str] = Field(None, description="传感器名称（模糊搜索）")
    mission_theme: Optional[str] = Field(None, description="任务主题关键词")
    sensor_type: Optional[str] = Field(None, description="传感器类型")

@app.post("/query_sensors")
def query_sensors_api(req: QuerySensorsRequest):
    """
    查询传感器数据
    """
    try:
        result = query_sensors(
            db_path=req.db_path,
            sensor_name=req.sensor_name,
            mission_theme=req.mission_theme,
            sensor_type=req.sensor_type
        )
        return {"success": True, "data": result, "count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== SSCI评估工具 ====================

class SSCIRequest(BaseModel):
    sensors_data: Dict[str, Dict] = Field(..., description="传感器数据字典")
    scenario_config: Dict = Field(..., description="场景配置")

@app.post("/calculate_ssci")
def calculate_ssci_api(req: SSCIRequest):
    """
    计算SSCI（传感器空间覆盖指数）
    """
    try:
        result = calculate_ssci(req.sensors_data, req.scenario_config)
        return {"success": True, "data": json.loads(result)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== OCEM评估工具 ====================

class OCEMRequest(BaseModel):
    sensors_data: Dict[str, Dict] = Field(..., description="传感器数据字典")
    scenario_config: Dict = Field(..., description="场景配置")

@app.post("/calculate_ocem")
def calculate_ocem_api(req: OCEMRequest):
    """
    计算OCEM（观测能力评估模型）
    """
    try:
        result = calculate_ocem(req.sensors_data, req.scenario_config)
        return {"success": True, "data": json.loads(result)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== DOCI评估工具 ====================

class DOCIRequest(BaseModel):
    sensors_data: Dict[str, Dict] = Field(..., description="传感器数据字典")
    scenario_config: Dict = Field(..., description="场景配置")

@app.post("/calculate_doci")
def calculate_doci_api(req: DOCIRequest):
    """
    计算DOCI（数据质量综合指数）
    """
    try:
        result = calculate_doci(req.sensors_data, req.scenario_config)
        return {"success": True, "data": json.loads(result)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== 综合评估工具 ====================

class ComprehensiveEvaluationRequest(BaseModel):
    db_path: str = Field(..., description="传感器数据库文件路径")
    evaluation_models: List[Literal["SSCI", "OCEM", "DOCI"]] = Field(..., description="评估模型列表")
    scenario_config: Dict = Field(..., description="场景配置")
    sensor_filters: Optional[Dict] = Field(None, description="传感器过滤条件")

@app.post("/comprehensive_evaluation")
def comprehensive_evaluation_api(req: ComprehensiveEvaluationRequest):
    """
    综合评估工具，支持多种评估模型
    """
    try:
        # 查询传感器数据
        sensors_data = query_sensors(
            db_path=req.db_path,
            sensor_name=req.sensor_filters.get("sensor_name") if req.sensor_filters else None,
            mission_theme=req.sensor_filters.get("mission_theme") if req.sensor_filters else None,
            sensor_type=req.sensor_filters.get("sensor_type") if req.sensor_filters else None
        )
        
        results = {}
        
        # 执行各种评估模型
        if "SSCI" in req.evaluation_models:
            try:
                ssci_result = calculate_ssci(sensors_data, req.scenario_config)
                results["SSCI"] = json.loads(ssci_result)
            except Exception as e:
                results["SSCI"] = {"error": str(e)}
        
        if "OCEM" in req.evaluation_models:
            try:
                ocem_result = calculate_ocem(sensors_data, req.scenario_config)
                results["OCEM"] = json.loads(ocem_result)
            except Exception as e:
                results["OCEM"] = {"error": str(e)}
        
        if "DOCI" in req.evaluation_models:
            try:
                doci_result = calculate_doci(sensors_data, req.scenario_config)
                results["DOCI"] = json.loads(doci_result)
            except Exception as e:
                results["DOCI"] = {"error": str(e)}
        
        return {
            "success": True,
            "sensor_count": len(sensors_data),
            "evaluation_models": req.evaluation_models,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== 预设场景配置 ====================

class PresetScenarioRequest(BaseModel):
    scenario_type: Literal["disaster_monitoring", "environmental_monitoring", "agricultural_monitoring", "urban_monitoring"] = Field(..., description="预设场景类型")
    custom_config: Optional[Dict] = Field(None, description="自定义配置覆盖")

@app.post("/get_preset_scenario")
def get_preset_scenario_api(req: PresetScenarioRequest):
    """
    获取预设场景配置
    """
    try:
        # 预设场景配置
        preset_scenarios = {
            "disaster_monitoring": {
                "description": "灾害监测场景",
                "time_window": {"start": "2025-08-24T00:00:00Z", "end": "2025-08-24T23:59:59Z"},
                "environment": {"cloudiness_forecast": 0.3},
                "models": {
                    "ssci": {
                        "description": "SSCI模型",
                        "weights_by_name": {"spatial_resolution_m": 0.3, "temporal_resolution_days": 0.2, "swath_width_km": 0.2, "band_count": 0.15, "snr": 0.15},
                        "reciprocal_cols_by_name": ["spatial_resolution_m", "temporal_resolution_days"]
                    },
                    "ocem": {
                        "description": "OCEM模型",
                        "requirements": {"s_task": 10000, "t_task": 5, "req_spatial_res": 10, "req_rad_res": 8},
                        "ahp_matrix": [[1, 2, 3, 4], [0.5, 1, 2, 3], [0.333, 0.5, 1, 2], [0.25, 0.333, 0.5, 1]]
                    },
                    "doci": {
                        "description": "DOCI模型",
                        "theme": "Disaster Monitoring",
                        "requirements": {"spatial_res": [30, 10, 3], "temporal_res": [3, 1, 0.5]},
                        "ahp_weights": [0.7, 0.3]
                    }
                }
            },
            "environmental_monitoring": {
                "description": "环境监测场景",
                "time_window": {"start": "2025-08-24T00:00:00Z", "end": "2025-08-24T23:59:59Z"},
                "environment": {"cloudiness_forecast": 0.4},
                "models": {
                    "ssci": {
                        "description": "SSCI模型",
                        "weights_by_name": {"spatial_resolution_m": 0.25, "temporal_resolution_days": 0.25, "swath_width_km": 0.2, "band_count": 0.2, "snr": 0.1},
                        "reciprocal_cols_by_name": ["spatial_resolution_m", "temporal_resolution_days"]
                    },
                    "ocem": {
                        "description": "OCEM模型",
                        "requirements": {"s_task": 20000, "t_task": 7, "req_spatial_res": 20, "req_rad_res": 12},
                        "ahp_matrix": [[1, 2, 3, 4], [0.5, 1, 2, 3], [0.333, 0.5, 1, 2], [0.25, 0.333, 0.5, 1]]
                    },
                    "doci": {
                        "description": "DOCI模型",
                        "theme": "Environmental Monitoring",
                        "requirements": {"spatial_res": [50, 20, 5], "temporal_res": [5, 2, 1]},
                        "ahp_weights": [0.6, 0.4]
                    }
                }
            },
            "agricultural_monitoring": {
                "description": "农业监测场景",
                "time_window": {"start": "2025-08-24T00:00:00Z", "end": "2025-08-24T23:59:59Z"},
                "environment": {"cloudiness_forecast": 0.2},
                "models": {
                    "ssci": {
                        "description": "SSCI模型",
                        "weights_by_name": {"spatial_resolution_m": 0.2, "temporal_resolution_days": 0.3, "swath_width_km": 0.25, "band_count": 0.15, "snr": 0.1},
                        "reciprocal_cols_by_name": ["spatial_resolution_m", "temporal_resolution_days"]
                    },
                    "ocem": {
                        "description": "OCEM模型",
                        "requirements": {"s_task": 15000, "t_task": 3, "req_spatial_res": 15, "req_rad_res": 10},
                        "ahp_matrix": [[1, 2, 3, 4], [0.5, 1, 2, 3], [0.333, 0.5, 1, 2], [0.25, 0.333, 0.5, 1]]
                    },
                    "doci": {
                        "description": "DOCI模型",
                        "theme": "Agricultural Monitoring",
                        "requirements": {"spatial_res": [40, 15, 5], "temporal_res": [4, 2, 1]},
                        "ahp_weights": [0.65, 0.35]
                    }
                }
            },
            "urban_monitoring": {
                "description": "城市监测场景",
                "time_window": {"start": "2025-08-24T00:00:00Z", "end": "2025-08-24T23:59:59Z"},
                "environment": {"cloudiness_forecast": 0.5},
                "models": {
                    "ssci": {
                        "description": "SSCI模型",
                        "weights_by_name": {"spatial_resolution_m": 0.35, "temporal_resolution_days": 0.2, "swath_width_km": 0.15, "band_count": 0.2, "snr": 0.1},
                        "reciprocal_cols_by_name": ["spatial_resolution_m", "temporal_resolution_days"]
                    },
                    "ocem": {
                        "description": "OCEM模型",
                        "requirements": {"s_task": 5000, "t_task": 2, "req_spatial_res": 5, "req_rad_res": 8},
                        "ahp_matrix": [[1, 2, 3, 4], [0.5, 1, 2, 3], [0.333, 0.5, 1, 2], [0.25, 0.333, 0.5, 1]]
                    },
                    "doci": {
                        "description": "DOCI模型",
                        "theme": "Urban Monitoring",
                        "requirements": {"spatial_res": [20, 10, 2], "temporal_res": [2, 1, 0.5]},
                        "ahp_weights": [0.8, 0.2]
                    }
                }
            }
        }
        
        scenario_config = preset_scenarios.get(req.scenario_type, {})
        
        # 应用自定义配置覆盖
        if req.custom_config:
            scenario_config = {**scenario_config, **req.custom_config}
        
        return {"success": True, "scenario_config": scenario_config}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== 评估结果分析工具 ====================

class EvaluationAnalysisRequest(BaseModel):
    evaluation_results: Dict = Field(..., description="评估结果")
    analysis_type: Literal["ranking", "comparison", "statistics"] = Field("ranking", description="分析类型")

@app.post("/analyze_evaluation_results")
def analyze_evaluation_results_api(req: EvaluationAnalysisRequest):
    """
    分析评估结果
    """
    try:
        results = req.evaluation_results
        analysis = {}
        
        if req.analysis_type == "ranking":
            # 排名分析
            for model_name, model_results in results.items():
                if "results" in model_results and isinstance(model_results["results"], list):
                    rankings = []
                    for item in model_results["results"]:
                        if "name" in item and "rank" in item:
                            rankings.append({"name": item["name"], "rank": item["rank"]})
                    analysis[model_name] = {"rankings": rankings}
        
        elif req.analysis_type == "comparison":
            # 对比分析
            sensor_scores = {}
            for model_name, model_results in results.items():
                if "results" in model_results and isinstance(model_results["results"], list):
                    for item in model_results["results"]:
                        if "name" in item:
                            sensor_name = item["name"]
                            if sensor_name not in sensor_scores:
                                sensor_scores[sensor_name] = {}
                            
                            # 提取分数
                            score_key = None
                            for key in ["ssci_score", "normalized_score", "components"]:
                                if key in item:
                                    score_key = key
                                    break
                            
                            if score_key:
                                sensor_scores[sensor_name][model_name] = item[score_key]
            
            analysis["sensor_comparison"] = sensor_scores
        
        elif req.analysis_type == "statistics":
            # 统计分析
            for model_name, model_results in results.items():
                if "results" in model_results and isinstance(model_results["results"], list):
                    scores = []
                    for item in model_results["results"]:
                        for key in ["ssci_score", "normalized_score"]:
                            if key in item and isinstance(item[key], (int, float)):
                                scores.append(item[key])
                                break
                    
                    if scores:
                        analysis[model_name] = {
                            "count": len(scores),
                            "mean": sum(scores) / len(scores),
                            "max": max(scores),
                            "min": min(scores),
                            "std": (sum((x - sum(scores) / len(scores)) ** 2 for x in scores) / len(scores)) ** 0.5
                        }
        
        return {"success": True, "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== 健康检查 ====================

@app.get("/health")
def health_check():
    """
    健康检查端点
    """
    return {"status": "healthy", "service": "EvaluationTool API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002) 