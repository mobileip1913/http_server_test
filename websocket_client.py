"""
WebSocket 客户端封装：管理 WebSocket 连接和消息传输
"""
import asyncio
import json
import time
from typing import Optional, Callable, Dict, Any, List
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from logger import Logger
from config import Config
from utils import get_timestamp, parse_json_message

class WebSocketClient:
    """WebSocket 客户端类"""
    
    def __init__(self, connection_id: int, device_sn: Optional[str] = None):
        self.connection_id = connection_id
        self.device_sn = device_sn  # 设备SN，如果为None则使用Config中的默认值
        self.logger = Logger()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.session_id: Optional[str] = None
        self.is_connected = False
        
        # 时间戳记录
        self.connect_start_time: Optional[float] = None
        self.connect_end_time: Optional[float] = None
        self.send_time: Optional[float] = None
        self.send_end_time: Optional[float] = None  # 发送语音结束的时间（发送完所有音频帧后）
        self.stt_response_time: Optional[float] = None
        self.llm_response_time: Optional[float] = None
        self.tts_start_time: Optional[float] = None
        self.tts_second_sentence_time: Optional[float] = None  # 第二句TTS回复开始的时间（跳过第一句）
        self.tts_stop_time: Optional[float] = None
        self.tts_sentence_count: int = 0  # TTS句子计数器
        
        # 消息统计
        self.sent_messages = 0
        self.received_messages = 0
        self.total_sent_bytes = 0
        self.total_received_bytes = 0
        
        # 回调函数
        self.on_message_received: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        
        # 响应标志
        self.has_stt = False
        self.has_llm = False
        self.has_tts_start = False
        self.has_tts_stop = False
        self.was_connected = False  # 记录是否曾经成功连接过（用于统计）
        self.auth_received = False  # 是否收到 auth 消息
        self.auth_failed = False  # 是否鉴权失败
        self.stt_empty = False  # STT识别结果是否为空（如果为空，禁止再发送任何消息）
        
        # 响应文本缓冲区
        self.llm_text_buffer = []  # LLM返回的文本内容
    
    async def connect(self) -> bool:
        """建立 WebSocket 连接"""
        self.connect_start_time = get_timestamp()
        
        try:
            url = Config.get_websocket_url(self.device_sn)
            headers = Config.get_headers(self.device_sn)
            
            # 打印鉴权请求信息
            self.logger.info(f"Connection #{self.connection_id}: ========== AUTH REQUEST ==========")
            self.logger.info(f"Connection #{self.connection_id}: Request URL: {url}")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: Request Headers:")
            for key, value in headers.items():
                self.logger.info(f"Connection #{self.connection_id}:   {key}: {value}")
            self.logger.info(f"Connection #{self.connection_id}: ==================================")
            
            self.logger.debug(f"Connection #{self.connection_id}: Connecting to {url}")
            
            # websockets 库传递 HTTP 头的方式
            # 格式：列表，每个元素是 (key, value) 元组
            additional_headers = []
            for key, value in headers.items():
                additional_headers.append((key, value))
            
            # 构建连接参数
            # websockets >= 10.0 使用 additional_headers
            # websockets < 10.0 可能不支持自定义头，需要检查库版本
            connect_kwargs = {
                "ping_interval": None,  # 禁用自动 ping
                "ping_timeout": None,
            }
            
            # 添加 HTTP 头
            # websockets >= 10.0 使用 additional_headers 参数
            if additional_headers:
                connect_kwargs["additional_headers"] = additional_headers
            
            # 尝试连接，如果 additional_headers 参数不被支持，则重试不带头
            try:
                self.websocket = await asyncio.wait_for(
                    websockets.connect(url, **connect_kwargs),
                    timeout=Config.CONNECT_TIMEOUT / 1000.0
                )
            except (TypeError, ValueError) as e:
                # 如果参数不被支持，尝试不使用 headers
                error_msg = str(e)
                if "additional_headers" in error_msg or "extra_headers" in error_msg or "unexpected keyword" in error_msg:
                    self.logger.warning(f"Connection #{self.connection_id}: Headers parameter not supported by websockets library, connecting without headers")
                    connect_kwargs.pop("additional_headers", None)
                    self.websocket = await asyncio.wait_for(
                        websockets.connect(url, **connect_kwargs),
                        timeout=Config.CONNECT_TIMEOUT / 1000.0
                    )
                else:
                    raise
            
            self.connect_end_time = get_timestamp()
            self.is_connected = True
            self.was_connected = True  # 标记为曾经成功连接
            
            connect_duration = self.connect_end_time - self.connect_start_time
            self.logger.connection(
                self.connection_id,
                "success",
                connect_duration,
                url
            )
            
            # 启动消息接收任务
            asyncio.create_task(self._receive_messages())
            
            return True
            
        except asyncio.TimeoutError:
            self.connect_end_time = get_timestamp()
            connect_duration = self.connect_end_time - self.connect_start_time
            self.logger.connection(
                self.connection_id,
                "timeout",
                connect_duration
            )
            if self.on_error:
                self.on_error("Connection timeout")
            return False
            
        except Exception as e:
            self.connect_end_time = get_timestamp()
            connect_duration = self.connect_end_time - self.connect_start_time
            self.logger.connection(
                self.connection_id,
                "failed",
                connect_duration
            )
            self.logger.error_log(self.connection_id, "ConnectionError", str(e))
            if self.on_error:
                self.on_error(f"Connection failed: {str(e)}")
            return False
    
    async def _receive_messages(self):
        """接收消息的异步任务"""
        self.logger.debug(f"Connection #{self.connection_id}: Receive task started")
        try:
            async for message in self.websocket:
                self.received_messages += 1
                self.logger.debug(f"Connection #{self.connection_id}: Received message #{self.received_messages}")
                
                if isinstance(message, bytes):
                    # 二进制消息（音频数据）
                    self.total_received_bytes += len(message)
                    # 只记录音频接收摘要（避免日志过多）
                    self.logger.debug(
                        f"Connection #{self.connection_id}: Received audio | "
                        f"Size: {len(message)} bytes"
                    )
                else:
                    # 文本消息（JSON）
                    self.total_received_bytes += len(message.encode('utf-8'))
                    
                    # 解析 JSON 消息
                    data = parse_json_message(message)
                    if data:
                        msg_type = data.get("type", "unknown")
                        await self._handle_json_message(data)
                    else:
                        self.logger.warning(f"Connection #{self.connection_id}: Failed to parse JSON message")
                
                if self.on_message_received:
                    self.on_message_received(message)
                    
        except ConnectionClosed:
            self.is_connected = False
            self.logger.warning(
                f"Connection #{self.connection_id}: Connection closed by server/network, "
                f"received {self.received_messages} messages total"
            )
            if self.on_error:
                self.on_error("Connection closed")
        except Exception as e:
            self.is_connected = False
            self.logger.error_log(self.connection_id, "ReceiveError", str(e))
            self.logger.warning(
                f"Connection #{self.connection_id}: Receive task exception, "
                f"received {self.received_messages} messages before error"
            )
            if self.on_error:
                self.on_error(f"Receive error: {str(e)}")
        finally:
            self.logger.debug(f"Connection #{self.connection_id}: Receive task ended")
    
    async def _handle_json_message(self, data: Dict[str, Any]):
        """处理接收到的 JSON 消息"""
        msg_type = data.get("type", "unknown")
        current_time = get_timestamp()
        
        # 诊断日志：记录每个消息的接收
        stt_time_str = f"{self.stt_response_time:.2f}ms" if self.stt_response_time else "None"
        llm_time_str = f"{self.llm_response_time:.2f}ms" if self.llm_response_time else "None"
        tts_start_time_str = f"{self.tts_start_time:.2f}ms" if self.tts_start_time else "None"
        self.logger.debug(
            f"Connection #{self.connection_id}: [DIAGNOSTIC] Received message | "
            f"Type: {msg_type} | "
            f"Time: {current_time:.2f}ms | "
            f"Has_STT: {self.has_stt} | "
            f"Has_LLM: {self.has_llm} | "
            f"Has_TTS_Start: {self.has_tts_start} | "
            f"Has_TTS_Stop: {self.has_tts_stop} | "
            f"STT_Time: {stt_time_str} | "
            f"LLM_Time: {llm_time_str} | "
            f"TTS_Start_Time: {tts_start_time_str}"
        )
        
        # 提取 session_id - 尝试多种可能的位置
        session_id_found = False
        
        # 1. 尝试从根级别获取
        if "session_id" in data:
            self.session_id = data["session_id"]
            session_id_found = True
        
        # 2. 尝试从 data.data 获取
        if not session_id_found and "data" in data:
            data_obj = data["data"]
            if isinstance(data_obj, dict) and "session_id" in data_obj:
                self.session_id = data_obj["session_id"]
                session_id_found = True
        
        if msg_type == "auth":
            # 认证响应
            self.auth_received = True
            code = data.get("code", 0)
            msg = data.get("msg", "")
            
            # 打印鉴权响应信息
            import json
            self.logger.info(f"Connection #{self.connection_id}: ========== AUTH RESPONSE ==========")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: Response Code: {code}")
            self.logger.info(f"Connection #{self.connection_id}: Response Message: {msg}")
            self.logger.info(f"Connection #{self.connection_id}: Full Response Data:")
            self.logger.info(f"Connection #{self.connection_id}: {json.dumps(data, ensure_ascii=False, indent=2)}")
            self.logger.info(f"Connection #{self.connection_id}: Session ID: {self.session_id}")
            self.logger.info(f"Connection #{self.connection_id}: ====================================")
            
            if code == -1 or msg == "auth_failed":
                # 鉴权失败
                self.auth_failed = True
                self.logger.error(
                    f"Connection #{self.connection_id}: ❌ Auth FAILED | "
                    f"Code: {code}, Message: {msg}, Device SN: {self.device_sn}"
                )
            elif code == 0 or code == 1 or msg == "auth_success":
                # 鉴权成功
                self.logger.info(
                    f"Connection #{self.connection_id}: ✅ Auth SUCCESS | "
                    f"Code: {code}, Message: {msg}, Session ID: {self.session_id}"
                )
            
        elif msg_type == "stt":
            # STT 响应 - 显示识别的文本内容
            text = data.get("text", "")
            # 保存STT识别结果
            self.stt_text = text
            
            # 记录STT识别结果是否为空（用于统计）
            if not text or text.strip() == "":
                self.stt_empty = True
            
            # 打印STT响应的详细信息
            import json as json_module
            self.logger.info(f"Connection #{self.connection_id}: ========== STT RESPONSE ==========")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: Full Response Data:")
            self.logger.info(f"Connection #{self.connection_id}: {json_module.dumps(data, ensure_ascii=False, indent=2)}")
            
            if not self.has_stt and self.send_time:
                self.stt_response_time = current_time
                self.has_stt = True
                stt_duration = self.stt_response_time - self.send_time
                self.logger.info(f"Connection #{self.connection_id}: Response Time: {stt_duration:.2f}ms (from send_start)")
                self.logger.info(f"Connection #{self.connection_id}: Recognized Text: {text}")
            else:
                # 如果已经记录过，也显示文本内容
                self.logger.info(f"Connection #{self.connection_id}: Update | Recognized Text: {text}")
            
            self.logger.info(f"Connection #{self.connection_id}: =================================")
            
            # 触发STT回调，用于实时更新
            if hasattr(self, '_tts_sentence_callback') and self._tts_sentence_callback:
                # 使用STT回调来更新，传入空字符串作为llm_text
                self._tts_sentence_callback("", text)
            
        elif msg_type == "llm":
            # LLM 响应 - 显示情感和文本内容
            emotion = data.get("emotion", "")
            text = data.get("text", "")
            
            # 保存LLM返回的文本内容
            if text and text.strip():
                if not hasattr(self, 'llm_text_buffer'):
                    self.llm_text_buffer = []
                self.llm_text_buffer.append(text.strip())
            
            # 打印LLM响应的详细信息
            import json as json_module
            self.logger.info(f"Connection #{self.connection_id}: ========== LLM RESPONSE ==========")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: Full Response Data:")
            self.logger.info(f"Connection #{self.connection_id}: {json_module.dumps(data, ensure_ascii=False, indent=2)}")
            
            if not self.has_llm:
                self.llm_response_time = current_time
                self.has_llm = True
                llm_duration = ""
                if self.stt_response_time:
                    llm_duration = f" | Duration: {self.llm_response_time - self.stt_response_time:.2f}ms"
                self.logger.info(f"Connection #{self.connection_id}: Response Time{llm_duration}")
                self.logger.info(f"Connection #{self.connection_id}: Emotion: {emotion}")
                self.logger.info(f"Connection #{self.connection_id}: Text: {text}")
            else:
                self.logger.info(f"Connection #{self.connection_id}: Update | Emotion: {emotion} | Text: {text}")
            
            self.logger.info(f"Connection #{self.connection_id}: =================================")
            
        elif msg_type == "tts":
            # TTS 响应 - 显示状态和文本内容（完全按照项目代码的处理逻辑）
            state = data.get("state", "")
            text = data.get("text", "")
            
            # 打印TTS响应的详细信息
            import json as json_module
            self.logger.info(f"Connection #{self.connection_id}: ========== TTS RESPONSE ==========")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: State: {state}")
            self.logger.info(f"Connection #{self.connection_id}: Full Response Data:")
            self.logger.info(f"Connection #{self.connection_id}: {json_module.dumps(data, ensure_ascii=False, indent=2)}")
            
            # 如果服务器没有发送单独的LLM消息，TTS的sentence_start中的text就是LLM返回的内容
            # 将TTS的文本内容也保存到llm_text_buffer中
            if state == "sentence_start" and text and text.strip():
                # 确保llm_text_buffer已初始化（在__init__中已初始化，这里作为双重保险）
                if not hasattr(self, 'llm_text_buffer'):
                    self.llm_text_buffer = []
                
                text_stripped = text.strip()
                # 避免重复添加相同的文本
                if not self.llm_text_buffer or self.llm_text_buffer[-1] != text_stripped:
                    self.llm_text_buffer.append(text_stripped)
                
                # 如果这是第一个LLM响应，设置has_llm标志（用于快速进入下一个问题）
                if not self.has_llm:
                    self.has_llm = True
                    self.llm_response_time = current_time
                
                # 触发TTS句子回调，用于实时更新
                if hasattr(self, '_tts_sentence_callback') and self._tts_sentence_callback:
                    self._tts_sentence_callback(text_stripped, getattr(self, 'stt_text', ''))
            
            if state == "start" and not self.has_tts_start:
                self.tts_start_time = current_time
                self.has_tts_start = True
                tts_start_duration = ""
                if self.llm_response_time:
                    tts_start_duration = f" | Duration: {self.tts_start_time - self.llm_response_time:.2f}ms"
                elif self.stt_response_time:
                    tts_start_duration = f" | Duration from STT: {self.tts_start_time - self.stt_response_time:.2f}ms"
                self.logger.info(f"Connection #{self.connection_id}: TTS Start Time{tts_start_duration}")
                # 诊断日志：检查是否有LLM响应
                if not self.has_llm:
                    self.logger.warning(
                        f"Connection #{self.connection_id}: [DIAGNOSTIC] TTS start received but no LLM response yet! "
                        f"STT_Time: {self.stt_response_time:.2f}ms" if self.stt_response_time else "STT_Time: None"
                    )
            elif state == "stop" and not self.has_tts_stop:
                self.tts_stop_time = current_time
                self.has_tts_stop = True
                tts_duration = ""
                if self.tts_start_time:
                    tts_duration = f" | Duration: {self.tts_stop_time - self.tts_start_time:.2f}ms"
                self.logger.info(f"Connection #{self.connection_id}: TTS Stop Time{tts_duration}")
            elif state == "sentence_start":
                # sentence_start 状态包含要显示的文本内容
                # 如果还没有记录tts_start_time，则用sentence_start的时间作为TTS开始时间
                # 因为这是用户真正听到回复的开始
                if not self.tts_start_time:
                    self.tts_start_time = current_time
                    self.has_tts_start = True
                
                # 记录第二句TTS回复开始的时间（跳过第一句"好嘞，请稍等，正在处理中"）
                self.tts_sentence_count += 1
                if self.tts_sentence_count == 2 and not self.tts_second_sentence_time:
                    self.tts_second_sentence_time = current_time
                    self.logger.debug(
                        f"Connection #{self.connection_id}: Second TTS sentence started at {current_time:.2f}ms"
                    )
                
                self.logger.info(f"Connection #{self.connection_id}: TTS Sentence Start | Text: {text}")
                # 诊断日志：记录sentence_start的详细信息
                self.logger.info(
                    f"Connection #{self.connection_id}: [DIAGNOSTIC] TTS sentence_start | "
                    f"Sentence #{self.tts_sentence_count} | "
                    f"Has_LLM: {self.has_llm} | "
                    f"LLM_Time: {self.llm_response_time:.2f}ms" if self.llm_response_time else "LLM_Time: None"
                )
            elif state == "sentence_end":
                self.logger.info(f"Connection #{self.connection_id}: TTS Sentence End")
            else:
                # 其他 TTS 状态
                self.logger.info(f"Connection #{self.connection_id}: TTS Update | State: {state}" + (f" | Text: {text}" if text else ""))
            
            self.logger.info(f"Connection #{self.connection_id}: =================================")
        
        elif msg_type == "hello":
            # 服务器 hello 消息（项目代码中有 ParseServerHello，但通常不等待）
            self.logger.debug(f"Connection #{self.connection_id}: Received hello message")
        
        elif msg_type == "abort":
            # 服务器主动打断
            self.logger.info(f"Connection #{self.connection_id}: Received abort message from server")
        
        elif msg_type == "interrupt":
            # 服务器主动中断
            self.logger.info(f"Connection #{self.connection_id}: Received interrupt message from server")
        
        elif msg_type == "iot":
            # IoT 控制消息
            commands = data.get("commands", [])
            self.logger.info(
                f"Connection #{self.connection_id}: Received IoT message | "
                f"Commands count: {len(commands) if isinstance(commands, list) else 0}"
            )
        
        elif msg_type == "actions":
            # 服务器下发的动作规则
            self.logger.info(f"Connection #{self.connection_id}: Received actions message from server")
        
        elif msg_type == "emoji":
            # 表情消息
            emotion = data.get("emotion", "")
            self.logger.info(
                f"Connection #{self.connection_id}: Received emoji message | "
                f"Emotion: {emotion}"
            )
        
        else:
            # 其他未知消息类型
            self.logger.debug(
                f"Connection #{self.connection_id}: Received unknown message type: {msg_type}"
            )
    
    async def send_text(self, message: str) -> bool:
        """发送文本消息"""
        if not self.is_connected or not self.websocket:
            self.logger.error_log(self.connection_id, "SendError", "Not connected")
            return False
        
        try:
            message_bytes = message.encode('utf-8')
            await self.websocket.send(message)
            
            self.sent_messages += 1
            self.total_sent_bytes += len(message_bytes)
            
            # 注意：send_time 应该在 send_user_message 中记录（开始发送音频时）
            # 这里不再自动记录，避免记录 start_listen 的发送时间
            # send_time 现在只在开始发送音频数据时记录
            
            # 只记录关键消息类型，避免日志过多
            try:
                import json
                msg_data = json.loads(message)
                msg_type = msg_data.get("type", "unknown")
                if msg_type in ["start_listen", "stop_listen"]:
                    self.logger.debug(
                        f"Connection #{self.connection_id}: Sent {msg_type} | "
                        f"Size: {len(message_bytes)} bytes"
                    )
            except:
                pass  # 如果不是 JSON，忽略
            
            return True
            
        except Exception as e:
            self.logger.error_log(self.connection_id, "SendError", str(e))
            if self.on_error:
                self.on_error(f"Send error: {str(e)}")
            return False
    
    async def send_start_listen(self, mode: str = None) -> bool:
        """发送 start_listen 消息（启动音频监听）"""
        # 如果鉴权失败，不允许发送数据
        if self.auth_failed:
            self.logger.error(
                f"Connection #{self.connection_id}: Cannot send start_listen - Auth failed"
            )
            return False
        """
        发送 start_listen 消息（启动音频监听）
        
        完全按照项目代码的格式：
        {
          "session_id": "...",
          "type": "start_listen",
          "data": {
            "format": "opus",
            "tts_format": "opus",
            "playTag": 1,
            "state": "asr",
            "mode": "realtime|auto|manual"
          }
        }
        """
        if mode is None:
            mode = Config.LISTENING_MODE
        
        # 生产环境模式：根据 mode 决定 state
        # realtime 模式使用 detect（服务端VAD），其他使用 asr
        if mode == "realtime":
            state_value = "detect"
        else:
            state_value = "asr"
        
        # 完全按照硬件代码 main/protocols/protocol.cc 的格式
        # IoT设备实际发送：state="asr", mode="auto"/"manual"/"realtime"，不包含vad_side参数
        # 
        # 服务端逻辑问题：
        # - 当 state=="asr" 时，vad_side 不会被设置（保持undefined）
        # - 当 mode=="auto" 时，is_vad_chat=true
        # - iat_speak.js 会误判为需要ASR worker，导致音频被丢弃
        #
        # 解决方案：使用 mode=="manual"，这样 is_vad_chat=false，不会走ASR路径
        # 或者：如果必须使用 mode=="auto"，需要服务端修复bug（在state=="asr"时也读取vad_side）
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "start_listen",
            "data": {
                "format": "opus",
                "tts_format": "opus",
                "playTag": 1,
                "state": state_value,
                "mode": mode
                # 注意：IoT设备不发送vad_side参数，测试脚本也不发送
                # 如果mode=="auto"，服务端有bug会导致音频被丢弃（需要服务端修复）
            }
        }
        
        message_str = json.dumps(message, ensure_ascii=False)
        
        # 打印发送start_listen的详细信息
        import json as json_module
        self.logger.info(f"Connection #{self.connection_id}: ========== SEND START_LISTEN ==========")
        self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
        self.logger.info(f"Connection #{self.connection_id}: WebSocket URL: {Config.get_websocket_url(self.device_sn)}")
        self.logger.info(f"Connection #{self.connection_id}: Session ID: {self.session_id}")
        self.logger.info(f"Connection #{self.connection_id}: Message Content:")
        self.logger.info(f"Connection #{self.connection_id}: {json_module.dumps(message, ensure_ascii=False, indent=2)}")
        self.logger.info(f"Connection #{self.connection_id}: Message Size: {len(message_str)} bytes")
        self.logger.info(f"Connection #{self.connection_id}: =======================================")
        
        self.logger.debug(f"Connection #{self.connection_id}: Sending start_listen with mode={mode}")
        return await self.send_text(message_str)
    
    async def send_stop_listen(self) -> bool:
        """
        发送 stop_listen 消息（停止音频监听）
        
        完全按照项目代码的格式：
        {"session_id":"...","type":"stop_listen","state":"stop"}
        """
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "stop_listen",
            "state": "stop"
        }
        
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending stop_listen")
        return await self.send_text(message_str)
    
    async def send_cancel_listen(self) -> bool:
        """
        发送 cancel_listen 消息（取消音频监听）
        
        完全按照项目代码的格式：
        {"session_id":"...","type":"cancel_listen"}
        """
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "cancel_listen"
        }
        
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending cancel_listen")
        return await self.send_text(message_str)

    async def send_enter_vad(self) -> bool:
        """发送 enter_vad 消息（进入持续对话/保持监听）

        与设备代码一致：`Protocol::SendEnterVad()`
        {"session_id":"...","type":"enter_vad","data":{"format":"opus","tts_format":"opus","playTag":1,"mode":"realtime"}}
        """
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "enter_vad",
            "data": {
                "format": "opus",
                "tts_format": "opus",
                "playTag": 1,
                "mode": "realtime"
            }
        }
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending enter_vad")
        return await self.send_text(message_str)

    async def send_exit_vad(self) -> bool:
        """发送 exit_detect 消息（退出持续对话/保持监听）

        与设备 `Application::ExitVad()` 一致：发送 type=exit_detect
        """
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "exit_detect"
        }
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending exit_detect")
        return await self.send_text(message_str)

    async def send_change_role(self, role_type: int = 0) -> bool:
        """发送 change_role（切换角色/系统类型）

        参考设备 `Application::ChangeRole`：{"type":"change_role","type":role,"system_type":2}
        """
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "change_role",
            "type": role_type,
            "system_type": 2
        }
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending change_role type={role_type}")
        return await self.send_text(message_str)

    async def send_play_welcome_voice(self) -> bool:
        """发送 play_voice（播放欢迎语等系统音）"""
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "play_voice",
            "system_type": 2
        }
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending play_voice")
        return await self.send_text(message_str)

    async def send_heartbeat(self,
                             status: int = 1,
                             wifi: int = 80,
                             battery: int = 80,
                             charging: int = 0,
                             volume: int = 50,
                             network_type: int = 0,
                             light: int = 20) -> bool:
        """发送 heartbeat 心跳（模拟设备定期上报）"""
        message = {
            "session_id": self.session_id if self.session_id else "",
            "type": "heartbeat",
            "status": status,
            "wifi": wifi,
            "battery": battery,
            "charging": charging,
            "volume": volume,
            "network_type": network_type,
            "light": light
        }
        message_str = json.dumps(message, ensure_ascii=False)
        self.logger.debug(f"Connection #{self.connection_id}: Sending heartbeat")
        return await self.send_text(message_str)
    
    async def send_audio_data(self, audio_data: bytes) -> bool:
        """发送 Opus 编码的音频数据（二进制，单个数据包）"""
        # 如果鉴权失败，不允许发送数据
        if self.auth_failed:
            self.logger.error(
                f"Connection #{self.connection_id}: Cannot send audio - Auth failed"
            )
            return False
        if not self.is_connected or not self.websocket:
            self.logger.error_log(self.connection_id, "SendError", "Not connected")
            return False
        
        try:
            # 发送二进制数据（Opus 数据包）
            await self.websocket.send(audio_data)
            
            self.sent_messages += 1
            self.total_sent_bytes += len(audio_data)
            
            self.logger.message(
                self.connection_id,
                "audio",
                "send",
                len(audio_data)
            )
            
            return True
            
        except Exception as e:
            self.logger.error_log(self.connection_id, "SendError", str(e))
            if self.on_error:
                self.on_error(f"Send audio error: {str(e)}")
            return False
    
    async def send_audio_frames(self, audio_frames: List[bytes], frame_interval_ms: float = 0.0) -> bool:
        """
        批量连续发送 Opus 音频数据（完全模拟设备发送流程）
        
        完全按照项目代码 MainLoop 的行为：
        - 音频数据通过 websocket_->Send(data.data(), data.size(), true) 发送（二进制）
        - MainLoop 中批量连续发送队列中的所有包，没有间隔
        - 代码：for (auto& opus : packets) { protocol_->SendAudio(std::move(opus)); }
        - 发送是异步的，不等待响应
        
        Args:
            audio_frames: Opus 帧列表，每个帧是一个独立的 Opus 数据包（60ms）
            frame_interval_ms: 帧间隔（毫秒），默认 0ms（批量连续发送，模拟 MainLoop 行为）
        """
        if not self.is_connected or not self.websocket:
            self.logger.error_log(self.connection_id, "SendError", "Not connected")
            return False
        
        if not audio_frames:
            self.logger.warning(f"Connection #{self.connection_id}: No audio frames to send")
            return False
        
        try:
            total_size = 0
            frame_count = len(audio_frames)
            
            # 记录发送开始
            total_bytes = sum(len(f) for f in audio_frames)
            self.logger.info(f"Connection #{self.connection_id}: ========== SEND AUDIO DATA ==========")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: WebSocket URL: {Config.get_websocket_url(self.device_sn)}")
            self.logger.info(f"Connection #{self.connection_id}: Session ID: {self.session_id}")
            self.logger.info(f"Connection #{self.connection_id}: Frame Count: {frame_count}")
            self.logger.info(f"Connection #{self.connection_id}: Total Size: {total_bytes} bytes")
            self.logger.info(f"Connection #{self.connection_id}: Average Frame Size: {total_bytes // frame_count if frame_count > 0 else 0} bytes")
            self.logger.info(f"Connection #{self.connection_id}: Send Mode: Batch (no interval)")
            self.logger.info(f"Connection #{self.connection_id}: =====================================")
            
            self.logger.debug(
                f"Connection #{self.connection_id}: Starting to send {frame_count} audio frames "
                f"(total {total_bytes} bytes) - batch mode (no interval)"
            )
            
            # 批量连续发送所有帧（模拟 MainLoop 的行为）
            # 项目代码：for (auto& opus : packets) { protocol_->SendAudio(std::move(opus)); }
            for frame in audio_frames:
                if not self.is_connected:
                    self.logger.warning(f"Connection #{self.connection_id}: Connection lost during audio sending")
                    break
                
                # 发送单个 Opus 帧（二进制数据包）
                # 项目代码：websocket_->Send(data.data(), data.size(), true) - 二进制发送
                # Python websockets: await websocket.send(frame) - frame 是 bytes，自动识别为二进制
                await self.websocket.send(frame)
                
                self.sent_messages += 1
                self.total_sent_bytes += len(frame)
                total_size += len(frame)
                
                # 注意：项目代码在 MainLoop 中是批量连续发送，没有间隔
                # 所以这里也不应该有任何延迟
                # 只有在需要模拟真实采集节奏时才使用间隔（但当前应该是批量发送）
                if frame_interval_ms > 0 and frame != audio_frames[-1]:  # 最后一帧不需要等待
                    await asyncio.sleep(frame_interval_ms / 1000.0)
            
            # 发送完成
            self.logger.info(f"Connection #{self.connection_id}: ========== AUDIO SEND COMPLETE ==========")
            self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
            self.logger.info(f"Connection #{self.connection_id}: Frames Sent: {frame_count}")
            self.logger.info(f"Connection #{self.connection_id}: Total Bytes Sent: {total_size} bytes")
            self.logger.info(f"Connection #{self.connection_id}: Messages Sent (cumulative): {self.messages_sent}")
            self.logger.info(f"Connection #{self.connection_id}: Total Bytes Sent (cumulative): {self.bytes_sent} bytes")
            self.logger.info(f"Connection #{self.connection_id}: =========================================")
            
            self.logger.debug(
                f"Connection #{self.connection_id}: Sent {frame_count} audio frames, "
                f"total {total_size} bytes (batch mode, no interval)"
            )
            
            return True
            
        except Exception as e:
            self.logger.error_log(self.connection_id, "SendError", str(e))
            if self.on_error:
                self.on_error(f"Send audio frames error: {str(e)}")
            return False
    
    async def send_user_message(self, text: str, audio_frames: Optional[List[bytes]] = None) -> bool:
        """
        发送用户消息（完全模拟设备发送流程）
        
        流程（完全按照项目代码）：
        1. 发送 start_listen 消息（文本 JSON）
        2. 逐帧发送 Opus 音频数据（二进制）
           关键：设备AudioLoop每10ms调用一次OnAudioInput，每次可能读取一个包
           但MainLoop中批量连续发送队列中的所有包，没有间隔
           为了更接近真实情况，我们分批发送（每批几个包，模拟队列积累）
        3. 根据监听模式决定是否发送 stop_listen：
           - auto: 可选发送（服务器可能自动检测VAD）
           - manual: 必须发送
           - realtime: 不发送（持续监听）
        """
        # 1. 先发送 start_listen 消息
        if not await self.send_start_listen():
            return False
        
        # 等待一小段时间，确保服务器准备好接收音频
        # 项目代码中，发送 start_listen 后立即进入监听状态并开始采集音频
        # 但为了确保服务器处理完 start_listen 消息，我们等待一小段时间
        # 注意：服务器端IAT服务启动有500ms延迟（setTimeout），所以需要等待更长时间
        await asyncio.sleep(0.6)  # 增加到 600ms，确保IAT服务已启动（500ms延迟 + 100ms缓冲）
        
        # 2. 如果提供了音频帧，发送音频数据
        # 关键：在开始发送音频数据时记录 send_time（用于计算响应时间）
        # 而不是在 send_start_listen 时记录，因为 start_listen 只是准备阶段
        if audio_frames:
            self.logger.info(f"Connection #{self.connection_id}: Preparing to send {len(audio_frames)} audio frames")
            # 在发送第一帧音频之前记录 send_time
            if self.send_time is None:
                from utils import get_timestamp
                self.send_time = get_timestamp()
                self.logger.debug(f"Connection #{self.connection_id}: Recorded send_time for audio data")
            # 关键发现（通过查看ws_server代码）：
            # 1. 服务器每个WebSocket消息的二进制数据会被当作一个Opus包解码
            # 2. decoder.decode(binaryData) 只能解码单个Opus包
            # 3. 设备每次 SendAudio() 对应一个WebSocket消息，每个消息是一个独立的Opus包
            # 4. 所以需要将连续的Opus数据分割为多个独立的包，每个包作为一个独立的WebSocket消息发送
            
            # 根据配置选择发送模式
            if Config.AUDIO_SEND_MODE == "continuous":
                # 持续输入模式：按照实际时间间隔发送（模拟真实采集节奏）
                # IoT设备实际采集：
                #   - AudioLoop每10ms调用一次OnAudioInput
                #   - 硬件编码：每30ms读取一次Opus数据
                #   - 软件编码：每60ms生成一个Opus包
                # 这里按照配置的间隔发送，模拟持续采集
                interval_sec = Config.AUDIO_SEND_INTERVAL_MS / 1000.0
                self.logger.debug(
                    f"Connection #{self.connection_id}: Sending {len(audio_frames)} audio frames "
                    f"in continuous mode (interval: {Config.AUDIO_SEND_INTERVAL_MS}ms)"
                )
                
                for i, frame in enumerate(audio_frames):
                    if not self.is_connected:
                        self.logger.warning(f"Connection #{self.connection_id}: Connection lost during audio sending")
                        break
                    
                    # 发送单个 Opus 包（二进制数据包）
                    await self.websocket.send(frame)
                    
                    self.sent_messages += 1
                    self.total_sent_bytes += len(frame)
                    
                    # 如果不是最后一帧，等待间隔时间（模拟持续采集）
                    if i < len(audio_frames) - 1:
                        await asyncio.sleep(interval_sec)
            else:
                # 批量发送模式：连续发送所有帧，没有间隔（模拟 MainLoop 批量发送）
                # 项目代码：for (auto& opus : packets) { protocol_->SendAudio(std::move(opus)); }
                # 每个 SendAudio() 调用对应一个 WebSocket 二进制消息
                frame_count = len(audio_frames)
                total_bytes = sum(len(f) for f in audio_frames)
                self.logger.info(f"Connection #{self.connection_id}: ========== SEND AUDIO DATA ==========")
                self.logger.info(f"Connection #{self.connection_id}: Device SN: {self.device_sn}")
                self.logger.info(f"Connection #{self.connection_id}: Frame Count: {frame_count}")
                self.logger.info(f"Connection #{self.connection_id}: Total Size: {total_bytes} bytes")
                self.logger.info(f"Connection #{self.connection_id}: Send Mode: Batch (no interval)")
                self.logger.info(f"Connection #{self.connection_id}: =====================================")
                
                sent_count = 0
                sent_bytes = 0
                for frame in audio_frames:
                    if not self.is_connected:
                        self.logger.warning(f"Connection #{self.connection_id}: Connection lost during audio sending")
                        break
                    
                    # 发送单个 Opus 包（二进制数据包）
                    # 项目代码：websocket_->Send(data.data(), data.size(), true) - 二进制发送
                    # Python websockets: await websocket.send(frame) - frame 是 bytes，自动识别为二进制
                    # 每个 WebSocket 消息对应一个独立的 Opus 包
                    await self.websocket.send(frame)
                    
                    self.sent_messages += 1
                    self.total_sent_bytes += len(frame)
                    sent_count += 1
                    sent_bytes += len(frame)
                
                # 记录发送完成
                self.logger.info(f"Connection #{self.connection_id}: ========== AUDIO SEND COMPLETE ==========")
                self.logger.info(f"Connection #{self.connection_id}: Frames Sent: {sent_count}/{frame_count}")
                self.logger.info(f"Connection #{self.connection_id}: Bytes Sent: {sent_bytes} bytes")
                self.logger.info(f"Connection #{self.connection_id}: =========================================")
            
            # 记录发送完成
            # 记录发送语音结束的时间（发送完所有音频帧后）
            from utils import get_timestamp
            self.send_end_time = get_timestamp()
            self.logger.debug(
                f"Connection #{self.connection_id}: Finished sending {len(audio_frames)} audio frames, "
                f"total {self.total_sent_bytes} bytes, send_time={self.send_time}, send_end_time={self.send_end_time}"
            )
            
            # 3. 根据监听模式和配置决定是否发送 stop_listen
            should_send_stop = Config.SEND_STOP_LISTEN
            if Config.LISTENING_MODE == "realtime":
                should_send_stop = False  # realtime 模式不发送 stop_listen
            
            if should_send_stop:
                # 等待一小段时间，确保最后一帧音频数据已发送
                await asyncio.sleep(0.1)
                await self.send_stop_listen()
                # 如果发送了stop_listen，更新send_end_time为stop_listen发送时间
                self.send_end_time = get_timestamp()
            
            return True
        else:
            # 如果没有提供音频数据，只发送文本消息（用于快速测试）
            self.logger.warning(f"Connection #{self.connection_id}: No audio frames provided, only sending start_listen")
            if Config.SEND_STOP_LISTEN and Config.LISTENING_MODE != "realtime":
                await asyncio.sleep(0.1)
                await self.send_stop_listen()
            return True
    
    def _is_websocket_closed(self) -> bool:
        """检查WebSocket连接是否已关闭"""
        if not self.websocket:
            return True
        try:
            # websockets库中，如果连接已关闭，close_code不为None
            return self.websocket.close_code is not None
        except:
            return True
    
    async def close(self):
        """关闭连接"""
        if self.websocket:
            try:
                self.logger.debug(
                    f"Connection #{self.connection_id}: Closing connection, "
                    f"received {self.received_messages} messages, connected: {self.is_connected}"
                )
                await self.websocket.close()
            except Exception as e:
                self.logger.error_log(self.connection_id, "CloseError", str(e))
            finally:
                self.is_connected = False
                self.websocket = None
                self.logger.debug(f"Connection #{self.connection_id}: Connection closed")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取连接指标"""
        metrics = {
            "connection_id": self.connection_id,
            "is_connected": self.is_connected,
            "connect_time": None,
            "connect_status": "unknown",
            "send_time": None,
            "send_end_time": None,
            "stt_latency": None,        # STT服务延迟
            "llm_latency": None,         # LLM服务延迟
            "tts_latency": None,         # TTS服务延迟
            "e2e_response_time": None,   # 端到端响应时间
            "audio_to_tts_delay": None,  # 从发送语音结束到TTS开始的延迟
            "message_size": None,
            "response_size": None,
            "sent_messages": self.sent_messages,
            "received_messages": self.received_messages,
            "total_sent_bytes": self.total_sent_bytes,
            "total_received_bytes": self.total_received_bytes,
            "complete": False,
            "error_type": None,
            "error_message": None
        }
        
        if self.connect_start_time and self.connect_end_time:
            metrics["connect_time"] = self.connect_end_time - self.connect_start_time
            # 判断连接状态：如果曾经成功连接过，或者收到了响应，就认为是成功
            # 不能只看 is_connected，因为连接可能在测试结束后已经关闭
            metrics["connect_status"] = "success" if (self.was_connected or self.has_tts_stop or self.received_messages > 0) else "failed"
        
        # send_time 保存为绝对时间戳（毫秒），用于计算时间差
        # 但在metrics中，我们保存的是相对于连接结束时间的偏移（毫秒），用于统计
        if self.send_time:
            # send_time 是绝对时间戳，计算相对于连接结束时间的偏移
            base_time = self.connect_end_time or self.connect_start_time
            if base_time:
                metrics["send_time"] = self.send_time - base_time
        
        # send_end_time 保存为绝对时间戳（毫秒）
        if self.send_end_time:
            base_time = self.connect_end_time or self.connect_start_time
            if base_time:
                metrics["send_end_time"] = self.send_end_time - base_time
        
        # 所有时间差计算都使用绝对时间戳（毫秒）
        # 调试信息：记录时间戳值
        if self.send_time:
            stt_str = f"{self.stt_response_time:.2f}" if self.stt_response_time else "None"
            llm_str = f"{self.llm_response_time:.2f}" if self.llm_response_time else "None"
            tts_start_str = f"{self.tts_start_time:.2f}" if self.tts_start_time else "None"
            tts_stop_str = f"{self.tts_stop_time:.2f}" if self.tts_stop_time else "None"
            self.logger.debug(
                f"Connection #{self.connection_id}: Time metrics - "
                f"send_time={self.send_time:.2f}, "
                f"stt_time={stt_str}, "
                f"llm_time={llm_str}, "
                f"tts_start={tts_start_str}, "
                f"tts_stop={tts_stop_str}"
            )
        
        # 性能指标设计（专业测试角度）：
        # 1. STT服务延迟：从发送音频到收到STT结果（包含网络传输+STT处理时间）
        if self.stt_response_time and self.send_time:
            metrics["stt_latency"] = self.stt_response_time - self.send_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated stt_latency = {metrics['stt_latency']:.2f}ms")
        
        # 2. LLM服务延迟：从STT完成到LLM响应（LLM处理时间）
        if self.llm_response_time and self.stt_response_time:
            metrics["llm_latency"] = self.llm_response_time - self.stt_response_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated llm_latency = {metrics['llm_latency']:.2f}ms")
        
        # 3. TTS服务延迟：从LLM完成到TTS开始（TTS启动延迟，包含TTS服务启动时间）
        if self.tts_start_time and self.llm_response_time:
            metrics["tts_latency"] = self.tts_start_time - self.llm_response_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated tts_latency = {metrics['tts_latency']:.2f}ms")
        
        # 注意：不记录TTS持续时间，因为这是内容长度决定的，不是性能指标
        
        # 计算从发送语音结束到TTS开始的延迟（这是客户端可以准确测量的指标）
        if self.send_end_time and self.tts_start_time:
            metrics["audio_to_tts_delay"] = self.tts_start_time - self.send_end_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated audio_to_tts_delay = {metrics['audio_to_tts_delay']:.2f}ms")
        
        # 计算从发送语音结束到第二句TTS开始的延迟（跳过第一句"好嘞，请稍等，正在处理中"）
        if self.send_end_time and self.tts_second_sentence_time:
            metrics["audio_to_second_tts_delay"] = self.tts_second_sentence_time - self.send_end_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated audio_to_second_tts_delay = {metrics['audio_to_second_tts_delay']:.2f}ms")
        
        # 记录第二句TTS时间（用于CSV导出）
        if self.tts_second_sentence_time:
            base_time = self.connect_end_time or self.connect_start_time
            if base_time:
                metrics["tts_second_sentence_time"] = self.tts_second_sentence_time - base_time
        
        # 4. 端到端响应时间：从发送音频到TTS结束（完整对话流程的总时间）
        if self.send_time and self.tts_stop_time:
            metrics["e2e_response_time"] = self.tts_stop_time - self.send_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated e2e_response_time = {metrics['e2e_response_time']:.2f}ms")
        elif self.send_time and self.tts_start_time:
            metrics["e2e_response_time"] = self.tts_start_time - self.send_time
            self.logger.debug(f"Connection #{self.connection_id}: Calculated e2e_response_time (from tts_start) = {metrics['e2e_response_time']:.2f}ms")
        
        metrics["message_size"] = self.total_sent_bytes
        metrics["response_size"] = self.total_received_bytes
        
        # 判断是否完成：只要收到 TTS stop 就认为完成
        # 因为有些情况下（如 STT 识别失败），服务器可能跳过 LLM 直接返回 TTS
        metrics["complete"] = (
            self.has_tts_stop or  # 只要有 TTS stop 就认为完成（主要判断）
            (self.has_stt and self.has_tts_start and self.has_tts_stop)  # 或者有完整流程
        )
        
        return metrics

