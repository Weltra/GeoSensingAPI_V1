# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI
FILE_NAME: test_toolchain_complete
AUTHOR: AI Assistant
DATE: 2025-01-11
DESCRIPTION: 完整的测试工具链，使用已封装的API实现
"""

import requests
import json
import time
from typing import Dict, Any, Optional

class GeoSensingAPITestChain:
    """地理空间智能API测试工具链"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        """
        初始化测试工具链
        
        Args:
            base_url: API服务的基础URL
        """
        self.base_url = base_url
        self.session = requests.Session()
        
    def test_api_health(self) -> bool:
        """测试API服务是否正常运行"""
        try:
            response = self.session.get(f"{self.base_url}/")
            return response.status_code == 200
        except Exception as e:
            print(f"API健康检查失败: {e}")
            return False
    
    def step1_get_satellite_tle(self, 
                               satellite_db_path: str,
                               mission_theme: str = "Land cover",
                               sensor_type: str = "Optical Sensor") -> Optional[Dict[str, str]]:
        """
        步骤1: 使用find_Satellite.py获取卫星TLE数据
        
        Args:
            satellite_db_path: 卫星数据库路径
            mission_theme: 任务主题
            sensor_type: 传感器类型
            
        Returns:
            卫星TLE数据字典，键为卫星名，值为TLE数据
        """
        print("=" * 60)
        print("步骤1: 获取卫星TLE数据")
        print("=" * 60)
        
        try:
            url = f"{self.base_url}/get_satellite_tle"
            payload = {
                "satellite_db_path": satellite_db_path,
                "mission_theme": mission_theme,
                "sensor_type": sensor_type
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result["success"]:
                tle_data = result["data"]
                print(f"✅ 成功获取 {len(tle_data)} 颗卫星的TLE数据")
                print(f"📋 卫星列表: {list(tle_data.keys())}")
                return tle_data
            else:
                print(f"❌ 获取TLE数据失败: {result['message']}")
                return None
                
        except Exception as e:
            print(f"❌ 步骤1执行失败: {e}")
            return None
    
    def step2_get_observation_overlap(self,
                                    tle_dict: Dict[str, str],
                                    start_time_str: str,
                                    end_time_str: str,
                                    target_geojson_path: str,
                                    fov: float = 10.0,
                                    interval_seconds: int = 600) -> Optional[Dict]:
        """
        步骤2: 使用get_observation_overlap.py获取重叠率
        
        Args:
            tle_dict: 卫星TLE数据字典
            start_time_str: 开始时间字符串
            end_time_str: 结束时间字符串
            target_geojson_path: 目标区域GeoJSON文件路径
            fov: 视场角度
            interval_seconds: 时间间隔（秒）
            
        Returns:
            重叠率计算结果
        """
        print("=" * 60)
        print("步骤2: 计算卫星观测重叠率")
        print("=" * 60)
        
        try:
            url = f"{self.base_url}/get_observation_overlap"
            payload = {
                "tle_dict": tle_dict,
                "start_time_str": start_time_str,
                "end_time_str": end_time_str,
                "target_geojson_path": target_geojson_path,
                "fov": fov,
                "interval_seconds": interval_seconds
            }
            
            print(f"🔄 正在计算 {len(tle_dict)} 颗卫星的重叠率...")
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result["success"]:
                coverage_results = result["coverage_results"]
                print(f"✅ 成功计算重叠率")
                print(f"📊 有重叠的卫星数量: {len(coverage_results)}")
                
                # 显示覆盖率统计
                for sat_name, coverage_data in coverage_results.items():
                    coverage_ratio = coverage_data.get('coverage_ratio', 0)
                    print(f"   📡 {sat_name}: 覆盖率 {coverage_ratio:.2%}")
                
                return coverage_results
            else:
                print(f"❌ 计算重叠率失败: {result['message']}")
                return None
                
        except Exception as e:
            print(f"❌ 步骤2执行失败: {e}")
            return None
    
    def step3_query_sensors_for_doci(self,
                                   db_path: str,
                                   mission_theme: Optional[str] = None,
                                   sensor_type: Optional[str] = None) -> Optional[Dict]:
        """
        步骤3: 使用query_utils.py查询计算DOCI的相关参数
        
        Args:
            db_path: 传感器数据库路径
            mission_theme: 任务主题
            sensor_type: 传感器类型
            
        Returns:
            传感器数据字典
        """
        print("=" * 60)
        print("步骤3: 查询传感器数据用于DOCI计算")
        print("=" * 60)
        
        try:
            url = f"{self.base_url}/query_sensors"
            payload = {
                "db_path": db_path
            }
            
            if mission_theme:
                payload["mission_theme"] = mission_theme
            if sensor_type:
                payload["sensor_type"] = sensor_type
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result["success"]:
                sensors_data = result["data"]
                print(f"✅ 成功查询到 {len(sensors_data)} 个传感器")
                
                # 显示传感器信息摘要
                for i, (sensor_name, sensor_data) in enumerate(sensors_data.items()):
                    if i >= 3:  # 只显示前3个
                        print(f"   ... 还有 {len(sensors_data) - 3} 个传感器")
                        break
                    spatial_res = sensor_data.get('spatial_resolution_m', 'N/A')
                    temporal_res = sensor_data.get('temporal_resolution_days', 'N/A')
                    print(f"   🔍 {sensor_name}: 空间分辨率 {spatial_res}m, 时间分辨率 {temporal_res}天")
                
                return sensors_data
            else:
                print(f"❌ 查询传感器数据失败")
                return None
                
        except Exception as e:
            print(f"❌ 步骤3执行失败: {e}")
            return None
    
    def step4_calculate_doci(self,
                           sensors_data: Dict,
                           scenario_config: Dict) -> Optional[Dict]:
        """
        步骤4: 使用DOCI.py计算DOCI并返回结果
        
        Args:
            sensors_data: 传感器数据字典
            scenario_config: 场景配置
            
        Returns:
            DOCI计算结果
        """
        print("=" * 60)
        print("步骤4: 计算DOCI评估结果")
        print("=" * 60)
        
        try:
            url = f"{self.base_url}/calculate_doci"
            payload = {
                "sensors_data": sensors_data,
                "scenario_config": scenario_config
            }
            
            print(f"�� 正在计算 {len(sensors_data)} 个传感器的DOCI...")
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if result["success"]:
                doci_data = result["data"]
                print(f"✅ 成功计算DOCI评估结果")
                
                # 显示DOCI结果摘要
                if "results" in doci_data and doci_data["results"]:
                    print(f"📊 评估结果 (前5名):")
                    for i, sensor_result in enumerate(doci_data["results"][:5]):
                        rank = sensor_result["rank"]
                        name = sensor_result["name"]
                        doci_score = sensor_result["components"]["DOCI"]
                        print(f"   🏆 第{rank}名: {name} (DOCI: {doci_score:.4f})")
                else:
                    print("📊 没有有效的评估结果")
                
                return doci_data
            else:
                print(f"❌ 计算DOCI失败")
                return None
                
        except Exception as e:
            print(f"❌ 步骤4执行失败: {e}")
            return None
    
    def run_complete_test_chain(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行完整的测试工具链
        
        Args:
            config: 测试配置字典
            
        Returns:
            完整的测试结果
        """
        print("🚀 开始运行完整的地理空间智能API测试工具链")
        print("=" * 80)
        
        # 检查API健康状态
        if not self.test_api_health():
            return {"error": "API服务不可用"}
        
        results = {}
        
        # 步骤1: 获取卫星TLE数据
        tle_data = self.step1_get_satellite_tle(
            satellite_db_path=config["satellite_db_path"],
            mission_theme=config.get("mission_theme", "Land cover"),
            sensor_type=config.get("sensor_type", "Optical Sensor")
        )
        results["step1_tle_data"] = tle_data
        
        if not tle_data:
            return {"error": "步骤1失败，无法获取TLE数据"}
        
        # 步骤2: 计算观测重叠率
        overlap_results = self.step2_get_observation_overlap(
            tle_dict=tle_data,
            start_time_str=config["start_time_str"],
            end_time_str=config["end_time_str"],
            target_geojson_path=config["target_geojson_path"],
            fov=config.get("fov", 10.0),
            interval_seconds=config.get("interval_seconds", 600)
        )
        results["step2_overlap_results"] = overlap_results
        
        # 步骤3: 查询传感器数据
        sensors_data = self.step3_query_sensors_for_doci(
            db_path=config["sensors_db_path"],
            mission_theme=config.get("doci_mission_theme"),
            sensor_type=config.get("doci_sensor_type")
        )
        results["step3_sensors_data"] = sensors_data
        
        if not sensors_data:
            return {"error": "步骤3失败，无法获取传感器数据"}
        
        # 步骤4: 计算DOCI
        doci_results = self.step4_calculate_doci(
            sensors_data=sensors_data,
            scenario_config=config["doci_scenario_config"]
        )
        results["step4_doci_results"] = doci_results
        
        print("=" * 80)
        print("🎉 完整测试工具链执行完成!")
        print("=" * 80)
        
        return results


