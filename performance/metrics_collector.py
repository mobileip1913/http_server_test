"""
指标收集器：收集和统计测试指标
"""
import json
import csv
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from logger import Logger
from config import Config
from utils import (
    calculate_statistics, 
    ensure_directory,
    sanitize_filename,
    format_timestamp
)

class MetricsCollector:
    """指标收集器类"""
    
    def __init__(self):
        self.logger = Logger()
        self.metrics: List[Dict[str, Any]] = []
        self.test_start_time: Optional[float] = None
        self.test_end_time: Optional[float] = None
        
        # 确保目录存在
        Config.create_directories()
        
        # 生成测试时间戳
        self.test_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    def start_test(self):
        """开始测试"""
        import time
        self.test_start_time = time.time()
        self.logger.info("测试开始")
    
    def end_test(self):
        """结束测试"""
        import time
        self.test_end_time = time.time()
        self.logger.info("测试结束")
    
    def add_metrics(self, metrics: Dict[str, Any]):
        """添加连接指标"""
        self.metrics.append(metrics)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取测试摘要"""
        if not self.metrics:
            return {
                "total_connections": 0,
                "successful_connections": 0,
                "failed_connections": 0,
                "connection_success_rate": 0.0,
                "total_messages": 0,
                "successful_messages": 0,
                "failed_messages": 0,
                "message_success_rate": 0.0,
                "avg_connect_time": 0.0,
                "avg_audio_to_tts_delay": 0.0,
                "p95_audio_to_tts_delay": 0.0,
                "p99_audio_to_tts_delay": 0.0,
                "min_audio_to_tts_delay": 0.0,
                "max_audio_to_tts_delay": 0.0,
                "avg_audio_to_second_tts_delay": 0.0,
                "p95_audio_to_second_tts_delay": 0.0,
                "p99_audio_to_second_tts_delay": 0.0,
                "min_audio_to_second_tts_delay": 0.0,
                "max_audio_to_second_tts_delay": 0.0,
                "qps": 0.0,
                "test_duration": 0.0
            }
        
        total_connections = len(self.metrics)
        successful_connections = sum(1 for m in self.metrics if m.get("connect_status") == "success")
        failed_connections = total_connections - successful_connections
        
        successful_metrics = [m for m in self.metrics if m.get("connect_status") == "success"]
        total_messages = sum(1 for m in successful_metrics if m.get("send_time") is not None)
        successful_messages = sum(1 for m in successful_metrics if m.get("complete", False))
        failed_messages = total_messages - successful_messages
        
        # 计算连接时间统计
        connect_times = [
            m.get("connect_time") 
            for m in self.metrics 
            if m.get("connect_time") is not None
        ]
        connect_stats = calculate_statistics(connect_times) if connect_times else {}
        
        # 计算从发送语音结束到TTS开始的延迟统计（客户端可测量的指标）
        # 只统计有完整数据的情况（有send_end_time和tts_start_time）
        audio_to_tts_delays = [
            m.get("audio_to_tts_delay")
            for m in successful_metrics
            if m.get("audio_to_tts_delay") is not None and m.get("audio_to_tts_delay") > 0
        ]
        audio_to_tts_stats = calculate_statistics(audio_to_tts_delays) if audio_to_tts_delays else {}
        
        # 计算从发送语音结束到第二句TTS开始的延迟统计（跳过第一句"好嘞，请稍等，正在处理中"）
        audio_to_second_tts_delays = [
            m.get("audio_to_second_tts_delay")
            for m in successful_metrics
            if m.get("audio_to_second_tts_delay") is not None and m.get("audio_to_second_tts_delay") > 0
        ]
        audio_to_second_tts_stats = calculate_statistics(audio_to_second_tts_delays) if audio_to_second_tts_delays else {}
        
        # 计算 QPS 和吞吐量
        duration = (self.test_end_time - self.test_start_time) if self.test_end_time and self.test_start_time else 0
        qps = total_messages / duration if duration > 0 else 0.0
        success_rate = (successful_messages / total_messages * 100) if total_messages > 0 else 0.0
        
        return {
            "total_connections": total_connections,
            "successful_connections": successful_connections,
            "failed_connections": failed_connections,
            "connection_success_rate": (successful_connections / total_connections * 100) if total_connections > 0 else 0.0,
            "total_messages": total_messages,
            "successful_messages": successful_messages,
            "failed_messages": failed_messages,
            "message_success_rate": success_rate,
            "avg_connect_time": connect_stats.get("avg", 0.0),
            "avg_audio_to_tts_delay": audio_to_tts_stats.get("avg", 0.0),
            "p95_audio_to_tts_delay": audio_to_tts_stats.get("p95", 0.0),
            "p99_audio_to_tts_delay": audio_to_tts_stats.get("p99", 0.0),
            "min_audio_to_tts_delay": audio_to_tts_stats.get("min", 0.0),
            "max_audio_to_tts_delay": audio_to_tts_stats.get("max", 0.0),
            "avg_audio_to_second_tts_delay": audio_to_second_tts_stats.get("avg", 0.0),
            "p95_audio_to_second_tts_delay": audio_to_second_tts_stats.get("p95", 0.0),
            "p99_audio_to_second_tts_delay": audio_to_second_tts_stats.get("p99", 0.0),
            "min_audio_to_second_tts_delay": audio_to_second_tts_stats.get("min", 0.0),
            "max_audio_to_second_tts_delay": audio_to_second_tts_stats.get("max", 0.0),
            "qps": qps,
            "test_duration": duration
        }
    
    def export_csv(self) -> str:
        """导出 CSV 文件"""
        if not self.metrics:
            self.logger.warning("没有指标数据可导出")
            return ""
        
        filename = sanitize_filename(f"test_results_{self.test_timestamp}.csv")
        filepath = Path(Config.CSV_DIR) / filename
        
        # CSV 列定义
        fieldnames = [
            "connection_id",
            "connect_time",
            "connect_status",
            "send_time",
            "send_end_time",
            "stt_time",
            "llm_time",
            "tts_start_time",
            "tts_second_sentence_time",
            "tts_duration",
            "total_response_time",
            "audio_to_tts_delay",
            "audio_to_second_tts_delay",
            "message_size",
            "response_size",
            "complete",
            "error_type",
            "error_message"
        ]
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for metrics in self.metrics:
                row = {field: metrics.get(field, "") for field in fieldnames}
                writer.writerow(row)
        
        self.logger.info(f"CSV 已导出到: {filepath}")
        return str(filepath)
    
    def export_json(self) -> str:
        """导出 JSON 文件"""
        summary = self.get_summary()
        
        test_info = {
            "start_time": format_timestamp(self.test_start_time) if self.test_start_time else None,
            "end_time": format_timestamp(self.test_end_time) if self.test_end_time else None,
            "duration": (self.test_end_time - self.test_start_time) if self.test_end_time and self.test_start_time else 0,
            "concurrent_connections": Config.CONCURRENT_CONNECTIONS,
            "test_message": Config.TEST_MESSAGE
        }
        
        data = {
            "test_info": test_info,
            "summary": summary,
            "connections": self.metrics
        }
        
        filename = sanitize_filename(f"test_results_{self.test_timestamp}.json")
        filepath = Path(Config.JSON_DIR) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"JSON 已导出到: {filepath}")
        return str(filepath)
    
    def print_summary(self):
        """打印测试摘要"""
        summary = self.get_summary()
        
        self.logger.info("=" * 60)
        self.logger.info("性能测试摘要")
        self.logger.info("=" * 60)
        self.logger.info(f"测试总时长: {summary['test_duration']:.2f}秒")
        self.logger.info("")
        self.logger.info("连接指标:")
        self.logger.info(f"  总连接数: {summary['total_connections']}")
        self.logger.info(f"  成功连接数: {summary['successful_connections']}")
        self.logger.info(f"  失败连接数: {summary['failed_connections']}")
        self.logger.info(f"  连接成功率: {summary['connection_success_rate']:.2f}%")
        avg_connect_sec = summary['avg_connect_time'] / 1000.0 if summary['avg_connect_time'] else 0.0
        self.logger.info(f"  平均连接时间: {avg_connect_sec:.3f}秒")
        self.logger.info("")
        self.logger.info("消息指标:")
        self.logger.info(f"  总消息数: {summary['total_messages']}")
        self.logger.info(f"  成功消息数: {summary['successful_messages']}")
        self.logger.info(f"  失败消息数: {summary['failed_messages']}")
        self.logger.info(f"  消息成功率: {summary['message_success_rate']:.2f}%")
        self.logger.info("")
        self.logger.info("响应延迟指标:")
        avg_delay_sec = summary['avg_audio_to_tts_delay'] / 1000.0 if summary['avg_audio_to_tts_delay'] else 0.0
        p95_delay_sec = summary['p95_audio_to_tts_delay'] / 1000.0 if summary['p95_audio_to_tts_delay'] else 0.0
        p99_delay_sec = summary['p99_audio_to_tts_delay'] / 1000.0 if summary['p99_audio_to_tts_delay'] else 0.0
        min_delay_sec = summary['min_audio_to_tts_delay'] / 1000.0 if summary['min_audio_to_tts_delay'] else 0.0
        max_delay_sec = summary['max_audio_to_tts_delay'] / 1000.0 if summary['max_audio_to_tts_delay'] else 0.0
        self.logger.info(f"  平均延迟（发送语音结束→第一句TTS开始）: {avg_delay_sec:.3f}秒")
        self.logger.info(f"  P95延迟: {p95_delay_sec:.3f}秒")
        self.logger.info(f"  P99延迟: {p99_delay_sec:.3f}秒")
        self.logger.info(f"  最小延迟: {min_delay_sec:.3f}秒")
        self.logger.info(f"  最大延迟: {max_delay_sec:.3f}秒")
        self.logger.info("")
        self.logger.info("响应延迟指标（跳过第一句）:")
        avg_second_delay_sec = summary['avg_audio_to_second_tts_delay'] / 1000.0 if summary['avg_audio_to_second_tts_delay'] else 0.0
        p95_second_delay_sec = summary['p95_audio_to_second_tts_delay'] / 1000.0 if summary['p95_audio_to_second_tts_delay'] else 0.0
        p99_second_delay_sec = summary['p99_audio_to_second_tts_delay'] / 1000.0 if summary['p99_audio_to_second_tts_delay'] else 0.0
        min_second_delay_sec = summary['min_audio_to_second_tts_delay'] / 1000.0 if summary['min_audio_to_second_tts_delay'] else 0.0
        max_second_delay_sec = summary['max_audio_to_second_tts_delay'] / 1000.0 if summary['max_audio_to_second_tts_delay'] else 0.0
        self.logger.info(f"  平均延迟（发送语音结束→第二句TTS开始）: {avg_second_delay_sec:.3f}秒")
        self.logger.info(f"  P95延迟: {p95_second_delay_sec:.3f}秒")
        self.logger.info(f"  P99延迟: {p99_second_delay_sec:.3f}秒")
        self.logger.info(f"  最小延迟: {min_second_delay_sec:.3f}秒")
        self.logger.info(f"  最大延迟: {max_second_delay_sec:.3f}秒")
        self.logger.info("")
        self.logger.info("吞吐量指标:")
        self.logger.info(f"  QPS (每秒查询数): {summary['qps']:.2f}")
        self.logger.info("=" * 60)
        
        # 记录统计日志
        self.logger.statistics(
            summary['total_connections'],
            summary['successful_connections'],
            summary['successful_connections'],
            summary['failed_connections'],
            summary['qps'],
            None,  # avg_response_time (服务器端指标，已移除)
            None,  # p95_response_time (服务器端指标，已移除)
            None   # p99_response_time (服务器端指标，已移除)
        )
    
    def export_all(self):
        """导出所有格式的数据"""
        csv_file = self.export_csv()
        json_file = self.export_json()
        self.print_summary()
        return csv_file, json_file

