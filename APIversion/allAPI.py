# -*- coding: utf-8 -*-
"""
PROJECT_NAME: GeoSensingAPI 
FILE_NAME: allAPI 
AUTHOR: welt 
E_MAIL: tjlwelt@foxmail.com
DATE: 2025-09-11 
"""

# 添加项目根目录和当前目录到Python路径
import sys
import os

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 添加当前目录（APIversion）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# main_api.py
import uvicorn
from fastapi import FastAPI

# 导入您提供的四个API模块中的FastAPI应用实例
# 为了避免命名冲突，我们使用 "as" 关键字为它们指定了不同的别名
from geopandas_api import app as geopandas_app
from satellite_api import app as satellite_app
from deploy_api import app as deploy_app
from evaluation_api import app as evaluation_app


# 初始化一个主FastAPI应用实例
# 我们为这个综合API服务设置了新的标题和描述
app = FastAPI(
	title="综合地理空间智能工具 API",
	description="一个集成了地理空间处理(GeoPandasTool)、卫星工具(SatelliteTool)、传感器部署(DeployTool)和模型评估(EvaluationTool)功能的综合API服务。",
	version="1.0.0",
)

# --- 路由挂载 ---
# 使用 include_router 将各个子应用的路由合并到主应用中
# 关键点：我们不设置 prefix 参数，这样所有的路由都会被挂载在根路径 "/" 下
# 我们使用 tags 参数为来自不同文件的API进行分组，以便在API文档中清晰地展示
app.include_router(geopandas_app.router, tags=["地理空间处理 (GeoPandasTool)"])
app.include_router(satellite_app.router, tags=["卫星工具 (SatelliteTool)"])
app.include_router(deploy_app.router, tags=["传感器部署 (DeployTool)"])
app.include_router(evaluation_app.router, tags=["模型评估 (EvaluationTool)"])


@app.get("/", tags=["根路径 (Root)"])
def read_root():
	"""
    访问API根路径，返回欢迎信息。
    可用于简单的健康检查。
    """
	return {"message": "欢迎使用综合地理空间智能工具 API"}


# 当直接运行此文件时，启动Uvicorn服务
if __name__ == "__main__":
	# 建议使用 8000 端口作为主服务的端口
	print("启动综合API服务，请访问 http://127.0.0.1:8000")
	print("API文档地址: http://127.0.0.1:8000/docs")
	uvicorn.run(app, host="0.0.0.0", port=8000)
