"""
询问和购买测试脚本：基于test_runner.py的逻辑
按顺序测试100个问题（50个询问 + 50个购买），确保询问响应完成后再进行购买
"""
import os
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from logger import Logger
from config import Config
from websocket_client import WebSocketClient
from audio_encoder import AudioEncoder

# 音频目录
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio", "inquiries")

class InquiryTester:
    """询问测试类（基于test_runner.py的逻辑）"""
    
    def __init__(self):
        self.logger = Logger()
        self.audio_encoder = AudioEncoder()
        self.results: List[Dict[str, Any]] = []
        self.test_start_time = datetime.now()
        
    def parse_inquiries_file(self, file_path: str) -> tuple:
        """解析询问文件，提取所有询问和购买文本"""
        inquiries = []
        purchases = []
        
        if not os.path.exists(file_path):
            self.logger.warning(f"File not found: {file_path}, will use audio files only")
            return inquiries, purchases
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('询问:'):
                text = line.replace('询问:', '').strip()
                inquiries.append(text)
            elif line.startswith('购买:'):
                text = line.replace('购买:', '').strip()
                purchases.append(text)
        
        return inquiries, purchases
    
    def _get_text_for_file(self, filename: str, index: int, prefix: str, 
                          text_map: dict, default_texts: list) -> str:
        """
        根据文件名获取对应的文本内容
        优先从file_list.txt的text_map中获取，否则从default_texts中按索引获取
        """
        # 先尝试从text_map中获取（最准确）
        text = text_map.get(filename)
        if text:
            return text
        
        # 如果text_map中没有，尝试从default_texts中按索引获取
        if index <= len(default_texts):
            return default_texts[index - 1]
        
        # 如果都没有，返回占位符
        return f"{'询问' if prefix == 'inquiry' else '对比' if prefix == 'compare' else '购买'} #{index}"
    
    def _random_select_test_files(self, inquiry_indices: list, compare_indices: list, 
                                   order_indices: list, inquiries_texts: list, 
                                   compares_texts: list, orders_texts: list, 
                                   test_count: int) -> list:
        """
        从所有opus文件中随机选择指定数量的文件进行测试（统一处理，不再区分类型）
        
        Args:
            inquiry_indices: 已废弃，保留以兼容旧代码
            compare_indices: 已废弃，保留以兼容旧代码
            order_indices: 已废弃，保留以兼容旧代码
            inquiries_texts: 文本列表（统一使用）
            compares_texts: 已废弃，保留以兼容旧代码
            orders_texts: 已废弃，保留以兼容旧代码
            test_count: 要选择的测试数量
        
        Returns:
            测试任务列表
        """
        import random
        import re
        
        # 统一使用inquiry_indices（实际是所有audio_文件的索引）
        all_indices = inquiry_indices if inquiry_indices else []
        
        # 如果测试数量大于可用文件总数，只测试所有可用文件
        actual_test_count = min(test_count, len(all_indices))
        
        if actual_test_count == 0:
            return []
        
        # 从所有文件中随机选择指定数量
        selected_indices = random.sample(all_indices, actual_test_count)
        
        # 从file_list.txt读取文本映射（用于准确匹配文本）
        file_list_txt = os.path.join(AUDIO_DIR, "file_list.txt")
        text_map = {}  # {filename: text}
        if os.path.exists(file_list_txt):
            with open(file_list_txt, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line in ["Inquiry Files:", "Compare Files:", "Order Files:"]:
                        continue
                    # 解析格式：001: filename.opus - 文本内容
                    match = re.match(r'(\d+):\s+(\w+_\d+\.opus)\s+-\s+(.+)', line)
                    if match:
                        filename = match.group(2)
                        text = match.group(3)
                        if text:  # 只保存非空文本
                            text_map[filename] = text
        
        # 构建测试任务（统一使用inquiry_file和inquiry_text，保持兼容性）
        all_test_items = []
        for index in selected_indices:
            audio_file = self.get_audio_file(index)
            if audio_file:
                # 根据实际文件名获取文本
                filename = os.path.basename(audio_file)
                text = text_map.get(filename) if filename in text_map else (inquiries_texts[index - 1] if index <= len(inquiries_texts) else f"测试 #{index}")
                all_test_items.append({
                    "index": index,
                    "inquiry_file": audio_file,  # 统一使用inquiry_file字段
                    "inquiry_text": text  # 统一使用inquiry_text字段
                })
        
        # 按index排序
        all_test_items.sort(key=lambda x: x["index"])
        
        return all_test_items
    
    def scan_audio_files(self, prefix: str = None) -> list:
        """
        自动扫描目录中的音频文件（统一使用audio_前缀，不再区分类型）
        
        Args:
            prefix: 已废弃，保留以兼容旧代码，实际不再使用
        
        Returns:
            找到的文件索引列表，按数字顺序排序
        """
        indices = []
        if not os.path.exists(AUDIO_DIR):
            return indices
        
        # 统一扫描audio_前缀的文件（不再区分类型）
        for filename in os.listdir(AUDIO_DIR):
            if filename.startswith("audio_") and filename.endswith(".opus"):
                try:
                    # 提取索引：audio_001.opus -> 1
                    index_str = filename.replace("audio_", "").replace(".opus", "")
                    index = int(index_str)
                    indices.append(index)
                except ValueError:
                    continue
        
        # 排序并返回
        indices.sort()
        return indices
    
    def parse_text_files(self) -> tuple:
        """
        解析文本文件（统一处理，不再区分类型）
        优先从file_list.txt读取文本内容（所有audio_前缀的文件）
        返回 (texts, [], []) 元组（保持兼容性，但只使用第一个元素）
        """
        import re
        texts = []
        
        # 优先从file_list.txt读取文本映射（所有audio_前缀的文件）
        file_list_txt = os.path.join(AUDIO_DIR, "file_list.txt")
        text_map = {}  # {filename: text}
        if os.path.exists(file_list_txt):
            with open(file_list_txt, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line in ["Inquiry Files:", "Compare Files:", "Order Files:"]:
                        continue
                    
                    # 解析格式：001: filename.opus - 文本内容
                    match = re.match(r'(\d+):\s+(\w+_\d+\.opus)\s+-\s+(.+)', line)
                    if match:
                        filename = match.group(2)
                        text = match.group(3)
                        if text:  # 只保存非空文本
                            text_map[filename] = text
        
        # 扫描所有audio_前缀的文件，按索引顺序获取文本
        audio_indices = self.scan_audio_files()
        for idx in sorted(audio_indices):
            filename = f"audio_{idx:03d}.opus"
            text = text_map.get(filename)
            if text:
                texts.append(text)
            else:
                texts.append(f"测试 #{idx}")
        
        # 返回 (texts, [], []) 保持兼容性
        return texts, [], []
    
    def get_audio_file(self, index: int, prefix: str = None) -> Optional[str]:
        """
        获取音频文件路径（Opus格式）
        统一使用audio_前缀，不再区分类型
        
        Args:
            index: 文件索引
            prefix: 已废弃，保留以兼容旧代码，实际不再使用
        """
        # 统一使用audio_前缀
        filename = f"audio_{index:03d}.opus"
        file_path = os.path.join(AUDIO_DIR, filename)
        
        if os.path.exists(file_path):
            return file_path
        
        return None
    
    def load_audio_frames(self, audio_file: str) -> Optional[List[bytes]]:
        """加载Opus文件为帧列表（与test_runner.py的逻辑一致）"""
        try:
            frames = self.audio_encoder._load_audio_file_as_frames(audio_file)
            if frames:
                self.logger.debug(f"Loaded {len(frames)} Opus frames from {os.path.basename(audio_file)}")
            return frames
        except Exception as e:
            self.logger.error(f"Failed to load audio file {audio_file}: {e}")
            return None
    
    async def test_single_audio(self, client: WebSocketClient, audio_file: str, text: str, 
                                test_type: str, index: int) -> Dict[str, Any]:
        """
        测试单个音频文件（完全基于test_runner.py的run_single_connection逻辑）
        
        Args:
            client: WebSocket客户端
            audio_file: 音频文件路径
            text: 对应的文本（用于记录）
            test_type: "inquiry" 或 "purchase"
            index: 测试序号
        """
        result = {
            "index": index,
            "type": test_type,
            "text": text,
            "audio_file": os.path.basename(audio_file),
            "success": False,
            "stt_text": "",
            "llm_text": "",
            "response_text": "",
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Testing [{test_type.upper()}] #{index:03d}: {text[:50]}...")
            self.logger.info(f"Audio file: {os.path.basename(audio_file)}")
            self.logger.info(f"{'='*60}")
            
            # 重置响应状态（为本次测试准备）
            client.stt_text = ""
            client.llm_text_buffer = []
            client.has_tts_stop = False
            client.has_stt = False
            client.has_llm = False
            client.has_tts_start = False
            client.send_time = None
            client.send_end_time = None
            client.tts_stop_time = None  # 重置TTS stop时间
            
            # 加载音频帧（与test_runner.py的逻辑一致）
            self.logger.info(f"Connection #{client.connection_id}: Loading audio file: {audio_file}")
            audio_frames = self.load_audio_frames(audio_file)
            if not audio_frames:
                self.logger.error(f"Connection #{client.connection_id}: Failed to load audio frames from {audio_file}")
                result["error"] = "Failed to load audio frames"
                return result
            self.logger.info(f"Connection #{client.connection_id}: Successfully loaded {len(audio_frames)} audio frames from {audio_file}")
            
            # 记录发送消息前的时间，用于判断后续消息是否属于本次测试
            send_start_time = time.time()
            send_start_time_ms = send_start_time * 1000  # 转换为毫秒时间戳，用于与TTS stop时间戳比较
            
            # 发送消息（完全使用test_runner.py的逻辑：send_user_message）
            # 这与之前成功的测试完全一致
            await client.send_user_message(text, audio_frames)
            
            # 记录发送消息后的时间，用于判断后续消息是否属于本次测试
            send_complete_time = time.time()
            
            # 根据配置选择测试模式
            # "normal": 正常模式 - 等待完整响应（TTS stop）后再进行下一个问题
            # "fast": 急速模式 - 只要大模型开始回复（has_llm + llm_text_buffer）就继续下一个问题
            test_mode = Config.TEST_MODE.lower()
            
            max_wait_time = Config.TTS_TIMEOUT / 1000.0  # 转换为秒
            wait_time = 0
            check_interval = 0.1  # 每 100ms 检查一次
            
            while wait_time < max_wait_time:
                await asyncio.sleep(check_interval)
                wait_time += check_interval
                
                # 检查连接状态
                if not client.is_connected:
                    self.logger.warning(f"Connection #{client.connection_id}: Connection lost during wait")
                    break
                
                # 注意：为了确保每个会话完成，即使是急速模式也等待完整响应（TTS stop）
                # 不再提前退出，必须等待TTS stop才能继续下一个对话
                # if test_mode == "fast":
                #     # 急速模式：只要大模型开始回复就继续下一个问题
                #     # 检查是否收到LLM响应（必须是大模型开始回复，不能仅仅是STT）
                #     # has_llm 标志只在收到LLM消息或TTS的sentence_start时设置，不会因为STT而设置
                #     # llm_text_buffer 也只在LLM相关消息时填充
                #     if client.has_llm:
                #         # 进一步确认：必须有实际的LLM内容（不能仅仅是STT）
                #         has_llm_content = (hasattr(client, 'llm_text_buffer') and 
                #                           client.llm_text_buffer and 
                #                           len(client.llm_text_buffer) > 0)
                #         if has_llm_content:
                #             self.logger.info(f"Connection #{client.connection_id}: LLM response started at {wait_time:.1f}s, proceeding to next question (fast mode)")
                #             break
                
                # 正常模式或急速模式：如果收到完整响应（TTS stop），都可以提前退出
                # 但需要验证TTS stop是否属于本次测试（时间戳在发送消息之后）
                if client.has_tts_stop and client.tts_stop_time is not None:
                    # 检查TTS stop时间是否在发送消息之后（允许2秒误差）
                    # tts_stop_time是毫秒时间戳，send_start_time_ms也是毫秒时间戳
                    if client.tts_stop_time >= send_start_time_ms - 2000:  # 允许2秒误差（2000ms）
                        self.logger.info(f"Connection #{client.connection_id}: Received complete response at {wait_time:.1f}s")
                        break
                    else:
                        # TTS stop是上一个测试的，忽略
                        tts_stop_time_sec = client.tts_stop_time / 1000.0
                        self.logger.debug(f"Connection #{client.connection_id}: TTS stop time ({tts_stop_time_sec:.3f}s) is before send start ({send_start_time:.3f}s), ignoring")
            
            # 等待循环结束后，再给一点时间让异步消息处理完成
            # 为了确保每个会话完成，必须等待完整响应（TTS stop）
            # 验证TTS stop是否属于本次测试
            tts_stop_valid = False
            if client.has_tts_stop and client.tts_stop_time is not None:
                # tts_stop_time是毫秒时间戳，send_start_time_ms也是毫秒时间戳
                if client.tts_stop_time >= send_start_time_ms - 2000:  # 允许2秒误差（2000ms）
                    tts_stop_valid = True
            
            # 如果没有收到有效的TTS stop，继续等待直到收到TTS stop或超时
            if not tts_stop_valid:
                # 额外等待时间：最多等待10秒，确保收到完整响应
                max_additional_wait = 10.0  # 最多额外等待10秒
                additional_wait_time = 0
                check_interval = 0.2  # 每200ms检查一次
                
                # 诊断日志：记录等待开始时的状态
                self.logger.info(
                    f"Connection #{client.connection_id}: [DIAGNOSTIC] Starting additional wait | "
                    f"Has_STT: {client.has_stt} | "
                    f"Has_LLM: {client.has_llm} | "
                    f"Has_TTS_Start: {client.has_tts_start} | "
                    f"Has_TTS_Stop: {client.has_tts_stop} | "
                    f"STT_Text: {getattr(client, 'stt_text', '')[:50]}... | "
                    f"LLM_Text: {' '.join(getattr(client, 'llm_text_buffer', []))[:50]}..."
                )
                
                while additional_wait_time < max_additional_wait:
                    await asyncio.sleep(check_interval)
                    additional_wait_time += check_interval
                    
                    # 检查是否收到有效的TTS stop
                    if client.has_tts_stop and client.tts_stop_time is not None:
                        if client.tts_stop_time >= send_start_time_ms - 2000:
                            self.logger.info(f"Connection #{client.connection_id}: Received TTS stop after additional wait ({additional_wait_time:.1f}s)")
                            tts_stop_valid = True
                            break
                    
                    # 每2秒输出一次诊断信息
                    if int(additional_wait_time * 5) % 10 == 0 and additional_wait_time > 0:
                        self.logger.info(
                            f"Connection #{client.connection_id}: [DIAGNOSTIC] Waiting... ({additional_wait_time:.1f}s) | "
                            f"Has_STT: {client.has_stt} | "
                            f"Has_LLM: {client.has_llm} | "
                            f"Has_TTS_Start: {client.has_tts_start} | "
                            f"Has_TTS_Stop: {client.has_tts_stop} | "
                            f"TTS_Sentence_Count: {getattr(client, 'tts_sentence_count', 0)}"
                        )
                    
                    # 如果收到了TTS start，说明服务器已经开始响应，继续等待
                    if client.has_tts_start:
                        continue
                    # 如果既没有TTS start也没有TTS stop，可能服务器没有响应，等待一段时间后退出
                    elif additional_wait_time >= 3.0:  # 如果等待超过3秒还没有任何响应，退出
                        self.logger.warning(
                            f"Connection #{client.connection_id}: [DIAGNOSTIC] No response after {additional_wait_time:.1f}s, stopping wait | "
                            f"Final state - Has_STT: {client.has_stt}, Has_LLM: {client.has_llm}, "
                            f"Has_TTS_Start: {client.has_tts_start}, Has_TTS_Stop: {client.has_tts_stop}"
                        )
                        break
                
                if not tts_stop_valid:
                    self.logger.warning(
                        f"Connection #{client.connection_id}: [DIAGNOSTIC] Did not receive complete TTS stop response after {wait_time + additional_wait_time:.1f}s total wait time | "
                        f"Final state - Has_STT: {client.has_stt}, Has_LLM: {client.has_llm}, "
                        f"Has_TTS_Start: {client.has_tts_start}, Has_TTS_Stop: {client.has_tts_stop} | "
                        f"STT_Text: {getattr(client, 'stt_text', '')} | "
                        f"LLM_Text: {' '.join(getattr(client, 'llm_text_buffer', []))}"
                    )
            
            # 收集响应文本
            stt_text = getattr(client, 'stt_text', '')
            llm_text = " ".join(getattr(client, 'llm_text_buffer', []))
            
            result["stt_text"] = stt_text
            result["llm_text"] = llm_text
            result["response_text"] = f"[STT] {stt_text} | [LLM] {llm_text}" if (stt_text or llm_text) else ""
            
            # 重新验证TTS stop是否有效（在额外等待后再次检查，确保使用最新的状态）
            # 注意：tts_stop_valid 可能已经在上面被设置为True了，这里只是再次确认
            if not tts_stop_valid and client.has_tts_stop and client.tts_stop_time is not None:
                # tts_stop_time是毫秒时间戳，send_start_time_ms也是毫秒时间戳
                if client.tts_stop_time >= send_start_time_ms - 2000:  # 允许2秒误差（2000ms）
                    tts_stop_valid = True
                else:
                    # TTS stop时间在发送消息之前，说明是上一个测试的stop，忽略
                    tts_stop_time_sec = client.tts_stop_time / 1000.0
                    self.logger.debug(f"TTS stop time ({tts_stop_time_sec:.3f}s) is before send start ({send_start_time:.3f}s), ignoring")
            
            # 判断成功：如果鉴权失败，直接标记为失败
            # 成功的条件：
            # 1. 有有效的TTS stop（完整响应）
            # 2. 或者有LLM文本内容（即使没有stop，有内容也算成功）
            # 注意：仅仅有TTS start不算成功，因为可能只是开始响应但还没有实际内容
            has_llm_content = bool(llm_text and llm_text.strip())
            result["success"] = not client.auth_failed and (tts_stop_valid or has_llm_content)
            
            # 收集性能指标（时间单位：毫秒）
            # 注意：send_time, stt_response_time等都是毫秒时间戳，直接相减即可得到毫秒差值
            # 但需要确保时间戳属于本次测试（在send_start_time之后）
            send_start_time_ms = send_start_time * 1000  # 转换为毫秒时间戳
            
            # 性能指标：详细拆解各个阶段的延迟（精细化指标）
            # 1. 音频发送阶段
            if client.send_time:
                result["send_time"] = client.send_time
            if client.send_end_time:
                result["send_end_time"] = client.send_end_time
                # 计算音频发送耗时（从第一帧到最后一帧）
                if client.send_time and client.send_end_time >= send_start_time_ms - 2000:
                    send_duration_ms = client.send_end_time - client.send_time
                    if 0 <= send_duration_ms <= 60000:
                        result["send_duration"] = send_duration_ms
            
            # 2. STT服务延迟（详细拆解）
            # STT是流式处理，收到第一个包就开始处理，但最终结果在发送完所有包后才返回
            if client.send_time and client.stt_response_time:
                if client.send_time >= send_start_time_ms - 2000 and client.stt_response_time >= send_start_time_ms - 2000:
                    # 从第一帧发送到STT响应（包含发送时间+STT处理时间）
                    stt_latency_from_first = client.stt_response_time - client.send_time
                    if 0 <= stt_latency_from_first <= 60000:
                        result["stt_latency"] = stt_latency_from_first  # 保持兼容性
                        result["stt_latency_from_first_frame"] = stt_latency_from_first
                    
                    # 从最后一帧发送到STT响应（纯STT处理时间，更准确）
                    if client.send_end_time and client.send_end_time >= send_start_time_ms - 2000:
                        stt_latency_from_last = client.stt_response_time - client.send_end_time
                        if 0 <= stt_latency_from_last <= 60000:
                            result["stt_latency_from_last_frame"] = stt_latency_from_last
                else:
                    result["stt_latency"] = None
            else:
                result["stt_latency"] = None
            
            # 3. LLM服务延迟（详细拆解）
            if client.stt_response_time and client.llm_response_time:
                if client.stt_response_time >= send_start_time_ms - 2000 and client.llm_response_time >= send_start_time_ms - 2000:
                    # 从STT完成到LLM响应（纯LLM处理时间）
                    llm_latency_ms = client.llm_response_time - client.stt_response_time
                    if 0 <= llm_latency_ms <= 60000:
                        result["llm_latency"] = llm_latency_ms
                    else:
                        result["llm_latency"] = None
                else:
                    result["llm_latency"] = None
            else:
                result["llm_latency"] = None
            
            # 4. TTS服务延迟（详细拆解）
            if client.llm_response_time and client.tts_start_time:
                if client.llm_response_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    # 从LLM完成到TTS开始（TTS启动延迟）
                    tts_latency_ms = client.tts_start_time - client.llm_response_time
                    if 0 <= tts_latency_ms <= 10000:
                        result["tts_latency"] = tts_latency_ms
                    else:
                        result["tts_latency"] = None
                else:
                    result["tts_latency"] = None
            else:
                result["tts_latency"] = None
            
            # TTS持续时间（从TTS开始到TTS结束）
            if client.tts_start_time and client.tts_stop_time:
                if client.tts_start_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    tts_duration_ms = client.tts_stop_time - client.tts_start_time
                    if 0 <= tts_duration_ms <= 120000:
                        result["tts_duration"] = tts_duration_ms
                    else:
                        result["tts_duration"] = None
                else:
                    result["tts_duration"] = None
            else:
                result["tts_duration"] = None
            
            # 5. 端到端响应时间（多个维度）
            # 5.1 从第一帧发送到TTS结束（完整端到端时间）
            if client.send_time and client.tts_stop_time:
                if client.send_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    e2e_from_first = client.tts_stop_time - client.send_time
                    if 0 <= e2e_from_first <= 120000:
                        result["e2e_response_time"] = e2e_from_first  # 保持兼容性
                        result["e2e_from_first_frame"] = e2e_from_first
                else:
                    result["e2e_response_time"] = None
            elif client.send_time and client.tts_start_time:
                if client.send_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    e2e_from_first = client.tts_start_time - client.send_time
                    if 0 <= e2e_from_first <= 120000:
                        result["e2e_response_time"] = e2e_from_first
                        result["e2e_from_first_frame"] = e2e_from_first
                else:
                    result["e2e_response_time"] = None
            else:
                result["e2e_response_time"] = None
            
            # 5.2 从最后一帧发送到TTS结束（不包含发送时间）
            if client.send_end_time and client.tts_stop_time:
                if client.send_end_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    e2e_from_last = client.tts_stop_time - client.send_end_time
                    if 0 <= e2e_from_last <= 120000:
                        result["e2e_from_last_frame"] = e2e_from_last
            elif client.send_end_time and client.tts_start_time:
                if client.send_end_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    e2e_from_last = client.tts_start_time - client.send_end_time
                    if 0 <= e2e_from_last <= 120000:
                        result["e2e_from_last_frame"] = e2e_from_last
            
            # 5.3 从STT响应到TTS结束（STT后的完整处理时间）
            if client.stt_response_time and client.tts_stop_time:
                if client.stt_response_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    e2e_from_stt = client.tts_stop_time - client.stt_response_time
                    if 0 <= e2e_from_stt <= 120000:
                        result["e2e_from_stt"] = e2e_from_stt
            elif client.stt_response_time and client.tts_start_time:
                if client.stt_response_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    e2e_from_stt = client.tts_start_time - client.stt_response_time
                    if 0 <= e2e_from_stt <= 120000:
                        result["e2e_from_stt"] = e2e_from_stt
            
            # 5.4 从LLM响应到TTS结束（LLM后的完整处理时间）
            if client.llm_response_time and client.tts_stop_time:
                if client.llm_response_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    e2e_from_llm = client.tts_stop_time - client.llm_response_time
                    if 0 <= e2e_from_llm <= 120000:
                        result["e2e_from_llm"] = e2e_from_llm
            elif client.llm_response_time and client.tts_start_time:
                if client.llm_response_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    e2e_from_llm = client.tts_start_time - client.llm_response_time
                    if 0 <= e2e_from_llm <= 120000:
                        result["e2e_from_llm"] = e2e_from_llm
            
            # 收集消息统计
            result["sent_messages"] = getattr(client, 'sent_messages', 0)
            result["received_messages"] = getattr(client, 'received_messages', 0)
            result["total_sent_bytes"] = getattr(client, 'total_sent_bytes', 0)
            result["total_received_bytes"] = getattr(client, 'total_received_bytes', 0)
            
            # 收集失败原因
            if client.auth_failed:
                result["failure_reason"] = "Authentication failed"
            elif not client.is_connected:
                result["failure_reason"] = "Connection lost"
            elif not client.has_stt and not client.has_llm:
                result["failure_reason"] = "No response received (no STT, no LLM)"
            elif client.has_stt and not client.has_llm:
                result["failure_reason"] = "STT received but no LLM response"
            elif client.has_llm and not client.has_tts_stop:
                result["failure_reason"] = "LLM received but no TTS stop (incomplete response)"
            elif not tts_stop_valid:
                result["failure_reason"] = "TTS stop time invalid (likely from previous test)"
            elif wait_time >= max_wait_time:
                result["failure_reason"] = f"Timeout (waited {wait_time:.1f}s)"
            else:
                result["failure_reason"] = "Unknown"
            
            if result["success"]:
                result["failure_reason"] = None
            
            if result["success"]:
                self.logger.info(f"✓ Response received: {result['response_text'][:100]}...")
            else:
                # 详细记录失败信息，用于问题分析
                self.logger.warning(f"✗ Test FAILED: [{test_type.upper()}] #{index:03d}")
                self.logger.warning(f"  - Audio file: {os.path.basename(audio_file)}")
                self.logger.warning(f"  - Text: {text[:100]}")
                self.logger.warning(f"  - Wait time: {wait_time:.1f}s (max: {max_wait_time:.1f}s)")
                self.logger.warning(f"  - Connection ID: {client.connection_id}")
                self.logger.warning(f"  - Device SN: {getattr(client, 'device_sn', 'N/A')}")
                self.logger.warning(f"  - Connection status: {'Connected' if client.is_connected else 'Disconnected'}")
                
                # 记录响应状态
                status = f"STT: {client.has_stt}, LLM: {client.has_llm}, TTS_start: {client.has_tts_start}, TTS_stop: {client.has_tts_stop}"
                self.logger.warning(f"  - Response status: {status}")
                
                # 记录时间信息
                if client.send_time:
                    send_time_sec = client.send_time / 1000.0
                    elapsed = time.time() - send_time_sec
                    self.logger.warning(f"  - Send time: {send_time_sec:.3f}s, Elapsed: {elapsed:.1f}s")
                
                # 记录收到的文本
                if stt_text:
                    self.logger.warning(f"  - STT text: {stt_text[:200]}")
                else:
                    self.logger.warning(f"  - STT text: (empty)")
                
                if llm_text:
                    self.logger.warning(f"  - LLM text: {llm_text[:200]}")
                else:
                    self.logger.warning(f"  - LLM text: (empty)")
                
                # 记录消息统计
                self.logger.warning(f"  - Messages sent: {client.sent_messages}, received: {client.received_messages}")
                self.logger.warning(f"  - Bytes sent: {client.total_sent_bytes}, received: {client.total_received_bytes}")
                
                # 记录TTS stop时间验证
                if client.has_tts_stop and client.tts_stop_time:
                    tts_stop_time_sec = client.tts_stop_time / 1000.0
                    time_diff = tts_stop_time_sec - send_start_time
                    self.logger.warning(f"  - TTS stop time: {tts_stop_time_sec:.3f}s, Time diff from send: {time_diff:.3f}s")
                    if time_diff < -2.0:
                        self.logger.warning(f"  - ⚠️ TTS stop time is before send time (likely from previous test)")
                
                # 记录失败原因
                if client.auth_failed:
                    self.logger.warning(f"  - ❌ Failure reason: Authentication failed (SN not in whitelist or sign mismatch)")
                elif not client.is_connected:
                    self.logger.warning(f"  - ❌ Failure reason: Connection lost")
                elif not client.has_stt and not client.has_llm:
                    self.logger.warning(f"  - ❌ Failure reason: No response received (no STT, no LLM)")
                elif client.has_stt and not client.has_llm:
                    self.logger.warning(f"  - ❌ Failure reason: STT received but no LLM response")
                elif client.has_llm and not client.has_tts_stop:
                    self.logger.warning(f"  - ❌ Failure reason: LLM received but no TTS stop (incomplete response)")
                elif not tts_stop_valid:
                    self.logger.warning(f"  - ❌ Failure reason: TTS stop time invalid (likely from previous test)")
                else:
                    self.logger.warning(f"  - ❌ Failure reason: Timeout (waited {wait_time:.1f}s)")
            
        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"Error testing audio: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        return result
    
    async def run_test(self):
        """运行完整测试（基于test_runner.py的逻辑）"""
        # 尝试解析文本文件（可选，主要用于记录）
        inquiries_file = os.path.join(os.path.dirname(__file__), "product_inquiries.txt")
        inquiries_texts, purchases_texts = self.parse_inquiries_file(inquiries_file)
        
        # 如果没有文本文件，使用默认文本
        if not inquiries_texts:
            inquiries_texts = [f"询问 #{i+1}" for i in range(50)]
        if not purchases_texts:
            purchases_texts = [f"购买 #{i+1}" for i in range(50)]
        
        self.logger.info("=" * 60)
        self.logger.info("开始测试询问和购买音频")
        self.logger.info(f"总询问数: {len(inquiries_texts)}")
        self.logger.info(f"总购买数: {len(purchases_texts)}")
        self.logger.info(f"服务器地址: {Config.get_websocket_url()}")
        self.logger.info("=" * 60)
        
        # 创建WebSocket客户端（与test_runner.py的逻辑一致）
        client = WebSocketClient(connection_id=1)
        
        try:
            # 建立连接（与test_runner.py的逻辑一致）
            self.logger.info("Connecting to server...")
            connected = await client.connect()
            
            if not connected:
                self.logger.error("Failed to connect to server")
                return
            
            # 等待收到服务器消息（与test_runner.py的逻辑一致）
            max_wait_server_msg = 3.0
            initial_wait = 0.2
            wait_server_msg_time = 0
            check_interval = 0.1
            
            await asyncio.sleep(initial_wait)
            
            while wait_server_msg_time < max_wait_server_msg and client.is_connected:
                if client.auth_received or client.session_id:
                    break
                await asyncio.sleep(check_interval)
                wait_server_msg_time += check_interval
            
            # 检查鉴权结果
            if client.auth_failed:
                self.logger.error("Authentication failed, cannot proceed with tests")
                return
            
            if not client.session_id and not client.auth_received:
                self.logger.warning("No auth message received, but proceeding anyway")
            else:
                self.logger.info("Authentication successful")
            
            self.logger.info("Connected successfully")
            
            # 按顺序测试：先询问，后购买（确保询问响应完成后再进行购买）
            for i in range(min(len(inquiries_texts), len(purchases_texts))):
                inquiry_text = inquiries_texts[i] if i < len(inquiries_texts) else f"询问 #{i+1}"
                purchase_text = purchases_texts[i] if i < len(purchases_texts) else f"购买 #{i+1}"
                
                # 获取音频文件
                inquiry_file = self.get_audio_file(i + 1, "inquiry")
                purchase_file = self.get_audio_file(i + 1, "purchase")
                
                if not inquiry_file:
                    self.logger.error(f"Inquiry audio file not found: inquiry_{i+1:03d}.opus")
                    continue
                
                if not purchase_file:
                    self.logger.error(f"Purchase audio file not found: purchase_{i+1:03d}.opus")
                    continue
                
                # 1. 测试询问（等待完整响应）
                inquiry_result = await self.test_single_audio(
                    client, inquiry_file, inquiry_text, "inquiry", i + 1
                )
                self.results.append(inquiry_result)
                
                # 等待响应完全结束（与test_runner.py的逻辑一致）
                final_wait = 0.5
                await asyncio.sleep(final_wait)
                
                # 2. 测试购买（等待完整响应）
                purchase_result = await self.test_single_audio(
                    client, purchase_file, purchase_text, "purchase", i + 1
                )
                self.results.append(purchase_result)
                
                # 等待响应完全结束
                await asyncio.sleep(final_wait)
                
                # 每10个测试对后保存一次结果
                if (i + 1) % 10 == 0:
                    self.save_results()
                    self.logger.info(f"Progress: {i+1}/{len(inquiries_texts)} pairs completed")
        
        except Exception as e:
            self.logger.error(f"Error during test: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            # 关闭连接（与test_runner.py的逻辑一致）
            if client.is_connected:
                await client.close()
            
            # 保存最终结果
            self.save_results()
            
            # 打印摘要
            self.print_summary()
    
    def save_results(self):
        """保存测试结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(os.path.dirname(__file__), "results")
        os.makedirs(results_dir, exist_ok=True)
        
        results_file = os.path.join(results_dir, f"inquiry_test_results_{timestamp}.json")
        text_file = os.path.join(results_dir, f"inquiry_test_results_{timestamp}.txt")
        
        # 保存JSON格式
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_start_time": self.test_start_time.isoformat(),
                "test_end_time": datetime.now().isoformat(),
                "total_tests": len(self.results),
                "results": self.results
            }, f, ensure_ascii=False, indent=2)
        
        # 保存文本格式（便于查看）
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("询问和购买测试结果\n")
            f.write("=" * 80 + "\n")
            f.write(f"测试开始时间: {self.test_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"测试结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总测试数: {len(self.results)}\n")
            f.write("=" * 80 + "\n\n")
            
            for result in self.results:
                f.write(f"\n[{result['type'].upper()}] #{result['index']:03d}\n")
                f.write(f"提问: {result['text']}\n")
                f.write(f"音频文件: {result['audio_file']}\n")
                f.write(f"状态: {'✓ 成功' if result['success'] else '✗ 失败'}\n")
                if result['error']:
                    f.write(f"错误: {result['error']}\n")
                if result.get('stt_text'):
                    f.write(f"STT识别: {result['stt_text']}\n")
                if result.get('llm_text'):
                    f.write(f"LLM返回: {result['llm_text']}\n")
                f.write(f"完整返回: {result['response_text']}\n")
                f.write("-" * 80 + "\n")
        
        self.logger.info(f"Results saved to: {results_file}")
        self.logger.info(f"Text results saved to: {text_file}")
    
    def print_summary(self):
        """打印测试摘要"""
        total = len(self.results)
        successful = sum(1 for r in self.results if r['success'])
        failed = total - successful
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info("测试摘要")
        self.logger.info("=" * 60)
        self.logger.info(f"总测试数: {total}")
        if total > 0:
            self.logger.info(f"成功: {successful} ({successful/total*100:.1f}%)")
            self.logger.info(f"失败: {failed} ({failed/total*100:.1f}%)")
        else:
            self.logger.info("成功: 0 (0.0%)")
            self.logger.info("失败: 0 (0.0%)")
            self.logger.warning("没有执行任何测试，请检查音频文件是否存在")
        self.logger.info("=" * 60)

async def main():
    """主函数"""
    tester = InquiryTester()
    await tester.run_test()

if __name__ == "__main__":
    asyncio.run(main())

