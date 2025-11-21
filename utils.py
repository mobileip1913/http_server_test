"""
工具函数：提供辅助功能
"""
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

def get_timestamp() -> float:
    """获取当前时间戳（毫秒）"""
    return time.time() * 1000

def format_timestamp(timestamp: Optional[float] = None) -> str:
    """格式化时间戳为字符串"""
    if timestamp is None:
        timestamp = time.time()
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def calculate_percentile(values: List[float], percentile: float) -> float:
    """计算百分位数（P95, P99等）"""
    if not values:
        return 0.0
    
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100.0)
    if index >= len(sorted_values):
        index = len(sorted_values) - 1
    return sorted_values[index]

def calculate_statistics(values: List[float]) -> Dict[str, float]:
    """计算统计信息（平均值、最小值、最大值、P95、P99）"""
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "avg": 0.0,
            "p95": 0.0,
            "p99": 0.0
        }
    
    sorted_values = sorted(values)
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "p95": calculate_percentile(sorted_values, 95),
        "p99": calculate_percentile(sorted_values, 99)
    }

def parse_json_message(message: str) -> Optional[Dict[str, Any]]:
    """解析 JSON 消息"""
    try:
        return json.loads(message)
    except json.JSONDecodeError as e:
        return None

def escape_json_string(s: str) -> str:
    """转义 JSON 字符串中的特殊字符"""
    return json.dumps(s)[1:-1]  # 去掉首尾的引号

def generate_session_id() -> str:
    """生成会话ID"""
    import uuid
    return str(uuid.uuid4())

def sanitize_filename(filename: str) -> str:
    """清理文件名，移除不合法字符"""
    import re
    # 移除或替换不合法字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return filename

def ensure_directory(path: str):
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)

