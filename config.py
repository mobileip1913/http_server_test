"""
配置文件：定义测试参数和配置项
"""
import os
import hashlib
from typing import Dict, Any, Tuple, Optional

class Config:
    """测试配置类"""
    
    # WebSocket 服务器配置
    # 默认连接到生产环境服务器
    # 可以通过环境变量 WS_SERVER_HOST 覆盖
    WS_SERVER_HOST = os.getenv("WS_SERVER_HOST", "ws://192.168.110.127:8081")
    WSS_SERVER_HOST = os.getenv("WSS_SERVER_HOST", "wss://toyaiws.spacechaintech.com")  # wss默认443端口，不需要显式指定
    
    # 使用 WS 还是 WSS
    USE_SSL = os.getenv("USE_SSL", "false").lower() == "true"
    
    # 访问令牌（已移除，不再使用）
    # ACCESS_TOKEN = os.getenv("WEBSOCKET_ACCESS_TOKEN", "")
    
    # 是否发送音频数据（true=发送Opus音频，false=只发送文本消息用于快速测试）
    SEND_AUDIO_DATA = os.getenv("SEND_AUDIO_DATA", "true").lower() == "true"
    
    # 是否分割Opus包（true=分割为多个独立包逐个发送，false=不分割，直接发送整个连续数据）
    # 硬编码为不分割，直接发送整个连续数据
    SPLIT_OPUS_PACKETS = False
    
    # 音频文件路径（如果使用预录制的音频文件）
    # 默认使用本地生成的测试音频文件（如果存在）
    DEFAULT_AUDIO_FILE = os.path.join(os.path.dirname(__file__), "audio", "test_audio.opus")
    AUDIO_FILE_PATH = os.getenv("AUDIO_FILE_PATH", DEFAULT_AUDIO_FILE if os.path.exists(DEFAULT_AUDIO_FILE) else "")
    
    # 音频格式参数（与实际设备保持一致）
    AUDIO_SAMPLE_RATE = 16000  # 16kHz
    AUDIO_CHANNELS = 1  # 单声道
    OPUS_FRAME_DURATION_MS = 60  # 60ms 帧长度
    OPUS_FRAME_SIZE = AUDIO_SAMPLE_RATE * OPUS_FRAME_DURATION_MS // 1000  # 960 samples per frame
    OPUS_COMPLEXITY = 3  # Opus 编码复杂度（WiFi 板使用 3，ML307 使用 5）
    MAX_OPUS_PACKET_SIZE = 1000  # 最大 Opus 数据包大小（字节）
    
    # 音频发送模式
    # "continuous": 持续输入模式 - 按照实际时间间隔发送（模拟真实采集节奏）
    #   - 硬件编码：每30ms发送一个包
    #   - 软件编码：每60ms发送一个包
    # "batch": 批量发送模式 - 连续发送所有包，没有间隔（模拟MainLoop批量发送）
    AUDIO_SEND_MODE = os.getenv("AUDIO_SEND_MODE", "continuous")  # 默认持续输入模式
    
    # 音频发送间隔（仅在AUDIO_SEND_MODE="continuous"时生效）
    # 硬件编码模式：30ms（每30ms一个Opus包）
    # 软件编码模式：60ms（每60ms一个Opus包）
    AUDIO_SEND_INTERVAL_MS = float(os.getenv("AUDIO_SEND_INTERVAL_MS", "60"))  # 默认60ms，模拟软件编码（60ms帧长度）
    
    # 设备信息（使用已注册的实际设备信息作为默认值）
    DEVICE_SN = os.getenv("DEVICE_SN", "FC012C2EA0E4")  # 测试设备 SN
    DEVICE_SIGN = os.getenv("DEVICE_SIGN", "c61505cccb8dc83d8e67450cbd4f32c4")
    BOARD_ID = os.getenv("BOARD_ID", "TKAI_BOARD_03_4G_VB6824_EYE_ST7789")
    FIRMWARE_VERSION = os.getenv("FIRMWARE_VERSION", "0.0.1")
    FIRMWARE_VERSION_CODE = os.getenv("FIRMWARE_VERSION_CODE", "20250908001")
    STRATEGY_ID = int(os.getenv("STRATEGY_ID", "0"))
    DEVICE_UID = int(os.getenv("DEVICE_UID", "0"))
    BOARD_TYPE = os.getenv("BOARD_TYPE", "ml307")
    RECOVER = int(os.getenv("RECOVER", "0"))
    SCREEN = int(os.getenv("SCREEN", "1"))
    
    # 测试参数
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"  # 调试模式：只发送1个连接
    CONCURRENT_CONNECTIONS = int(os.getenv("CONCURRENT_CONNECTIONS", "1"))  # 并发连接数，默认1
    TEST_MESSAGE = os.getenv("TEST_MESSAGE", "你好啊，我想去故宫")
    
    # 监听模式（与实际设备保持一致）
    # "realtime": 持续监听模式（AlwaysOn）- 不会自动停止
    # "auto": 自动停止模式（AutoStop）- 服务器通过VAD自动检测并处理
    #   ⚠️ 注意：如果使用auto模式，服务端有bug会导致音频被丢弃（state=="asr"时vad_side未设置）
    # "manual": 手动停止模式（ManualStop）- 需要发送stop_listen（推荐用于测试，避免服务端bug）
    LISTENING_MODE = os.getenv("LISTENING_MODE", "manual")  # 默认使用manual模式，避免服务端ASR路径bug
    
    # 是否在发送完音频后发送stop_listen
    # 对于auto模式，服务器可能自动检测，但发送stop_listen可以确保服务器开始处理
    # 对于manual模式，必须发送stop_listen
    SEND_STOP_LISTEN = os.getenv("SEND_STOP_LISTEN", "true").lower() == "true"
    
    # 硬件模拟与心跳
    USE_IOT_SIMULATOR = os.getenv("USE_IOT_SIMULATOR", "true").lower() == "true"
    HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "false").lower() == "true"
    HEARTBEAT_INTERVAL_SEC = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "10"))
    
    @classmethod
    def get_concurrent_connections(cls) -> int:
        """获取实际并发连接数（调试模式返回1，否则返回配置值）"""
        if cls.DEBUG_MODE:
            return 1
        return cls.CONCURRENT_CONNECTIONS
    
    # 超时设置（毫秒）
    CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT", "10000"))  # 10秒
    MESSAGE_TIMEOUT = int(os.getenv("MESSAGE_TIMEOUT", "30000"))  # 30秒
    STT_TIMEOUT = int(os.getenv("STT_TIMEOUT", "5000"))  # 5秒
    TTS_TIMEOUT = int(os.getenv("TTS_TIMEOUT", "60000"))  # 60秒
    
    # 测试模式
    # "normal": 正常模式 - 等待完整响应（TTS stop）后再进行下一个问题
    # "fast": 急速模式 - 只要大模型开始回复（has_llm + llm_text_buffer）就继续下一个问题
    TEST_MODE = os.getenv("TEST_MODE", "normal")  # 默认正常模式
    
    # 极限性能测试模式：减少等待时间以测试服务器极限并发处理能力
    # true=极限性能模式（减少等待，快速完成），false=完整响应模式（等待完整响应）
    STRESS_TEST_MODE = os.getenv("STRESS_TEST_MODE", "true").lower() == "true"
    
    # 极限性能模式下的优化设置（仅在STRESS_TEST_MODE=true时生效）
    STRESS_AUTH_WAIT_SEC = float(os.getenv("STRESS_AUTH_WAIT_SEC", "0.5"))  # 等待auth时间（秒），极限模式减少到0.5秒
    # 响应等待时间：根据并发数动态调整，确保有足够时间处理所有请求
    # 基础等待时间 + 并发数 * 每个连接额外等待时间
    # 注意：连接在1秒内均匀分布，最后一个连接需要额外等待时间
    STRESS_RESPONSE_BASE_SEC = float(os.getenv("STRESS_RESPONSE_BASE_SEC", "15.0"))  # 基础等待时间（秒），增加到15秒
    STRESS_RESPONSE_PER_CONN_SEC = float(os.getenv("STRESS_RESPONSE_PER_CONN_SEC", "0.15"))  # 每个连接额外等待时间（秒），增加到0.15秒
    STRESS_RESPONSE_MAX_SEC = float(os.getenv("STRESS_RESPONSE_MAX_SEC", "60.0"))  # 最大等待时间（秒），增加到60秒
    STRESS_FINAL_WAIT_SEC = float(os.getenv("STRESS_FINAL_WAIT_SEC", "0.1"))  # 最后等待时间（秒），极限模式减少到0.1秒
    
    @classmethod
    def get_stress_response_wait_sec(cls) -> float:
        """获取极限性能模式下的响应等待时间（根据并发数动态计算）"""
        if not cls.STRESS_TEST_MODE:
            return cls.TTS_TIMEOUT / 1000.0
        wait_time = cls.STRESS_RESPONSE_BASE_SEC + (cls.get_concurrent_connections() * cls.STRESS_RESPONSE_PER_CONN_SEC)
        return min(wait_time, cls.STRESS_RESPONSE_MAX_SEC)
    
    # 结果输出目录
    RESULTS_DIR = os.getenv("RESULTS_DIR", "results")
    LOGS_DIR = os.path.join(RESULTS_DIR, "logs")
    CSV_DIR = os.path.join(RESULTS_DIR, "csv")
    JSON_DIR = os.path.join(RESULTS_DIR, "json")
    
    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    LOG_TO_CONSOLE = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    
    @classmethod
    def calculate_sign(cls, device_sn: str) -> str:
        """
        根据SN计算鉴权sign
        公式: md5(sn + "a1c3e5f7890b2")
        与 ws_server/app/event/hw/base_event.js:33 中的逻辑一致
        """
        secret = "a1c3e5f7890b2"
        sign_input = device_sn + secret
        sign = hashlib.md5(sign_input.encode()).hexdigest()
        return sign
    
    @classmethod
    def get_websocket_url(cls, device_sn: Optional[str] = None) -> str:
        """构建 WebSocket 连接 URL"""
        host = cls.WSS_SERVER_HOST if cls.USE_SSL else cls.WS_SERVER_HOST
        
        # 如果提供了device_sn，使用它；否则使用默认值
        sn = device_sn if device_sn is not None else cls.DEVICE_SN
        
        # 根据SN动态计算sign（每个SN对应不同的sign）
        sign = cls.calculate_sign(sn)
        
        params = {
            "sn": sn,
            "sign": sign,
            "platform": "hw",
            "bid": cls.BOARD_ID,
            "fv": cls.FIRMWARE_VERSION,
            "fvc": cls.FIRMWARE_VERSION_CODE,
            "strategy_id": str(cls.STRATEGY_ID),
            "uid": str(cls.DEVICE_UID),
            "board_type": cls.BOARD_TYPE,
            "recover": str(cls.RECOVER),
            "enableP3": "2",
            "tool": "idf",
            "screen": str(cls.SCREEN)
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{host}/?{query_string}"
    
    @classmethod
    def get_headers(cls, device_sn: Optional[str] = None) -> Dict[str, str]:
        """
        获取 WebSocket 连接所需的 HTTP 头
        
        完全按照项目代码的格式：
        - Protocol-Version: "1"
        - Device-Id: MAC 地址（从 SystemInfo::GetMacAddress() 获取）
        - Authorization: "Bearer <token>" （可选，如果服务器不需要验证则不设置）
        """
        headers = {
            "Protocol-Version": "1",
        }
        
        # 如果提供了device_sn，使用它；否则使用默认值
        sn = device_sn if device_sn is not None else cls.DEVICE_SN
        
        # Device-Id: 项目代码使用 SystemInfo::GetMacAddress()
        # 这里从 SN 生成 MAC 地址格式（SN 通常是 12 位十六进制，如 FC012C2EA0A0）
        # 格式化为 MAC 地址：FC:01:2C:2E:A0:A0
        if len(sn) >= 12:
            mac_address = ":".join([
                sn[i:i+2] for i in range(0, 12, 2)
            ])
        else:
            # 如果 SN 格式不对，使用默认格式
            mac_address = ":".join([
                sn[i:i+2] if i+2 <= len(sn) else sn[i:]
                for i in range(0, len(sn), 2)
            ])
        headers["Device-Id"] = mac_address
        
        # Authorization: 项目代码设置了，但用户说服务器不需要验证
        # 如果未来需要，可以通过环境变量设置
        auth_token = os.getenv("WEBSOCKET_ACCESS_TOKEN", "")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        
        return headers
    
    @classmethod
    def create_directories(cls):
        """创建必要的目录"""
        directories = [cls.RESULTS_DIR, cls.LOGS_DIR, cls.CSV_DIR, cls.JSON_DIR]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    @classmethod
    def validate(cls) -> Tuple[bool, str]:
        """验证配置是否完整"""
        # ACCESS_TOKEN 现在是可选的（如果服务器不需要认证）
        
        if not cls.DEVICE_SN:
            return False, "DEVICE_SN 未设置"
        
        if not cls.DEVICE_SIGN:
            return False, "DEVICE_SIGN 未设置"
        
        if cls.CONCURRENT_CONNECTIONS <= 0:
            return False, "CONCURRENT_CONNECTIONS 必须大于 0"
        
        # 如果设置了发送音频数据，但没有提供音频文件，将在运行时生成
        if cls.SEND_AUDIO_DATA and cls.AUDIO_FILE_PATH:
            if not os.path.exists(cls.AUDIO_FILE_PATH):
                return False, f"音频文件不存在: {cls.AUDIO_FILE_PATH}"
        
        return True, "配置验证通过"

