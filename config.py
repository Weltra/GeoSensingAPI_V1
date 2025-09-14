# -*- coding: utf-8 -*-
"""
全局配置文件
设置全局的 geojson 文件夹路径
"""

import os

# 全局 geojson 文件夹路径
GLOBAL_GEOJSON_DIR = os.path.join(os.path.dirname(__file__), "geojson")

# 确保全局 geojson 目录存在
os.makedirs(GLOBAL_GEOJSON_DIR, exist_ok=True)

def get_geojson_path(filename: str) -> str:
    """
    获取全局 geojson 目录下的文件路径
    
    Args:
        filename: 文件名（不包含子目录）
    
    Returns:
        完整的文件路径
    """
    return os.path.join(GLOBAL_GEOJSON_DIR, filename)

def save_geojson_file(filename: str, data: dict) -> str:
    """
    保存 geojson 数据到全局目录
    
    Args:
        filename: 文件名
        data: geojson 数据字典
    
    Returns:
        保存的文件路径
    """
    import json
    file_path = get_geojson_path(filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return file_path 
