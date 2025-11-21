"""
日志记录器：提供分级日志功能
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import Config

class Logger:
    """日志记录器类"""
    
    _instance: Optional['Logger'] = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.logger = logging.getLogger("websocket_performance_test")
        self.logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
        
        # 清除已有的处理器
        self.logger.handlers.clear()
        
        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台输出
        if Config.LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # 文件输出
        if Config.LOG_TO_FILE:
            Config.create_directories()
            log_file = Path(Config.LOGS_DIR) / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
            self.log_file_path = str(log_file)
        else:
            self.log_file_path = None
    
    def debug(self, message: str):
        """DEBUG 级别日志"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """INFO 级别日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """WARNING 级别日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """ERROR 级别日志"""
        self.logger.error(message)
    
    def connection(self, connection_id: int, status: str, duration: Optional[float] = None, url: Optional[str] = None):
        """记录连接日志"""
        message = f"Connection #{connection_id} | Status: {status}"
        if duration is not None:
            message += f" | Duration: {duration:.2f}ms"
        # 移除 URL 输出（太长，日志太多）
        self.info(f"[CONNECTION] {message}")
    
    def message(self, connection_id: int, msg_type: str, direction: str, size: Optional[int] = None, duration: Optional[float] = None):
        """记录消息日志"""
        message = f"Connection #{connection_id} | Type: {msg_type} | Direction: {direction}"
        if size is not None:
            message += f" | Size: {size}bytes"
        if duration is not None:
            message += f" | Duration: {duration:.2f}ms"
        self.info(f"[MESSAGE] {message}")
    
    def response(self, connection_id: int, message_type: str, stt_time: Optional[float] = None, 
                 llm_time: Optional[float] = None, tts_time: Optional[float] = None, 
                 total_time: Optional[float] = None):
        """记录响应日志"""
        message = f"Connection #{connection_id} | Message Type: {message_type}"
        if stt_time is not None:
            message += f" | STT Time: {stt_time:.2f}ms"
        if llm_time is not None:
            message += f" | LLM Time: {llm_time:.2f}ms"
        if tts_time is not None:
            message += f" | TTS Time: {tts_time:.2f}ms"
        if total_time is not None:
            message += f" | Total: {total_time:.2f}ms"
        self.info(f"[RESPONSE] {message}")
    
    def error_log(self, connection_id: int, error_type: str, error_message: str):
        """记录错误日志"""
        self.error(f"[ERROR] Connection #{connection_id} | Error Type: {error_type} | Error Message: {error_message}")
    
    def statistics(self, total: int, active: int, success: int, failed: int, 
                   qps: Optional[float] = None, avg_response: Optional[float] = None,
                   p95: Optional[float] = None, p99: Optional[float] = None):
        """记录统计日志"""
        message = (f"Total Connections: {total} | Active: {active} | "
                  f"Success: {success} | Failed: {failed}")
        if qps is not None:
            message += f" | QPS: {qps:.2f}"
        if avg_response is not None:
            message += f" | Avg Response: {avg_response:.2f}ms"
        if p95 is not None:
            message += f" | P95: {p95:.2f}ms"
        if p99 is not None:
            message += f" | P99: {p99:.2f}ms"
        self.info(f"[STATISTICS] {message}")

