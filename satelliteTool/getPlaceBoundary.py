import os
import requests
import osm2geojson
import json
from typing import List, Union, Dict
import sys

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import get_geojson_path

OVERPASS_URL = "http://overpass-api.de/api/interpreter"

def fetch_boundary_and_save(place_name: str) -> Union[str, Dict[str, str]]:
    """
    获取单个地名的边界并保存为 GeoJSON 文件，返回文件路径或错误信息。
    """
    query = f"""
    [out:xml][timeout:25];
    relation["name:en"="{place_name}"]["boundary"="administrative"];
    out body;
    >;
    out skel qt;
    """
    response = requests.get(OVERPASS_URL, params={'data': query})

    if response.status_code == 200:
        geojson_data = osm2geojson.xml2geojson(response.text)
        file_path = get_geojson_path(f"{place_name.replace(' ', '_')}.geojson")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        return file_path
    else:
        return f"Error: HTTP {response.status_code}"

def get_boundary(place_names: Union[str, List[str]]) -> Union[str, Dict[str, str]]:
    """
    获取一个或多个地名的行政边界，并返回本地保存路径。
    :param place_names: 地名字符串或字符串列表
    :return: 单个路径或 {place_name: 路径}
    """
    # 如果是单个字符串，转为列表处理
    is_single = isinstance(place_names, str)
    names = [place_names] if is_single else place_names
    results = {}
    
    for name in names:
        result = fetch_boundary_and_save(name)
        results[name] = result
    
    return results[place_names] if is_single else results

if __name__ == "__main__":
    # 测试代码
    result = get_boundary("Wuhan")
    print(f"结果: {result}")
