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
    
    def get_audio_file(self, index: int, prefix: str) -> Optional[str]:
        """获取音频文件路径（Opus格式）"""
        filename = f"{prefix}_{index:03d}.opus"
        file_path = os.path.join(AUDIO_DIR, filename)
        return file_path if os.path.exists(file_path) else None
    
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
            audio_frames = self.load_audio_frames(audio_file)
            if not audio_frames:
                result["error"] = "Failed to load audio frames"
                return result
            
            # 记录发送消息前的时间，用于判断后续消息是否属于本次测试
            send_start_time = time.time()
            
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
                
                if test_mode == "fast":
                    # 急速模式：只要大模型开始回复就继续下一个问题
                    # 检查是否收到LLM响应（必须是大模型开始回复，不能仅仅是STT）
                    # has_llm 标志只在收到LLM消息或TTS的sentence_start时设置，不会因为STT而设置
                    # llm_text_buffer 也只在LLM相关消息时填充
                    if client.has_llm:
                        # 进一步确认：必须有实际的LLM内容（不能仅仅是STT）
                        has_llm_content = (hasattr(client, 'llm_text_buffer') and 
                                          client.llm_text_buffer and 
                                          len(client.llm_text_buffer) > 0)
                        if has_llm_content:
                            self.logger.info(f"Connection #{client.connection_id}: LLM response started at {wait_time:.1f}s, proceeding to next question (fast mode)")
                            break
                
                # 正常模式或急速模式：如果收到完整响应（TTS stop），都可以提前退出
                if client.has_tts_stop:
                    self.logger.info(f"Connection #{client.connection_id}: Received complete response at {wait_time:.1f}s")
                    break
            
            # 等待循环结束后，再给一点时间让异步消息处理完成
            # 避免消息在等待循环结束后才到达的情况
            if test_mode == "fast":
                # 急速模式：如果没有收到LLM响应，额外等待
                if not client.has_llm or not (hasattr(client, 'llm_text_buffer') and client.llm_text_buffer):
                    await asyncio.sleep(0.2)  # 额外等待 200ms
            else:
                # 正常模式：如果没有收到完整响应，额外等待
                if not client.has_tts_stop:
                    await asyncio.sleep(0.2)  # 额外等待 200ms
            
            # 收集响应文本
            stt_text = getattr(client, 'stt_text', '')
            llm_text = " ".join(getattr(client, 'llm_text_buffer', []))
            
            result["stt_text"] = stt_text
            result["llm_text"] = llm_text
            result["response_text"] = f"[STT] {stt_text} | [LLM] {llm_text}" if (stt_text or llm_text) else ""
            
            # 判断TTS stop是否有效（确保是本次测试的stop，而不是上一个测试的）
            tts_stop_valid = False
            if client.has_tts_stop and client.tts_stop_time is not None:
                # tts_stop_time是毫秒时间戳（从get_timestamp()获取，返回time.time() * 1000）
                # send_start_time是秒时间戳（从time.time()获取）
                # 需要统一单位进行比较：将毫秒转换为秒
                tts_stop_time_sec = client.tts_stop_time / 1000.0
                # 检查TTS stop时间是否在发送消息之后（允许2秒误差，因为可能有延迟或时间同步问题）
                if tts_stop_time_sec >= send_start_time - 2.0:  # 允许2秒误差
                    tts_stop_valid = True
                else:
                    # TTS stop时间在发送消息之前，说明是上一个测试的stop，忽略
                    self.logger.debug(f"TTS stop time ({tts_stop_time_sec:.3f}s) is before send start ({send_start_time:.3f}s), ignoring")
            
            # 判断成功：如果鉴权失败，直接标记为失败；否则检查TTS stop有效，或者有LLM返回内容
            result["success"] = not client.auth_failed and (tts_stop_valid or (bool(llm_text and llm_text.strip())))
            
            # 收集性能指标（时间单位：毫秒）
            # 注意：send_time, stt_response_time等都是毫秒时间戳，直接相减即可得到毫秒差值
            # 但需要确保时间戳属于本次测试（在send_start_time之后）
            send_start_time_ms = send_start_time * 1000  # 转换为毫秒时间戳
            
            if client.send_time and client.stt_response_time:
                # 确保时间戳属于本次测试
                if client.send_time >= send_start_time_ms - 2000 and client.stt_response_time >= send_start_time_ms - 2000:
                    stt_time_ms = client.stt_response_time - client.send_time
                    # 过滤异常值：应该在0到60秒之间（0-60000ms）
                    if 0 <= stt_time_ms <= 60000:
                        result["stt_time"] = stt_time_ms
                    else:
                        result["stt_time"] = None
                else:
                    result["stt_time"] = None
            else:
                result["stt_time"] = None
            
            if client.stt_response_time and client.llm_response_time:
                if client.stt_response_time >= send_start_time_ms - 2000 and client.llm_response_time >= send_start_time_ms - 2000:
                    llm_time_ms = client.llm_response_time - client.stt_response_time
                    # 过滤异常值：应该在0到60秒之间
                    if 0 <= llm_time_ms <= 60000:
                        result["llm_time"] = llm_time_ms
                    else:
                        result["llm_time"] = None
                else:
                    result["llm_time"] = None
            else:
                result["llm_time"] = None
            
            if client.llm_response_time and client.tts_start_time:
                if client.llm_response_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    tts_start_time_ms = client.tts_start_time - client.llm_response_time
                    # 过滤异常值：应该在0到10秒之间
                    if 0 <= tts_start_time_ms <= 10000:
                        result["tts_start_time"] = tts_start_time_ms
                    else:
                        result["tts_start_time"] = None
                else:
                    result["tts_start_time"] = None
            else:
                result["tts_start_time"] = None
            
            if client.tts_start_time and client.tts_stop_time:
                if client.tts_start_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    tts_duration_ms = client.tts_stop_time - client.tts_start_time
                    # 过滤异常值：应该在0到120秒之间
                    if 0 <= tts_duration_ms <= 120000:
                        result["tts_duration"] = tts_duration_ms
                    else:
                        result["tts_duration"] = None
                else:
                    result["tts_duration"] = None
            else:
                result["tts_duration"] = None
            
            if client.send_time and client.tts_stop_time:
                if client.send_time >= send_start_time_ms - 2000 and client.tts_stop_time >= send_start_time_ms - 2000:
                    total_time_ms = client.tts_stop_time - client.send_time
                    # 过滤异常值：应该在0到120秒之间
                    if 0 <= total_time_ms <= 120000:
                        result["total_response_time"] = total_time_ms
                    else:
                        result["total_response_time"] = None
                else:
                    result["total_response_time"] = None
            elif client.send_time and client.tts_start_time:
                if client.send_time >= send_start_time_ms - 2000 and client.tts_start_time >= send_start_time_ms - 2000:
                    total_time_ms = client.tts_start_time - client.send_time
                    # 过滤异常值：应该在0到120秒之间
                    if 0 <= total_time_ms <= 120000:
                        result["total_response_time"] = total_time_ms
                    else:
                        result["total_response_time"] = None
                else:
                    result["total_response_time"] = None
            else:
                result["total_response_time"] = None
            
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

