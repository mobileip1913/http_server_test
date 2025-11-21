"""
主测试脚本：执行 WebSocket 性能测试
"""
import asyncio
import sys
import signal
from typing import List, Optional
from logger import Logger
from config import Config
from websocket_client import WebSocketClient
from iot_hardware_simulator import IoTHardwareSimulator
from metrics_collector import MetricsCollector
from audio_encoder import AudioEncoder

class TestRunner:
    """测试运行器类"""
    
    def __init__(self):
        self.logger = Logger()
        self.metrics_collector = MetricsCollector()
        self.audio_encoder = AudioEncoder() if Config.SEND_AUDIO_DATA else None
        self.clients: List[WebSocketClient] = []
        self.running = True
        
        # 预生成音频帧列表（如果启用）
        self.test_audio_frames: Optional[List[bytes]] = None
        if Config.SEND_AUDIO_DATA and self.audio_encoder:
            self.logger.info("正在生成测试音频帧...")
            self.test_audio_frames = self.audio_encoder.text_to_opus_frames(Config.TEST_MESSAGE)
            if self.test_audio_frames:
                total_bytes = sum(len(frame) for frame in self.test_audio_frames)
                self.logger.info(f"已生成 {len(self.test_audio_frames)} 个 Opus 帧，总计 {total_bytes} 字节")
            else:
                self.logger.warning("生成音频帧失败，将使用纯文本模式")
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器（Ctrl+C）"""
        self.logger.info("收到中断信号，正在停止测试...")
        self.running = False
    
    async def _delayed_connection(self, connection_id: int, delay: float) -> WebSocketClient:
        """延迟启动连接（用于均匀分布连接启动时间）"""
        if delay > 0:
            await asyncio.sleep(delay)
        return await self.run_single_connection(connection_id)
    
    async def run_single_connection(self, connection_id: int) -> WebSocketClient:
        """运行单个连接测试"""
        self.logger.info(f"连接 #{connection_id}: 开始... (USE_IOT_SIMULATOR={Config.USE_IOT_SIMULATOR})")
        # 如果启用IOT模拟器，使用高拟真硬件模拟器
        if Config.USE_IOT_SIMULATOR:
            simulator = IoTHardwareSimulator(connection_id, self.logger)
            self.clients.append(simulator.client)  # 添加底层客户端用于指标收集
            try:
                connected = await simulator.connect()
                if not connected:
                    self.logger.error_log(connection_id, "ConnectionFailed", "通过模拟器建立连接失败")
                    return simulator.client  # 返回客户端用于指标
                
                if Config.HEARTBEAT_ENABLED:
                    await simulator.start_heartbeat(Config.HEARTBEAT_INTERVAL_SEC)

                # 等待服务器下发 auth/session_id
                # 极限性能模式：减少等待时间
                if Config.STRESS_TEST_MODE:
                    max_wait_server_msg = Config.STRESS_AUTH_WAIT_SEC
                    initial_wait = 0.1
                else:
                    max_wait_server_msg = 3.0
                    initial_wait = 0.2
                
                wait_server_msg_time = 0.0
                check_interval = 0.1
                await asyncio.sleep(initial_wait)
                while wait_server_msg_time < max_wait_server_msg and simulator.client.is_connected:
                    if simulator.client.auth_received or simulator.client.session_id:
                        break
                    await asyncio.sleep(check_interval)
                    wait_server_msg_time += check_interval
                
                # 性能测试模式：每个连接只发送一次消息，避免产生多次聊天记录
                # 使用 auto 或 manual 模式，确保一次完整的请求-响应循环
                if Config.LISTENING_MODE == "realtime":
                    # realtime模式：进入持续对话，但只发送一次消息后立即退出
                    await simulator.enter_keep_listening()
                    await simulator.send_speech(Config.TEST_MESSAGE, audio_frames=self.test_audio_frames, send_stop=False)
                    # 等待响应后立即退出，避免持续对话产生多次记录
                    # 极限性能模式：根据并发数动态计算等待时间
                    realtime_wait = Config.get_stress_response_wait_sec() if Config.STRESS_TEST_MODE else 2.0
                    await asyncio.sleep(realtime_wait)
                    await simulator.exit_keep_listening()
                else:
                    # auto或manual模式：发送一次语音并可选发送stop_listen
                    await simulator.send_speech(Config.TEST_MESSAGE, audio_frames=self.test_audio_frames, send_stop=Config.SEND_STOP_LISTEN)
                
                # 等待响应（设置超时）
                # 极限性能模式：根据并发数动态计算等待时间
                if Config.STRESS_TEST_MODE:
                    max_wait_time = Config.get_stress_response_wait_sec()
                else:
                    max_wait_time = Config.TTS_TIMEOUT / 1000.0
                
                wait_time = 0
                check_interval = 0.1
                
                while wait_time < max_wait_time and self.running:
                    await asyncio.sleep(check_interval)
                    wait_time += check_interval
                    if simulator.client.has_tts_stop:
                        self.logger.info(f"连接 #{connection_id}: 通过模拟器收到完整响应，耗时 {wait_time:.1f}秒")
                        break
                
                # 等待结束后，记录收到的响应状态（用于诊断）
                if not simulator.client.has_tts_stop:
                    status = f"连接 #{connection_id}: 等待 {wait_time:.1f}秒后未收到完整响应"
                    status += f" | STT: {simulator.client.has_stt}"
                    status += f" | LLM: {simulator.client.has_llm}"
                    status += f" | TTS_start: {simulator.client.has_tts_start}"
                    status += f" | TTS_stop: {simulator.client.has_tts_stop}"
                    status += f" | 收到消息数: {simulator.client.received_messages}"
                    status += f" | 连接状态: {simulator.client.is_connected}"
                    self.logger.debug(status)
                
                # 极限性能模式：减少最后等待时间
                final_wait = Config.STRESS_FINAL_WAIT_SEC if Config.STRESS_TEST_MODE else 0.5
                await asyncio.sleep(final_wait)
                
            except Exception as e:
                self.logger.error_log(connection_id, "TestError", str(e))
                import traceback
                self.logger.error(f"Connection #{connection_id}: Exception in simulator: {traceback.format_exc()}")
            finally:
                await simulator.close()
            return simulator.client
        else:
            # 使用原始WebSocketClient逻辑
            client = WebSocketClient(connection_id)
        self.clients.append(client)
        
        try:
            # 建立连接
            connected = await client.connect()
            if not connected:
                self.logger.error_log(connection_id, "ConnectionFailed", "Failed to establish connection")
                return client
            
            # 等待收到服务器消息
            # 极限性能模式：减少等待时间
            if Config.STRESS_TEST_MODE:
                max_wait_server_msg = Config.STRESS_AUTH_WAIT_SEC
                initial_wait = 0.1
            else:
                max_wait_server_msg = 3.0
                initial_wait = 0.2
            
            wait_server_msg_time = 0
            check_interval = 0.1  # 每 100ms 检查一次
            
            # 等待一小段时间让消息到达
            await asyncio.sleep(initial_wait)
            
            # 检查是否收到消息或有 session_id
            while wait_server_msg_time < max_wait_server_msg and client.is_connected:
                if client.auth_received or client.session_id:
                    break
                await asyncio.sleep(check_interval)
                wait_server_msg_time += check_interval
            
            if not client.session_id and not client.auth_received:
                self.logger.debug(f"Connection #{connection_id}: No auth message received, proceeding anyway")
            
            # 发送测试消息
            if client.is_connected:
                # 根据配置决定发送音频帧还是文本消息
                if Config.SEND_AUDIO_DATA and self.test_audio_frames:
                    # 音频模式：发送 start_listen + 逐帧发送 Opus 音频数据
                    await client.send_user_message(Config.TEST_MESSAGE, self.test_audio_frames)
                else:
                    # 文本模式：只发送 start_listen 消息（用于快速测试）
                    await client.send_user_message(Config.TEST_MESSAGE, None)
                
                # 等待响应（设置超时）
                # 极限性能模式：根据并发数动态计算等待时间
                if Config.STRESS_TEST_MODE:
                    max_wait_time = Config.get_stress_response_wait_sec()
                else:
                    max_wait_time = Config.TTS_TIMEOUT / 1000.0  # 转换为秒
                
                wait_time = 0
                check_interval = 0.1  # 每 100ms 检查一次
                
                # 记录初始连接状态
                initial_connected = client.is_connected
                self.logger.debug(f"Connection #{connection_id}: Starting wait, connected: {initial_connected}")
                
                while wait_time < max_wait_time and self.running:
                    await asyncio.sleep(check_interval)
                    wait_time += check_interval
                    
                    # 定期检查连接状态（每5秒检查一次）
                    if int(wait_time * 10) % 50 == 0:  # 每5秒
                        if not client.is_connected:
                            self.logger.warning(
                                f"Connection #{connection_id}: Connection lost during wait "
                                f"(at {wait_time:.1f}s), received_msgs: {client.received_messages}"
                            )
                            break
                    
                    # 检查是否收到完整响应
                    if client.has_tts_stop:
                        self.logger.info(f"Connection #{connection_id}: Received complete response at {wait_time:.1f}s")
                        break
                
                # 记录等待结束时的状态
                final_connected = client.is_connected
                final_received = client.received_messages
                self.logger.debug(
                    f"Connection #{connection_id}: Wait ended at {wait_time:.1f}s, "
                    f"connected: {final_connected}, received_msgs: {final_received}, "
                    f"has_stt: {client.has_stt}, has_llm: {client.has_llm}, has_tts: {client.has_tts_start}"
                )
                
                # 极限性能模式：减少最后等待时间
                final_wait = Config.STRESS_FINAL_WAIT_SEC if Config.STRESS_TEST_MODE else 0.5
                await asyncio.sleep(final_wait)
            
        except Exception as e:
            self.logger.error_log(connection_id, "TestError", str(e))
        finally:
            # 关闭连接
            await client.close()
        
        return client
    
    async def run_concurrent_test(self):
        """运行并发测试"""
        # 获取实际并发连接数（调试模式返回1）
        actual_connections = Config.get_concurrent_connections()
        mode_str = "DEBUG MODE" if Config.DEBUG_MODE else "TEST MODE"
        
        self.logger.info("=" * 60)
        mode_str_cn = "调试模式" if Config.DEBUG_MODE else "测试模式"
        self.logger.info(f"开始 WebSocket 性能测试 - {mode_str_cn}")
        self.logger.info("=" * 60)
        if Config.DEBUG_MODE:
            self.logger.info(f"⚠️  调试模式: 使用 1 个连接（用于调试）")
            self.logger.info(f"   设置 DEBUG_MODE=false 以启用完整测试（{Config.CONCURRENT_CONNECTIONS} 个连接）")
        else:
            self.logger.info(f"并发连接数: {actual_connections}")
        
        # 显示极限性能模式状态
        if Config.STRESS_TEST_MODE:
            dynamic_wait_time = Config.get_stress_response_wait_sec()
            self.logger.info(f"⚡ 极限性能模式: 已启用（根据并发数动态调整等待时间）")
            self.logger.info(f"   - Auth等待: {Config.STRESS_AUTH_WAIT_SEC}秒")
            self.logger.info(f"   - 响应等待: {dynamic_wait_time:.1f}秒（动态计算：基础{Config.STRESS_RESPONSE_BASE_SEC}秒 + 每个连接{Config.STRESS_RESPONSE_PER_CONN_SEC}秒 × {actual_connections}连接）")
            self.logger.info(f"   - 最后等待: {Config.STRESS_FINAL_WAIT_SEC}秒")
        else:
            self.logger.info(f"✓ 完整响应模式: 等待完整响应（用于端到端性能测试）")
        
        self.logger.info(f"测试消息: {Config.TEST_MESSAGE}")
        self.logger.info(f"服务器地址: {Config.get_websocket_url()}")
        self.logger.info(f"设备SN: {Config.DEVICE_SN} (已注册)")
        self.logger.info(f"板卡类型: {Config.BOARD_TYPE}")
        self.logger.info(f"发送音频数据: {Config.SEND_AUDIO_DATA}")
        self.logger.info("=" * 60)
        
        self.metrics_collector.start_test()
        
        # 创建所有连接任务
        # 极限性能测试：100个连接在1秒内均匀分布发送，模拟真实场景
        tasks = []
        if actual_connections > 1:
            # 计算每个连接之间的间隔（秒）
            total_spread_time = 1.0  # 1秒内分布
            interval = total_spread_time / actual_connections
            
            self.logger.info(f"连接启动方式: 在 {total_spread_time} 秒内均匀分布 {actual_connections} 个连接（间隔 {interval*1000:.1f}ms）")
            
            for i in range(1, actual_connections + 1):
                if not self.running:
                    break
                # 计算这个连接的启动延迟
                delay = (i - 1) * interval
                task = asyncio.create_task(self._delayed_connection(i, delay))
                tasks.append(task)
        else:
            # 单个连接，直接启动
            for i in range(1, actual_connections + 1):
                if not self.running:
                    break
                task = asyncio.create_task(self.run_single_connection(i))
                tasks.append(task)
        
        # 等待所有任务完成
        self.logger.info(f"等待 {len(tasks)} 个连接完成...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 检查结果中的异常
        for i, result in enumerate(results, 1):
            if isinstance(result, Exception):
                self.logger.error(f"连接 #{i} 失败，异常: {result}")
                import traceback
                self.logger.error(traceback.format_exc())
        
        # 收集指标
        for client in self.clients:
            metrics = client.get_metrics()
            self.metrics_collector.add_metrics(metrics)
        
        self.metrics_collector.end_test()
        
        # 导出结果
        self.logger.info("导出测试结果...")
        csv_file, json_file = self.metrics_collector.export_all()
        
        self.logger.info(f"测试完成。结果已保存到:")
        self.logger.info(f"  CSV: {csv_file}")
        self.logger.info(f"  JSON: {json_file}")
        
        return results
    
    def run(self):
        """运行测试（主入口）"""
        # 验证配置
        is_valid, error_message = Config.validate()
        if not is_valid:
            self.logger.error(f"配置验证失败: {error_message}")
            sys.exit(1)
        
        # 运行测试
        try:
            asyncio.run(self.run_concurrent_test())
        except KeyboardInterrupt:
            self.logger.info("测试被用户中断")
        except Exception as e:
            self.logger.error(f"测试失败，错误: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            sys.exit(1)

def main():
    """主函数"""
    runner = TestRunner()
    runner.run()

if __name__ == "__main__":
    main()