def main():
    """主函数 - 运行测试示例"""
    
    # 测试配置
    test_config = {
        # 数据库路径
        "satellite_db_path": "D:\\GeoSensingAPI\\data\\satellite_data.db",
        "sensors_db_path": "D:\\GeoSensingAPI\\data\\sensors_enriched.db",
        
        # 卫星查询参数
        "mission_theme": "Land cover",
        "sensor_type": "Optical Sensor",
        
        # 时间窗口
        "start_time_str": "2025-08-01 00:00:00.000",
        "end_time_str": "2025-08-01 23:59:59.000",
        
        # 目标区域
        "target_geojson_path": "D:\\GeoSensingAPI\\data\\Wuhan.geojson",
        
        # 观测参数
        "fov": 10.0,
        "interval_seconds": 600,
        
        # DOCI查询参数
        "doci_mission_theme": "Cloud",
        "doci_sensor_type": None,
        
        # DOCI场景配置
        "doci_scenario_config": {
            "description": "DOCI评估测试",
            "time_window": {
                "start": "2025-08-01 00:00:00.000",
                "end": "2025-08-01 23:59:59.000"
            },
            "target_area_geojson_path": "D:\\GeoSensingAPI\\data\\Wuhan.geojson",
            "environment": {
                "cloudiness_forecast": 0.45
            },
            "models": {
                "doci": {
                    "description": "DOCI模型测试",
                    "theme": "Disaster Monitoring",
                    "requirements": {
                        "spatial_res": [50, 20, 5],
                        "temporal_res": [5, 2, 1]
                    },
                    "ahp_weights": [0.7, 0.3]
                }
            }
        }
    }
    
    # 创建测试工具链实例
    test_chain = GeoSensingAPITestChain()
    
    # 运行完整测试
    results = test_chain.run_complete_test_chain(test_config)
    
    # 保存结果到文件
    output_file = "test_chain_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"�� 测试结果已保存到: {output_file}")
    
    # 显示最终结果摘要
    if "error" not in results:
        print("\n�� 测试结果摘要:")
        print(f"   ��️  获取卫星数量: {len(results.get('step1_tle_data', {}))}")
        print(f"   📊 重叠率计算: {'成功' if results.get('step2_overlap_results') else '失败'}")
        print(f"   🔍 传感器查询: {len(results.get('step3_sensors_data', {}))} 个")
        print(f"   �� DOCI评估: {'成功' if results.get('step4_doci_results') else '失败'}")
    else:
        print(f"❌ 测试失败: {results['error']}")


if __name__ == "__main__":
    main()