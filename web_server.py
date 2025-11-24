"""
测试Web服务：提供测试界面和实时数据展示
"""
import os
import json
import asyncio
import threading
import multiprocessing
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import sys
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from test_inquiries import InquiryTester
from config import Config

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key-2025'
# 使用 threading 模式以支持在后台线程中发送消息
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)
CORS(app)

# 全局测试状态
test_state = {
    "is_running": False,
    "progress": 0,
    "total": 0,
    "current_test": None,
    "results": [],
    "summary": {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "success_rate": 0.0
    },
    "start_time": None,
    "end_time": None,
    "error": None
}

# 测试器实例
tester_instance = None
test_thread = None

def emit_test_update(event, data):
    """发送测试更新到前端"""
    # Flask-SocketIO 5.x 版本：从后台线程发送消息需要使用应用上下文
    # 不需要 broadcast 参数，默认就是广播所有连接的客户端
    try:
        # 在应用上下文中发送消息
        with app.app_context():
            socketio.emit(event, data)
    except Exception as e:
        # 如果发送失败，记录错误但不中断测试
        print(f"Failed to emit {event}: {e}")
        import traceback
        traceback.print_exc()

class WebInquiryTester(InquiryTester):
    """带WebSocket通知的测试器"""
    
    def __init__(self):
        super().__init__()
        self.current_index = 0
        self.current_client = None  # 保存当前测试的客户端，用于实时更新
    
    def _create_tts_sentence_callback(self, client, test_index: int, test_type: str, test_text: str, is_single_test: bool = False):
        """为每个测试创建独立的TTS句子回调函数，绑定到该测试的index和type"""
        # 存储已发送的句子数量，用于流式显示
        sent_sentence_count = [0]  # 使用列表以便在闭包中修改
        
        def callback(text: str, stt_text: str = ""):
            # 获取当前客户端的LLM文本缓冲区
            llm_sentences = []
            if client and hasattr(client, 'llm_text_buffer'):
                llm_sentences = client.llm_text_buffer
            
            # 获取STT文本（只使用当前客户端的STT文本，而不是传入的参数，避免并发测试时的混乱）
            current_stt_text = ""
            if client and hasattr(client, 'stt_text'):
                current_stt_text = client.stt_text or ""
            
            # 流式显示：只发送新增的句子，而不是所有累积的句子
            new_sentences = llm_sentences[sent_sentence_count[0]:]
            if new_sentences:
                # 更新已发送的句子数量
                sent_sentence_count[0] = len(llm_sentences)
                # 只发送新句子（用于流式显示）
                new_sentence = new_sentences[-1]  # 最新的一句
                # 同时发送累积文本（用于完整显示）
                cumulative_text = " ".join(llm_sentences)
            else:
                new_sentence = ""
                cumulative_text = " ".join(llm_sentences) if llm_sentences else ""
            
            # 根据是否为单语音测试选择不同的事件
            if is_single_test:
                # 单语音测试使用专门的事件
                emit_test_update("single_test_update", {
                    "stt_text": current_stt_text,
                    "llm_text": cumulative_text,  # 累积文本（用于完整显示）
                    "llm_sentence": new_sentence,  # 新句子（用于流式追加）
                    "status": "testing"
                })
            else:
                # 批量测试使用原有的事件
                emit_test_update("test_detail_update", {
                    "index": test_index,
                    "type": test_type,
                    "text": test_text,
                    "stt_text": current_stt_text,
                    "llm_text": cumulative_text,  # 累积文本（用于完整显示）
                    "llm_sentence": new_sentence,  # 新句子（用于流式追加）
                    "status": "testing"
                })
        
        return callback
    
    async def test_single_audio(self, client, audio_file: str, text: str, 
                                test_type: str, index: int, concurrency_index: int = None, is_single_test: bool = False) -> dict:
        """重写测试方法，添加实时通知"""
        # 保存当前客户端，用于实时更新
        self.current_client = client
        
        # 为当前测试创建独立的TTS句子回调函数（绑定到当前测试的index和type）
        # 如果回调已经设置（例如在单语音测试中），则不覆盖
        if not hasattr(client, '_tts_sentence_callback') or client._tts_sentence_callback is None:
            client._tts_sentence_callback = self._create_tts_sentence_callback(
                client, index, test_type, text, is_single_test=is_single_test
            )
        
        # 更新当前测试状态
        test_state["current_test"] = {
            "index": index,
            "type": test_type,
            "text": text,
            "audio_file": os.path.basename(audio_file),
            "status": "running",
            "timestamp": datetime.now().isoformat()
        }
        
        # 发送测试开始事件（包含并发索引）
        test_start_data = test_state["current_test"].copy()
        if concurrency_index is not None:
            test_start_data["concurrency_index"] = concurrency_index
        emit_test_update("test_start", test_start_data)
        
        # 执行测试
        try:
            result = await super().test_single_audio(client, audio_file, text, test_type, index)
        finally:
            # 测试完成后，清理回调函数，避免内存泄漏
            if hasattr(client, '_tts_sentence_callback'):
                client._tts_sentence_callback = None
        
        # 更新结果（确保包含所有必要字段）
        test_state["current_test"]["status"] = "completed" if result.get("success", False) else "failed"
        test_state["current_test"]["result"] = result
        
        # 确保result包含所有字段
        result["index"] = index
        result["type"] = test_type
        result["text"] = text  # 确保包含原始文本
        if "timestamp" not in result:
            result["timestamp"] = datetime.now().isoformat()
        
        # 发送结果更新（包含完整的result数据和并发索引）
        emit_test_update("test_result", {
            "result": result,
            "current_test": test_state["current_test"],
            "concurrency_index": concurrency_index
        })
        
        return result
    
    async def run_test(self):
        """重写运行测试方法，添加进度通知 - 使用前端设置的SN、并发数和测试模式"""
        global test_state
        
        # 从test_state获取设置，如果没有则使用默认值
        settings = test_state.get("settings", {})
        device_sns = settings.get("device_sns", [
            "FC012C2EA0D4",
            "FC012C2EA174",
            "FC012C2EA0E8",
            "FC012C2EA134",
            "FC012C2EA114",
            "FC012C2EA0A0",
            "FC012C2EA108",
            "FC012C2E9E18",
            "FC012C2E9E34",
            "FC012C2E9E2C"
        ])
        # 优先使用设置中的并发数，如果没有则使用SN数量
        concurrency = settings.get("concurrency")
        if concurrency is None:
            concurrency = len(device_sns)
        test_mode = settings.get("test_mode", "normal")
        
        # 记录实际使用的设置
        self.logger.info(f"测试设置 - 并发数: {concurrency}, SN数量: {len(device_sns)}, 测试模式: {test_mode}")
        self.logger.info(f"SN列表: {device_sns}")
        
        # 如果并发数大于SN数量，每个SN创建多个连接
        # 例如：10个SN，100个并发 = 每个SN创建10个连接
        connections_per_sn = max(1, concurrency // len(device_sns))
        total_connections = connections_per_sn * len(device_sns)
        
        if concurrency > len(device_sns):
            self.logger.info(f"并发数({concurrency})大于SN数量({len(device_sns)})，每个SN将创建{connections_per_sn}个连接，总共{total_connections}个并发连接")
        elif concurrency < len(device_sns):
            self.logger.info(f"并发数({concurrency})小于SN数量({len(device_sns)})，只使用前{concurrency}个SN")
            device_sns = device_sns[:concurrency]
            connections_per_sn = 1
            total_connections = concurrency
        else:
            connections_per_sn = 1
            total_connections = len(device_sns)
        
        # 设置测试模式到Config（供test_single_audio使用）
        from config import Config
        Config.TEST_MODE = test_mode
        
        try:
            # 初始化状态
            test_state["is_running"] = True
            test_state["error"] = None
            test_state["start_time"] = datetime.now().isoformat()
            test_state["results"] = []
            test_state["summary"] = {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0.0
            }
            
            # 计算实际并发连接数（在device_sns可能被截取之前计算）
            connections_per_sn_for_notification = max(1, concurrency // len(device_sns)) if concurrency > len(device_sns) else 1
            total_connections_for_notification = connections_per_sn_for_notification * len(device_sns) if concurrency > len(device_sns) else min(concurrency, len(device_sns))
            
            # 统一处理所有audio_前缀的文件（不再区分类型）
            inquiries_texts, compares_texts, orders_texts = self.parse_text_files()
            
            # 从file_list.txt读取文本映射（用于准确匹配文本）
            import re
            FILE_LIST_TXT = os.path.join(os.path.dirname(__file__), "audio", "inquiries", "file_list.txt")
            text_map = {}  # {filename: text}
            if os.path.exists(FILE_LIST_TXT):
                with open(FILE_LIST_TXT, 'r', encoding='utf-8') as f:
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
            
            # 准备所有测试任务（统一处理，不再区分类型）
            all_test_items = []
            
            # 统一扫描所有audio_前缀的文件
            all_indices = self.scan_audio_files()
            
            # 统计opus文件总数
            total_opus_files = len(all_indices)
            
            # 检查是否有测试数量限制
            test_count = settings.get("test_count")
            
            if test_count and test_count > 0:
                # 随机选择指定数量的文件（统一处理，不再区分类型）
                selected_items = self._random_select_test_files(
                    all_indices, [], [],  # 统一使用all_indices
                    inquiries_texts, [], [],  # 统一使用inquiries_texts
                    test_count
                )
                all_test_items = selected_items
                # 实际测试数 = 选择的文件数
                actual_test_count = len(all_test_items)
                if len(all_test_items) < test_count:
                    self.logger.info(f"随机选择了 {len(all_test_items)} 个测试任务（设置数量: {test_count}，实际可用: {total_opus_files}）")
                else:
                    self.logger.info(f"随机选择了 {len(all_test_items)} 个测试任务（设置数量: {test_count}）")
            else:
                # 测试所有文件（统一处理，不再区分类型）
                self.logger.info(f"测试所有文件，共 {total_opus_files} 个文件")
                # 实际测试数 = opus文件总数
                actual_test_count = total_opus_files
                
                for index in sorted(all_indices):
                    audio_file = self.get_audio_file(index)
                    if audio_file:
                        # 从file_list.txt获取文本（更准确）
                        filename = os.path.basename(audio_file)
                        text = text_map.get(filename) if filename in text_map else (inquiries_texts[index - 1] if index <= len(inquiries_texts) else f"测试 #{index}")
                        all_test_items.append({
                            "index": index,
                            "inquiry_file": audio_file,  # 统一使用inquiry_file字段
                            "inquiry_text": text  # 统一使用inquiry_text字段
                        })
                
                # 计算实际会执行的测试数量（每个测试任务中的每个文件类型都会执行一次测试）
                actual_test_count = 0
                for item in all_test_items:
                    if "inquiry_file" in item:
                        actual_test_count += 1
                    if "compare_file" in item:
                        actual_test_count += 1
                    if "order_file" in item or "purchase_file" in item:
                        actual_test_count += 1
                self.logger.info(f"实际会执行 {actual_test_count} 个测试（测试任务数: {len(all_test_items)}）")
            
            # 设置实际测试数（用于进度显示）
            test_state["total"] = actual_test_count
            test_state["total_opus_files"] = total_opus_files  # 保存opus文件总数
            
            # 保存settings到test_state，供报告使用
            if "settings" not in test_state:
                test_state["settings"] = {}
            test_state["settings"]["total_opus_files"] = total_opus_files
            test_state["settings"]["test_count"] = test_count
            
            # 发送测试开始通知（在计算 actual_test_count 之后）
            emit_test_update("test_started", {
                "start_time": test_state["start_time"],
                "total": actual_test_count,  # 实际测试数（设置的测试数或所有文件数）
                "total_opus_files": total_opus_files,  # opus文件总数
                "concurrency_count": total_connections_for_notification
            })
            
            # 单SN并发测试
            from websocket_client import WebSocketClient
            
            try:
                if not test_state["is_running"]:
                    return

                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"开始测试 | SN数量: {len(device_sns)}, 每个SN连接数: {connections_per_sn}, 总并发连接数: {total_connections}, 测试模式: {test_mode}")
                self.logger.info(f"SN列表: {', '.join(device_sns)}")
                self.logger.info(f"{'='*60}")

                # 为每个SN创建多个客户端（如果需要）
                clients = []
                connection_id = 1
                for sn in device_sns:
                    for conn_idx in range(connections_per_sn):
                        clients.append(WebSocketClient(connection_id=connection_id, device_sn=sn))
                        connection_id += 1
                
                self.logger.info(f"共创建 {len(clients)} 个WebSocket客户端")

                # 建立连接并等待鉴权
                async def connect_and_auth(client, sn):
                    connected = await client.connect()
                    if not connected:
                        self.logger.error(f"SN {sn}: 连接失败 (Conn #{client.connection_id})")
                        return False
                    max_wait_server_msg = 3.0
                    initial_wait = 0.2
                    await asyncio.sleep(initial_wait)
                    wait_server_msg_time = 0
                    check_interval = 0.1
                    while wait_server_msg_time < max_wait_server_msg and client.is_connected:
                        if client.auth_received or client.session_id:
                            break
                        await asyncio.sleep(check_interval)
                        wait_server_msg_time += check_interval
                    if client.auth_failed:
                        self.logger.error(f"SN {sn}: 鉴权失败 (Conn #{client.connection_id})")
                        return False
                    self.logger.info(f"SN {sn}: 鉴权成功 (Conn #{client.connection_id})")
                    return True

                # 获取每个客户端对应的SN
                client_sns = []
                for sn in device_sns:
                    client_sns.extend([sn] * connections_per_sn)
                
                connect_results = await asyncio.gather(*(connect_and_auth(c, sn) for c, sn in zip(clients, client_sns)))
                active_clients = [c for c, ok in zip(clients, connect_results) if ok]
                if not active_clients:
                    self.logger.error("所有连接均失败，终止测试")
                    return

                # 创建共享任务队列，所有客户端从队列中取任务
                task_queue = asyncio.Queue()
                for item in all_test_items:
                    await task_queue.put(item)

                async def run_client_tasks(client):
                    """每个客户端独立从队列中取任务，完成一个立即取下一个"""
                    while test_state["is_running"]:
                        try:
                            # 从队列中取任务，如果队列为空则等待最多1秒
                            test_item = await asyncio.wait_for(task_queue.get(), timeout=1.0)
                        except asyncio.TimeoutError:
                            # 队列为空，退出
                            break
                        
                        if not test_state["is_running"]:
                            # 如果测试被停止，将任务放回队列
                            await task_queue.put(test_item)
                            break
                        
                        try:
                            # 统一处理所有测试任务（不再区分类型）
                            if "inquiry_file" in test_item:
                                test_result = await self.test_single_audio(
                                    client, test_item["inquiry_file"], test_item["inquiry_text"],
                                    "inquiry", test_item["index"], concurrency_index=client.connection_id - 1
                                )
                                self.results.append(test_result)
                                test_state["results"].append(test_result)
                                test_state["progress"] = len(test_state["results"])
                                if test_result["success"]:
                                    test_state["summary"]["successful"] += 1
                                else:
                                    test_state["summary"]["failed"] += 1
                                test_state["summary"]["total"] += 1
                                test_state["summary"]["success_rate"] = (
                                    test_state["summary"]["successful"] / test_state["summary"]["total"] * 100
                                    if test_state["summary"]["total"] > 0 else 0
                                )
                                emit_test_update("progress_update", {
                                    "progress": test_state["progress"],
                                    "total": test_state["total"],
                                    "total_opus_files": test_state.get("total_opus_files", 0),
                                    "summary": test_state["summary"]
                                })
                                await asyncio.sleep(0.2)
                            
                            # 标记任务完成
                            task_queue.task_done()
                        except Exception as e:
                            self.logger.error(f"SN {client.device_sn} (Conn #{client.connection_id}) 处理任务时出错: {e}")
                            task_queue.task_done()
                            continue
                    
                    self.logger.info(f"SN {client.device_sn} (Conn #{client.connection_id}): 任务处理完成")

                # 启动所有客户端的任务处理协程
                tasks = [run_client_tasks(client) for client in active_clients]
                
                if tasks:
                    # 等待所有任务完成
                    await asyncio.gather(*tasks)
                    
                    # 等待队列中剩余任务完成（如果有）
                    await task_queue.join()

                # 关闭所有连接
                for c in active_clients:
                    if c.is_connected:
                        await c.close()

                # 测试完成
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"所有测试完成")
                self.logger.info(f"总测试数: {test_state['summary']['total']}")
                self.logger.info(f"成功: {test_state['summary']['successful']}")
                self.logger.info(f"失败: {test_state['summary']['failed']}")
                self.logger.info(f"成功率: {test_state['summary']['success_rate']:.2f}%")
                self.logger.info(f"{'='*60}\n")
                
                test_state["end_time"] = datetime.now().isoformat()
                emit_test_update("test_completed", {
                    "end_time": test_state["end_time"],
                    "summary": test_state["summary"],
                    "results": test_state["results"]
                })
                
            except Exception as e:
                test_state["error"] = str(e)
                test_state["is_running"] = False
                emit_test_update("test_error", {"error": str(e)})
                import traceback
                print(traceback.format_exc())
            finally:
                test_state["is_running"] = False
                
        except Exception as e:
            test_state["error"] = str(e)
            test_state["is_running"] = False
            emit_test_update("test_error", {"error": str(e)})
            import traceback
            print(traceback.format_exc())

def run_test_async():
    """在异步环境中运行测试"""
    global tester_instance
    tester_instance = WebInquiryTester()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tester_instance.run_test())
    loop.close()

@app.route('/')
def index():
    """主页面"""
    return render_template('test_dashboard.html')

@app.route('/opus-management')
def opus_management():
    """Opus文件管理页面"""
    return render_template('opus_management.html')

@app.route('/api/status')
def get_status():
    """获取测试状态"""
    return jsonify(test_state)

@app.route('/api/results')
def get_results():
    """获取测试结果"""
    return jsonify({
        "results": test_state["results"],
        "summary": test_state["summary"]
    })

def generate_test_report(results, summary, start_time, end_time, settings):
    """生成测试报告"""
    import statistics
    
    # 基础统计
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r.get("success", False))
    failed_tests = total_tests - successful_tests
    success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
    
    # 计算测试持续时间
    duration_seconds = 0
    if start_time and end_time:
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration_seconds = (end_dt - start_dt).total_seconds()
        except:
            pass
    
    # 性能指标统计（专业测试角度：精细化拆解各个阶段的延迟）
    # 过滤掉无效值：None、负值、异常大的值
    
    # 1. 音频发送阶段
    send_durations = [r.get("send_duration") for r in results if r.get("send_duration") is not None and r.get("send_duration") >= 0 and r.get("send_duration") <= 60000]
    
    # 2. STT服务延迟（优先使用从最后一帧计算的延迟，纯STT处理时间）
    stt_latencies = []
    stt_latencies_from_first = []
    stt_latencies_from_last = []
    for r in results:
        # 从最后一帧计算的延迟（纯STT处理时间，更准确）
        stt_latency_from_last = r.get("stt_latency_from_last_frame")
        if stt_latency_from_last is not None and 0 <= stt_latency_from_last <= 60000:
            stt_latencies_from_last.append(stt_latency_from_last)
            stt_latencies.append(stt_latency_from_last)  # 优先使用这个
        
        # 从第一帧计算的延迟（包含发送时间）
        stt_latency_from_first = r.get("stt_latency_from_first_frame") or r.get("stt_latency")
        if stt_latency_from_first is not None and 0 <= stt_latency_from_first <= 60000:
            stt_latencies_from_first.append(stt_latency_from_first)
            if stt_latency_from_last is None:  # 如果没有最后一帧的延迟，使用第一帧的
                stt_latencies.append(stt_latency_from_first)
    
    # 3. LLM服务延迟
    llm_latencies = [r.get("llm_latency") for r in results if r.get("llm_latency") is not None and r.get("llm_latency") >= 0 and r.get("llm_latency") <= 60000]
    
    # 4. TTS服务延迟
    tts_latencies = [r.get("tts_latency") for r in results if r.get("tts_latency") is not None and r.get("tts_latency") >= 0 and r.get("tts_latency") <= 10000]
    tts_durations = [r.get("tts_duration") for r in results if r.get("tts_duration") is not None and r.get("tts_duration") >= 0 and r.get("tts_duration") <= 120000]
    
    # 5. 端到端响应时间（多个维度）
    e2e_from_first = [r.get("e2e_from_first_frame") or r.get("e2e_response_time") for r in results if (r.get("e2e_from_first_frame") or r.get("e2e_response_time")) is not None and (r.get("e2e_from_first_frame") or r.get("e2e_response_time")) >= 0 and (r.get("e2e_from_first_frame") or r.get("e2e_response_time")) <= 120000]
    e2e_from_last = [r.get("e2e_from_last_frame") for r in results if r.get("e2e_from_last_frame") is not None and r.get("e2e_from_last_frame") >= 0 and r.get("e2e_from_last_frame") <= 120000]
    e2e_from_stt = [r.get("e2e_from_stt") for r in results if r.get("e2e_from_stt") is not None and r.get("e2e_from_stt") >= 0 and r.get("e2e_from_stt") <= 120000]
    e2e_from_llm = [r.get("e2e_from_llm") for r in results if r.get("e2e_from_llm") is not None and r.get("e2e_from_llm") >= 0 and r.get("e2e_from_llm") <= 120000]
    
    def calc_stats(times):
        if not times:
            return None
        sorted_times = sorted(times)
        return {
            "min": min(times),
            "max": max(times),
            "avg": statistics.mean(times),
            "median": statistics.median(times),
            "p95": sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else None,
            "p99": sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else None,
            "count": len(times)
        }
    
    # 失败原因统计
    failure_reasons = {}
    for r in results:
        if not r.get("success", False):
            reason = r.get("failure_reason", "Unknown")
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    
    # 按测试类型统计（支持三种类型：inquiry、compare、order/purchase）
    inquiry_results = [r for r in results if r.get("type") == "inquiry"]
    compare_results = [r for r in results if r.get("type") == "compare"]
    order_results = [r for r in results if r.get("type") in ["order", "purchase"]]
    
    inquiry_success = sum(1 for r in inquiry_results if r.get("success", False))
    compare_success = sum(1 for r in compare_results if r.get("success", False))
    order_success = sum(1 for r in order_results if r.get("success", False))
    
    # 吞吐量计算（QPS）
    qps = total_tests / duration_seconds if duration_seconds > 0 else 0
    
    # 时间线数据（用于图表）
    timeline_data = []
    for i, r in enumerate(results):
        timeline_data.append({
            "index": i + 1,
            "timestamp": r.get("timestamp"),
            "type": r.get("type"),
            "success": r.get("success", False),
            "e2e_response_time": r.get("e2e_response_time")
        })
    
    # 收集测试环境信息
    from config import Config
    test_environment = {
        "websocket_server": settings.get("websocket_url", Config.WSS_SERVER_HOST if Config.USE_SSL else Config.WS_SERVER_HOST),
        "device_sns": settings.get("device_sns", []),
        "test_count": settings.get("test_count"),
        "total_opus_files": settings.get("total_opus_files", 0),
        "python_version": sys.version.split()[0],
        "platform": sys.platform
    }
    
    # 详细的测试用例列表（每个测试的完整信息）
    test_cases = []
    for i, r in enumerate(results):
        test_case = {
            "test_id": i + 1,
            "timestamp": r.get("timestamp"),
            "type": r.get("type", "unknown"),
            "index": r.get("index", 0),
            "success": r.get("success", False),
            "request_text": r.get("text", ""),
            "stt_text": r.get("stt_text", ""),
            "llm_text": r.get("llm_text", ""),
            "response_text": r.get("response_text", ""),
            "audio_file": r.get("audio_file", ""),
            "connection_id": r.get("connection_id"),
            "device_sn": r.get("device_sn", ""),
            "stt_latency_ms": r.get("stt_latency"),
            "llm_latency_ms": r.get("llm_latency"),
            "tts_latency_ms": r.get("tts_latency"),
            "e2e_response_time_ms": r.get("e2e_response_time"),
            "failure_reason": r.get("failure_reason"),
            "error": r.get("error"),
            "sent_messages": r.get("sent_messages", 0),
            "received_messages": r.get("received_messages", 0),
            "total_sent_bytes": r.get("total_sent_bytes", 0),
            "total_received_bytes": r.get("total_received_bytes", 0)
        }
        test_cases.append(test_case)
    
    report = {
        "test_info": {
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration_seconds,
            "concurrency": settings.get("concurrency", 0),
            "device_count": len(settings.get("device_sns", [])),
            "test_mode": settings.get("test_mode", "normal"),
            "test_count": settings.get("test_count"),
            "total_opus_files": settings.get("total_opus_files", 0)
        },
        "test_environment": test_environment,
        "test_cases": test_cases,  # 详细的测试用例列表
        "summary": {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": round(success_rate, 2),
            "qps": round(qps, 2),
            "inquiry_total": len(inquiry_results),
            "inquiry_success": inquiry_success,
            "inquiry_success_rate": round((inquiry_success / len(inquiry_results) * 100) if inquiry_results else 0, 2),
            "compare_total": len(compare_results),
            "compare_success": compare_success,
            "compare_success_rate": round((compare_success / len(compare_results) * 100) if compare_results else 0, 2),
            "order_total": len(order_results),
            "order_success": order_success,
            "order_success_rate": round((order_success / len(order_results) * 100) if order_results else 0, 2),
            # 兼容旧格式
            "purchase_total": len(order_results),
            "purchase_success": order_success,
            "purchase_success_rate": round((order_success / len(order_results) * 100) if order_results else 0, 2)
        },
        "performance_metrics": {
            # 1. 音频发送阶段
            "send_duration": calc_stats(send_durations),  # 音频发送耗时（从第一帧到最后一帧）
            
            # 2. STT服务延迟
            "stt_latency": calc_stats(stt_latencies),  # STT延迟（优先使用从最后一帧计算的，纯STT处理时间）
            "stt_latency_from_first_frame": calc_stats(stt_latencies_from_first),  # STT延迟（从第一帧发送，包含发送时间）
            "stt_latency_from_last_frame": calc_stats(stt_latencies_from_last),  # STT延迟（从最后一帧发送，纯STT处理时间）
            
            # 3. LLM服务延迟
            "llm_latency": calc_stats(llm_latencies),  # LLM延迟（从STT完成到LLM响应）
            
            # 4. TTS服务延迟
            "tts_latency": calc_stats(tts_latencies),  # TTS启动延迟（从LLM完成到TTS开始）
            "tts_duration": calc_stats(tts_durations),  # TTS持续时间（从TTS开始到TTS结束）
            
            # 5. 端到端响应时间（多个维度）
            "e2e_response_time": calc_stats(e2e_from_first),  # 端到端响应时间（从第一帧发送到TTS结束）
            "e2e_from_first_frame": calc_stats(e2e_from_first),  # 从第一帧发送到TTS结束
            "e2e_from_last_frame": calc_stats(e2e_from_last),  # 从最后一帧发送到TTS结束（不包含发送时间）
            "e2e_from_stt": calc_stats(e2e_from_stt),  # 从STT响应到TTS结束（STT后的完整处理时间）
            "e2e_from_llm": calc_stats(e2e_from_llm)  # 从LLM响应到TTS结束（LLM后的完整处理时间）
        },
        "failure_analysis": {
            "failure_reasons": failure_reasons,
            "failure_rate": round((failed_tests / total_tests * 100) if total_tests > 0 else 0, 2)
        },
        "timeline": timeline_data
    }
    
    return report

@app.route('/api/report')
def get_report():
    """获取测试报告（包含详细统计和指标）"""
    global test_state
    
    results = test_state.get("results", [])
    summary = test_state.get("summary", {})
    start_time = test_state.get("start_time")
    end_time = test_state.get("end_time")
    settings = test_state.get("settings", {})
    
    # 计算详细统计
    report = generate_test_report(results, summary, start_time, end_time, settings)
    
    return jsonify(report)

@app.route('/api/report/pdf')
def export_report_pdf():
    """导出测试报告为PDF"""
    global test_state
    
    results = test_state.get("results", [])
    summary = test_state.get("summary", {})
    start_time = test_state.get("start_time")
    end_time = test_state.get("end_time")
    settings = test_state.get("settings", {})
    
    # 生成报告数据
    report = generate_test_report(results, summary, start_time, end_time, settings)
    
    # 生成PDF
    pdf_buffer = generate_pdf_report(report)
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"测试报告_{timestamp}.pdf"
    
    # 返回PDF文件
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/report/csv')
def export_report_csv():
    """导出测试报告为CSV（专业测试团队使用）"""
    global test_state
    import csv
    
    results = test_state.get("results", [])
    summary = test_state.get("summary", {})
    start_time = test_state.get("start_time")
    end_time = test_state.get("end_time")
    settings = test_state.get("settings", {})
    
    # 生成报告数据
    report = generate_test_report(results, summary, start_time, end_time, settings)
    
    # 创建CSV内容
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 写入报告头部信息
    writer.writerow(["语音对话测试报告 - CSV导出"])
    writer.writerow(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    
    # 测试信息
    test_info = report.get("test_info", {})
    writer.writerow(["测试信息"])
    writer.writerow(["开始时间", test_info.get("start_time", "")])
    writer.writerow(["结束时间", test_info.get("end_time", "")])
    writer.writerow(["持续时间(秒)", test_info.get("duration_seconds", 0)])
    writer.writerow(["并发数", test_info.get("concurrency", 0)])
    writer.writerow(["设备数量", test_info.get("device_count", 0)])
    writer.writerow(["测试模式", test_info.get("test_mode", "normal")])
    writer.writerow(["测试数量", test_info.get("test_count", "全部")])
    writer.writerow(["Opus文件总数", test_info.get("total_opus_files", 0)])
    writer.writerow([])
    
    # 测试环境
    env = report.get("test_environment", {})
    writer.writerow(["测试环境"])
    writer.writerow(["WebSocket服务器", env.get("websocket_server", "")])
    writer.writerow(["设备SN列表", ", ".join(env.get("device_sns", []))])
    writer.writerow(["Python版本", env.get("python_version", "")])
    writer.writerow(["平台", env.get("platform", "")])
    writer.writerow([])
    
    # 总体统计
    summary_data = report.get("summary", {})
    writer.writerow(["总体统计"])
    writer.writerow(["总测试数", summary_data.get("total_tests", 0)])
    writer.writerow(["成功", summary_data.get("successful_tests", 0)])
    writer.writerow(["失败", summary_data.get("failed_tests", 0)])
    writer.writerow(["成功率(%)", summary_data.get("success_rate", 0)])
    writer.writerow(["吞吐量(QPS)", summary_data.get("qps", 0)])
    writer.writerow(["询问测试", f"{summary_data.get('inquiry_success', 0)}/{summary_data.get('inquiry_total', 0)} ({summary_data.get('inquiry_success_rate', 0)}%)"])
    writer.writerow(["对比测试", f"{summary_data.get('compare_success', 0)}/{summary_data.get('compare_total', 0)} ({summary_data.get('compare_success_rate', 0)}%)"])
    writer.writerow(["下单测试", f"{summary_data.get('order_success', 0)}/{summary_data.get('order_total', 0)} ({summary_data.get('order_success_rate', 0)}%)"])
    writer.writerow([])
    
    # 性能指标
    metrics = report.get("performance_metrics", {})
    writer.writerow(["性能指标"])
    writer.writerow(["指标", "平均值(ms)", "中位数(ms)", "P95(ms)", "P99(ms)", "最小值(ms)", "最大值(ms)", "样本数"])
    for key, name in [("stt_latency", "STT服务延迟"), ("llm_latency", "LLM服务延迟"), 
                      ("tts_latency", "TTS服务延迟"), ("e2e_response_time", "端到端响应时间")]:
        metric = metrics.get(key)
        if metric and metric.get("count", 0) > 0:
            writer.writerow([
                name,
                round(metric.get("avg", 0), 2) if metric.get("avg") else "",
                round(metric.get("median", 0), 2) if metric.get("median") else "",
                round(metric.get("p95", 0), 2) if metric.get("p95") else "",
                round(metric.get("p99", 0), 2) if metric.get("p99") else "",
                round(metric.get("min", 0), 2) if metric.get("min") else "",
                round(metric.get("max", 0), 2) if metric.get("max") else "",
                metric.get("count", 0)
            ])
    writer.writerow([])
    
    # 失败分析
    failure_analysis = report.get("failure_analysis", {})
    failure_reasons = failure_analysis.get("failure_reasons", {})
    if failure_reasons:
        writer.writerow(["失败分析"])
        writer.writerow(["失败原因", "数量", "占比(%)"])
        total_failures = sum(failure_reasons.values())
        for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_failures * 100) if total_failures > 0 else 0
            writer.writerow([reason, count, round(percentage, 2)])
        writer.writerow([])
    
    # 详细测试用例列表
    test_cases = report.get("test_cases", [])
    writer.writerow(["详细测试用例列表"])
    writer.writerow([
        "测试ID", "时间戳", "类型", "索引", "状态", "请求文本", "STT文本", "LLM文本",
        "音频文件", "连接ID", "设备SN", "STT延迟(ms)", "LLM延迟(ms)", "TTS延迟(ms)",
        "端到端响应时间(ms)", "失败原因", "错误信息", "发送消息数", "接收消息数",
        "发送字节数", "接收字节数"
    ])
    
    for tc in test_cases:
        writer.writerow([
            tc.get("test_id", ""),
            tc.get("timestamp", ""),
            tc.get("type", ""),
            tc.get("index", ""),
            "成功" if tc.get("success") else "失败",
            tc.get("request_text", "")[:100],  # 限制长度
            tc.get("stt_text", "")[:100],
            tc.get("llm_text", "")[:200],
            tc.get("audio_file", ""),
            tc.get("connection_id", ""),
            tc.get("device_sn", ""),
            round(tc.get("stt_latency_ms", 0), 2) if tc.get("stt_latency_ms") else "",
            round(tc.get("llm_latency_ms", 0), 2) if tc.get("llm_latency_ms") else "",
            round(tc.get("tts_latency_ms", 0), 2) if tc.get("tts_latency_ms") else "",
            round(tc.get("e2e_response_time_ms", 0), 2) if tc.get("e2e_response_time_ms") else "",
            tc.get("failure_reason", ""),
            tc.get("error", ""),
            tc.get("sent_messages", 0),
            tc.get("received_messages", 0),
            tc.get("total_sent_bytes", 0),
            tc.get("total_received_bytes", 0)
        ])
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"测试报告_{timestamp}.csv"
    
    # 返回CSV文件
    output.seek(0)
    csv_bytes = output.getvalue().encode('utf-8-sig')  # 使用UTF-8 BOM以便Excel正确显示中文
    csv_buffer = io.BytesIO(csv_bytes)
    
    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/report/json')
def export_report_json():
    """导出测试报告为JSON（专业测试团队使用）"""
    global test_state
    
    results = test_state.get("results", [])
    summary = test_state.get("summary", {})
    start_time = test_state.get("start_time")
    end_time = test_state.get("end_time")
    settings = test_state.get("settings", {})
    
    # 生成报告数据
    report = generate_test_report(results, summary, start_time, end_time, settings)
    
    # 添加导出元数据
    report["export_info"] = {
        "export_time": datetime.now().isoformat(),
        "export_format": "JSON",
        "version": "1.0"
    }
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"测试报告_{timestamp}.json"
    
    # 返回JSON文件
    json_str = json.dumps(report, ensure_ascii=False, indent=2)
    json_bytes = json_str.encode('utf-8')
    json_buffer = io.BytesIO(json_bytes)
    
    return send_file(
        json_buffer,
        mimetype='application/json',
        as_attachment=True,
        download_name=filename
    )

def generate_pdf_report(report):
    """生成PDF报告"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    story = []
    
    # 注册中文字体
    try:
        # Windows系统字体路径
        font_paths = [
            'C:/Windows/Fonts/simsun.ttc',  # 宋体
            'C:/Windows/Fonts/simhei.ttf',   # 黑体
            'C:/Windows/Fonts/msyh.ttc',     # 微软雅黑
            'C:/Windows/Fonts/simkai.ttf',   # 楷体
        ]
        
        chinese_font_name = 'ChineseFont'
        chinese_font_bold_name = 'ChineseFontBold'
        font_registered = False
        
        # 尝试注册宋体（常规）
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    if 'simsun' in font_path.lower() or 'msyh' in font_path.lower():
                        pdfmetrics.registerFont(TTFont(chinese_font_name, font_path, subfontIndex=0))
                        pdfmetrics.registerFont(TTFont(chinese_font_bold_name, font_path, subfontIndex=0))
                        font_registered = True
                        break
                except:
                    continue
        
        # 如果Windows字体不可用，尝试使用reportlab内置字体（不支持中文，但不会报错）
        if not font_registered:
            chinese_font_name = 'Helvetica'
            chinese_font_bold_name = 'Helvetica-Bold'
    except Exception as e:
        # 如果字体注册失败，使用默认字体
        print(f"Warning: Failed to register Chinese font: {e}")
        chinese_font_name = 'Helvetica'
        chinese_font_bold_name = 'Helvetica-Bold'
    
    # 样式
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=chinese_font_bold_name,
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=chinese_font_bold_name,
        fontSize=16,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=12,
        spaceBefore=20
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=chinese_font_name,
        fontSize=10
    )
    
    # 标题
    story.append(Paragraph("语音对话测试报告", title_style))
    story.append(Spacer(1, 10*mm))
    
    # 测试信息
    story.append(Paragraph("测试信息", heading_style))
    test_info = report.get("test_info", {})
    info_data = [
        ['开始时间', format_pdf_datetime(test_info.get("start_time"))],
        ['结束时间', format_pdf_datetime(test_info.get("end_time"))],
        ['持续时间', format_pdf_duration(test_info.get("duration_seconds", 0))],
        ['并发数', str(test_info.get("concurrency", 0))],
        ['设备数量', str(test_info.get("device_count", 0))],
        ['测试模式', '急速模式' if test_info.get("test_mode") == 'fast' else '正常模式'],
        ['测试数量', str(test_info.get("test_count", "全部"))],
        ['Opus文件总数', str(test_info.get("total_opus_files", 0))]
    ]
    
    # 测试环境信息
    test_environment = report.get("test_environment", {})
    if test_environment:
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph("测试环境", heading_style))
        env_data = [
            ['WebSocket服务器', test_environment.get("websocket_server", "")],
            ['设备SN列表', ", ".join(test_environment.get("device_sns", []))],
            ['Python版本', test_environment.get("python_version", "")],
            ['运行平台', test_environment.get("platform", "")]
        ]
        env_table = Table(env_data, colWidths=[40*mm, 120*mm])
        env_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), chinese_font_bold_name),
            ('FONTNAME', (1, 0), (1, -1), chinese_font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        story.append(env_table)
    info_table = Table(info_data, colWidths=[40*mm, 120*mm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), chinese_font_bold_name),
        ('FONTNAME', (1, 0), (1, -1), chinese_font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10*mm))
    
    # 总体统计
    story.append(Paragraph("总体统计", heading_style))
    summary = report.get("summary", {})
    stats_data = [
        ['指标', '数值'],
        ['总测试数', str(summary.get("total_tests", 0))],
        ['成功', f"{summary.get('successful_tests', 0)} ({summary.get('success_rate', 0)}%)"],
        ['失败', f"{summary.get('failed_tests', 0)} ({100 - summary.get('success_rate', 0):.2f}%)"],
        ['吞吐量 (QPS)', str(summary.get("qps", 0))],
        ['询问测试', f"{summary.get('inquiry_success', 0)}/{summary.get('inquiry_total', 0)} ({summary.get('inquiry_success_rate', 0)}%)"],
        ['对比测试', f"{summary.get('compare_success', 0)}/{summary.get('compare_total', 0)} ({summary.get('compare_success_rate', 0)}%)"],
        ['购买测试', f"{summary.get('order_success', summary.get('purchase_success', 0))}/{summary.get('order_total', summary.get('purchase_total', 0))} ({summary.get('order_success_rate', summary.get('purchase_success_rate', 0))}%)"]
    ]
    stats_table = Table(stats_data, colWidths=[60*mm, 100*mm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), chinese_font_bold_name),
        ('FONTNAME', (0, 1), (-1, -1), chinese_font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 10*mm))
    
    # 性能指标（精细化拆解）
    story.append(Paragraph("性能指标", heading_style))
    metrics = report.get("performance_metrics", {})
    
    # 按阶段分组显示指标
    metric_groups = {
        '音频发送阶段': {
            'send_duration': '音频发送耗时（从第一帧到最后一帧）'
        },
        'STT服务延迟': {
            'stt_latency_from_last_frame': 'STT延迟（从最后一帧发送，纯STT处理时间）',
            'stt_latency_from_first_frame': 'STT延迟（从第一帧发送，包含发送时间）',
            'stt_latency': 'STT延迟（综合，优先使用从最后一帧）'
        },
        'LLM服务延迟': {
            'llm_latency': 'LLM延迟（从STT完成到LLM响应）'
        },
        'TTS服务延迟': {
            'tts_latency': 'TTS启动延迟（从LLM完成到TTS开始）',
            'tts_duration': 'TTS持续时间（从TTS开始到TTS结束）'
        },
        '端到端响应时间': {
            'e2e_from_first_frame': '端到端时间（从第一帧发送到TTS结束）',
            'e2e_from_last_frame': '端到端时间（从最后一帧发送到TTS结束）',
            'e2e_from_stt': '端到端时间（从STT响应到TTS结束）',
            'e2e_from_llm': '端到端时间（从LLM响应到TTS结束）',
            'e2e_response_time': '端到端时间（综合，从第一帧发送）'
        }
    }
    
    # 按阶段分组显示
    for group_name, metric_dict in metric_groups.items():
        group_metrics = []
        for key, name in metric_dict.items():
            metric = metrics.get(key)
            if metric and metric.get("count", 0) > 0:
                group_metrics.append((key, name, metric))
        
        if group_metrics:
            story.append(Paragraph(f"<b>{group_name}</b>", heading_style))
            for key, name, metric in group_metrics:
                story.append(Paragraph(f"  {name}", normal_style))
                metric_data = [
                    ['指标', '数值'],
                    ['平均值', format_pdf_time(metric.get("avg"))],
                    ['中位数', format_pdf_time(metric.get("median"))],
                    ['P95', format_pdf_time(metric.get("p95"))],
                    ['P99', format_pdf_time(metric.get("p99"))],
                    ['最小值', format_pdf_time(metric.get("min"))],
                    ['最大值', format_pdf_time(metric.get("max"))],
                    ['样本数', str(metric.get("count", 0))]
                ]
            metric_table = Table(metric_data, colWidths=[40*mm, 120*mm])
            metric_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), chinese_font_bold_name),
                ('FONTNAME', (0, 1), (-1, -1), chinese_font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ]))
            story.append(metric_table)
            story.append(Spacer(1, 8*mm))
    
    # 失败分析
    failure_analysis = report.get("failure_analysis", {})
    failure_reasons = failure_analysis.get("failure_reasons", {})
    if failure_reasons:
        story.append(Paragraph("失败分析", heading_style))
        failure_data = [['失败原因', '数量', '占比']]
        total_failures = sum(failure_reasons.values())
        for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_failures * 100) if total_failures > 0 else 0
            failure_data.append([reason, str(count), f"{percentage:.2f}%"])
        
        failure_table = Table(failure_data, colWidths=[100*mm, 30*mm, 30*mm])
        failure_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ef4444')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (2, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), chinese_font_bold_name),
            ('FONTNAME', (0, 1), (-1, -1), chinese_font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fef2f2')]),
        ]))
        story.append(failure_table)
        story.append(Spacer(1, 10*mm))
    
    # 测试用例摘要（显示前20个失败的测试用例）
    test_cases = report.get("test_cases", [])
    failed_cases = [tc for tc in test_cases if not tc.get("success", False)]
    if failed_cases:
        story.append(Paragraph("失败测试用例详情（前20个）", heading_style))
        case_data = [['测试ID', '类型', '请求文本', '失败原因', '响应时间(ms)']]
        for tc in failed_cases[:20]:  # 只显示前20个
            request_text = tc.get("request_text", "")[:30] + "..." if len(tc.get("request_text", "")) > 30 else tc.get("request_text", "")
            case_data.append([
                str(tc.get("test_id", "")),
                tc.get("type", ""),
                request_text,
                tc.get("failure_reason", "Unknown")[:40],
                str(round(tc.get("e2e_response_time_ms", 0), 2)) if tc.get("e2e_response_time_ms") else "N/A"
            ])
        
        case_table = Table(case_data, colWidths=[20*mm, 20*mm, 50*mm, 50*mm, 20*mm])
        case_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ef4444')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), chinese_font_bold_name),
            ('FONTNAME', (0, 1), (-1, -1), chinese_font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fef2f2')]),
        ]))
        story.append(case_table)
        if len(failed_cases) > 20:
            story.append(Spacer(1, 5*mm))
            story.append(Paragraph(f"注：共有 {len(failed_cases)} 个失败用例，此处仅显示前20个。完整列表请查看CSV或JSON导出。", normal_style))
        story.append(Spacer(1, 10*mm))
    
    # 生成PDF
    doc.build(story)
    return buffer

def format_pdf_datetime(iso_string):
    """格式化日期时间用于PDF"""
    if not iso_string:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return iso_string

def format_pdf_duration(seconds):
    """格式化持续时间用于PDF"""
    if not seconds or seconds <= 0:
        return 'N/A'
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}小时 {minutes}分钟 {secs}秒"
    elif minutes > 0:
        return f"{minutes}分钟 {secs}秒"
    else:
        return f"{secs}秒"

def format_pdf_time(ms):
    """格式化时间（毫秒）用于PDF"""
    if ms is None or ms < 0:
        return 'N/A'
    if ms < 1000:
        return f"{ms:.0f} ms"
    elif ms < 60000:
        return f"{ms/1000:.2f} s"
    elif ms < 3600000:
        minutes = int(ms // 60000)
        seconds = (ms % 60000) / 1000
        return f"{minutes}分 {seconds:.1f}秒"
    else:
        hours = int(ms // 3600000)
        minutes = int((ms % 3600000) // 60000)
        return f"{hours}小时 {minutes}分钟"

@app.route('/api/generate-tts', methods=['POST'])
def generate_tts():
    """生成TTS音频文件（单语音测试模式）"""
    import subprocess
    import tempfile
    import shutil
    
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({"error": "请输入要测试的文字"}), 400
    
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix='tts_test_')
        temp_pcm = os.path.join(temp_dir, 'temp_audio.pcm')
        temp_opus = os.path.join(temp_dir, 'temp_audio.opus')
        
        # 调用generate_tts_audio.py生成音频
        from generate_tts_audio import synthesize_speech
        
        # 异步生成PCM
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(synthesize_speech(text, temp_pcm, audio_format="raw"))
        loop.close()
        
        if not result.get("success", False):
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"error": f"TTS生成失败: {result.get('error', 'Unknown error')}"}), 500
        
        # 使用ffmpeg转换为Opus
        try:
            subprocess.run([
                "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                "-i", temp_pcm, "-c:a", "libopus", "-b:a", "32k", "-frame_duration", "60",
                temp_opus
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"error": f"音频转换失败: {str(e)}"}), 500
        
        # 读取opus文件内容
        with open(temp_opus, 'rb') as f:
            opus_data = f.read()
        
        # 清理临时文件
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # 保存到临时文件供测试使用
        test_audio_dir = os.path.join(os.path.dirname(__file__), "audio", "temp_test")
        os.makedirs(test_audio_dir, exist_ok=True)
        import time as time_module
        test_audio_file = os.path.join(test_audio_dir, f"single_test_{int(time_module.time() * 1000)}.opus")
        
        with open(test_audio_file, 'wb') as f:
            f.write(opus_data)
        
        return jsonify({
            "success": True,
            "audio_file": test_audio_file,
            "text": text,
            "size": len(opus_data)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成TTS失败: {str(e)}"}), 500

@app.route('/api/single-test', methods=['POST'])
def single_test():
    """执行单语音测试"""
    global test_state
    
    if test_state["is_running"]:
        return jsonify({"error": "测试正在进行中，请先停止当前测试"}), 400
    
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({"error": "请输入要测试的文字"}), 400
    
    # 获取测试配置（多层fallback）
    device_sns = data.get('device_sns', [])
    if not device_sns:
        # 从test_state获取默认配置
        settings = test_state.get("settings", {})
        device_sns = settings.get("device_sns", [])
    
    # 如果还是没有，使用Config中的默认值（单设备SN）
    if not device_sns:
        from config import Config
        device_sns = [Config.DEVICE_SN]  # 使用Config中的默认设备SN
    
    # 确保至少有一个设备SN
    if not device_sns:
        return jsonify({"error": "请先配置设备SN（可在设置中配置，或使用config.py中的默认值）"}), 400
    
    ws_url = data.get('ws_url', '')
    test_mode = data.get('test_mode', 'normal')
    
    # 在新线程中执行测试
    def run_single_test():
        global test_state
        temp_dir = None
        try:
            # 生成TTS音频
            from generate_tts_audio import synthesize_speech
            import subprocess
            import tempfile
            import shutil
            
            temp_dir = tempfile.mkdtemp(prefix='tts_test_')
            temp_pcm = os.path.join(temp_dir, 'temp_audio.pcm')
            temp_opus = os.path.join(temp_dir, 'temp_audio.opus')
            
            socketio.emit('single_test_start', {
                "text": text,
                "status": "正在生成TTS音频..."
            })
            
            # 异步生成PCM
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(synthesize_speech(text, temp_pcm, audio_format="raw"))
            loop.close()
            
            if not result.get("success", False):
                socketio.emit('single_test_error', {"error": f"TTS生成失败: {result.get('error', 'Unknown error')}"})
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                return
            
            # 转换为Opus
            socketio.emit('single_test_start', {
                "text": text,
                "status": "正在转换音频格式..."
            })
            
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                    "-i", temp_pcm, "-c:a", "libopus", "-b:a", "32k", "-frame_duration", "60",
                    temp_opus
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                socketio.emit('single_test_error', {"error": f"音频转换失败: {str(e)}"})
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                return
            
            # 执行测试
            test_state["is_running"] = True
            test_state["start_time"] = datetime.now().isoformat()
            
            socketio.emit('single_test_start', {
                "text": text,
                "status": "TTS生成完成，正在执行测试..."
            })
            
            # 使用第一个设备SN进行测试
            device_sn = device_sns[0] if device_sns else None
            
            # 如果提供了WebSocket URL，设置到Config
            if ws_url:
                from urllib.parse import urlparse
                from config import Config as ConfigModule  # 在函数内部重新导入
                if ws_url.startswith('wss://'):
                    parsed = urlparse(ws_url.replace('wss://', 'http://'))
                    host_with_port = f"{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
                    ConfigModule.WSS_SERVER_HOST = f"wss://{host_with_port}"
                    ConfigModule.WS_SERVER_HOST = f"ws://{host_with_port}"
                    ConfigModule.USE_SSL = True
                else:
                    parsed = urlparse(ws_url.replace('ws://', 'http://'))
                    host_with_port = f"{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
                    ConfigModule.WS_SERVER_HOST = f"ws://{host_with_port}"
                    ConfigModule.WSS_SERVER_HOST = f"wss://{host_with_port}"
                    ConfigModule.USE_SSL = False
            
            # 执行测试
            from websocket_client import WebSocketClient
            
            # 使用WebInquiryTester以支持实时更新
            tester = WebInquiryTester()
            client = WebSocketClient(connection_id=1, device_sn=device_sn)
            
            # 建立WebSocket连接
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def run_test_with_connection():
                # 先建立连接
                connected = await client.connect()
                if not connected:
                    socketio.emit('single_test_error', {"error": "WebSocket连接失败"})
                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    return None
                
                # 等待一小段时间让服务器响应（鉴权）
                await asyncio.sleep(0.2)
                wait_server_msg_time = 0
                max_wait_server_msg = 3.0
                check_interval = 0.1
                while wait_server_msg_time < max_wait_server_msg and client.is_connected:
                    if client.auth_received or client.session_id:
                        break
                    await asyncio.sleep(check_interval)
                    wait_server_msg_time += check_interval
                
                if client.auth_failed:
                    socketio.emit('single_test_error', {"error": "WebSocket鉴权失败"})
                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    return None
                
                # 为单语音测试创建实时更新回调
                client._tts_sentence_callback = tester._create_tts_sentence_callback(
                    client, 1, "single", text, is_single_test=True
                )
                
                # 执行单次测试（传入is_single_test=True，但回调已设置，不会覆盖）
                test_result = await tester.test_single_audio(
                    client, temp_opus, text, "single", 1, is_single_test=True
                )
                
                # 关闭连接
                if client.is_connected:
                    await client.close()
                
                return test_result
            
            # 执行测试
            test_result = loop.run_until_complete(run_test_with_connection())
            loop.close()
            
            if test_result is None:
                return
            
            # 保存Opus文件和文字到记录中
            try:
                # 获取下一个可用的文件编号
                import glob
                import re
                pattern = os.path.join(AUDIO_DIR, "audio_*.opus")
                existing_files = glob.glob(pattern)
                current_index = 1
                if existing_files:
                    indices = []
                    for file in existing_files:
                        basename = os.path.basename(file)
                        match = re.match(r'audio_(\d+)\.opus', basename)
                        if match:
                            indices.append(int(match.group(1)))
                    if indices:
                        current_index = max(indices) + 1
                
                # 检查文件是否已存在，如果存在则使用下一个索引
                while True:
                    filename = f"audio_{current_index:03d}.opus"
                    output_file = os.path.join(AUDIO_DIR, filename)
                    if os.path.exists(output_file):
                        current_index += 1
                    else:
                        break
                
                # 复制临时Opus文件到目标位置
                if os.path.exists(temp_opus):
                    shutil.copy2(temp_opus, output_file)
                    
                    # 更新file_list.txt
                    # 先读取现有的file_list.txt，保留已存在文件的文本内容
                    existing_text_map = {}
                    if os.path.exists(FILE_LIST_TXT):
                        with open(FILE_LIST_TXT, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if not line or line in ["Inquiry Files:", "Compare Files:", "Order Files:"]:
                                    continue
                                # 解析格式：001: filename.opus - 文本内容
                                match = re.match(r'(\d+):\s+(\w+_\d+\.opus)\s+-\s*(.+)', line)
                                if match:
                                    existing_filename = match.group(2)
                                    existing_text = match.group(3)
                                    if existing_text:  # 只保存非空文本
                                        existing_text_map[existing_filename] = existing_text
                    
                    # 添加新文件的文本内容
                    existing_text_map[filename] = text
                    
                    # 重新扫描所有文件
                    inquiries, compares, orders = scan_opus_files()
                    
                    # 用existing_text_map中的文本内容覆盖扫描结果
                    for file_list in [inquiries, compares, orders]:
                        for file_info in file_list:
                            if file_info["filename"] in existing_text_map:
                                file_info["text"] = existing_text_map[file_info["filename"]]
                    
                    # 确保新文件在列表中
                    found = False
                    for file_list in [inquiries, compares, orders]:
                        if any(f["filename"] == filename for f in file_list):
                            # 确保文本内容正确
                            for f in file_list:
                                if f["filename"] == filename:
                                    f["text"] = text
                            found = True
                            break
                    
                    # 如果不在任何列表中，添加到inquiries
                    if not found:
                        file_stat = os.stat(output_file)
                        inquiries.append({
                            "index": f"{current_index:03d}",
                            "filename": filename,
                            "text": text,
                            "file_size": file_stat.st_size,
                            "created_time": datetime.fromtimestamp(file_stat.st_ctime).isoformat()
                        })
                    
                    # 生成新的file_list.txt
                    from generate_batch_tts import generate_file_list
                    generate_file_list(
                        [(int(f["index"]), f["filename"], f["text"]) for f in inquiries],
                        [(int(f["index"]), f["filename"], f["text"]) for f in compares],
                        [(int(f["index"]), f["filename"], f["text"]) for f in orders],
                        FILE_LIST_TXT
                    )
                    
                    socketio.emit('single_test_saved', {
                        "filename": filename,
                        "text": text,
                        "message": f"已保存到记录：{filename}"
                    })
            except Exception as e:
                import traceback
                traceback.print_exc()
                # 保存失败不影响测试结果，只记录错误
                print(f"保存Opus文件失败: {e}")
            
            # 清理临时文件
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            # 发送测试结果
            test_state["end_time"] = datetime.now().isoformat()
            test_state["is_running"] = False
            
            socketio.emit('single_test_complete', {
                "result": test_result,
                "text": text
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            test_state["is_running"] = False
            socketio.emit('single_test_error', {"error": str(e)})
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
    
    test_thread = threading.Thread(target=run_single_test, daemon=True)
    test_thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/start', methods=['POST'])
def start_test():
    """开始测试"""
    global test_state, test_thread
    
    if test_state["is_running"]:
        return jsonify({"error": "测试正在进行中"}), 400
    
    # 获取前端传来的设置
    data = request.get_json() or {}
    concurrency = data.get('concurrency', 10)
    device_sns = data.get('device_sns', [])
    test_mode = data.get('test_mode', 'normal')
    ws_url = data.get('ws_url', '')
    
    # 验证设置
    if not device_sns or len(device_sns) == 0:
        return jsonify({"error": "请至少设置一个设备SN"}), 400
    
    if concurrency < 1 or concurrency > 100:
        return jsonify({"error": "并发数必须在1-100之间"}), 400
    
    if len(device_sns) > concurrency:
        return jsonify({"error": f"设备SN数量({len(device_sns)})不能超过并发数({concurrency})"}), 400
    
    if test_mode not in ['normal', 'fast']:
        return jsonify({"error": "测试模式无效，必须是 'normal' 或 'fast'"}), 400
    
    # 验证WebSocket URL（如果提供了）
    if ws_url and not (ws_url.startswith('ws://') or ws_url.startswith('wss://')):
        return jsonify({"error": "WebSocket地址格式不正确，应以 ws:// 或 wss:// 开头"}), 400
    
    # 如果提供了WebSocket URL，设置到Config
    if ws_url:
        from config import Config
        from urllib.parse import urlparse
        # 解析URL，判断是WS还是WSS
        # 处理ws://和wss://协议
        if ws_url.startswith('wss://'):
            parsed = urlparse(ws_url.replace('wss://', 'http://'))
            host_with_port = f"{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
            Config.WSS_SERVER_HOST = f"wss://{host_with_port}"
            Config.WS_SERVER_HOST = f"ws://{host_with_port}"
            Config.USE_SSL = True
        else:
            parsed = urlparse(ws_url.replace('ws://', 'http://'))
            host_with_port = f"{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
            Config.WS_SERVER_HOST = f"ws://{host_with_port}"
            Config.WSS_SERVER_HOST = f"wss://{host_with_port}"
            Config.USE_SSL = False
        print(f"WebSocket URL已设置为: {Config.WSS_SERVER_HOST if Config.USE_SSL else Config.WS_SERVER_HOST} (USE_SSL={Config.USE_SSL})")
    
    # 获取测试数量（可选）
    test_count = data.get("test_count")
    if test_count:
        try:
            test_count = int(test_count)
            if test_count < 1:
                test_count = None
        except (ValueError, TypeError):
            test_count = None
    
    # 保存设置到全局变量，供测试使用
    test_state["settings"] = {
        "concurrency": concurrency,
        "device_sns": device_sns,
        "test_mode": test_mode,
        "ws_url": ws_url,
        "test_count": test_count
    }
    
    # 重置状态
    test_state["is_running"] = True
    test_state["progress"] = 0
    test_state["results"] = []
    test_state["error"] = None
    
    # 在新线程中运行测试
    test_thread = threading.Thread(target=run_test_async, daemon=True)
    test_thread.start()
    
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_test():
    """停止测试"""
    global test_state
    test_state["is_running"] = False
    return jsonify({"status": "stopped"})

# ==================== Opus文件管理API ====================

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio", "inquiries")
INQUIRIES_TXT = os.path.join(AUDIO_DIR, "inquiries.txt")
COMPARES_TXT = os.path.join(AUDIO_DIR, "compares.txt")
ORDERS_TXT = os.path.join(AUDIO_DIR, "orders.txt")
FILE_LIST_TXT = os.path.join(AUDIO_DIR, "file_list.txt")

def get_next_index(file_type: str) -> int:
    """获取下一个可用的文件编号"""
    import glob
    import re
    
    pattern = os.path.join(AUDIO_DIR, f"{file_type}_*.opus")
    existing_files = glob.glob(pattern)
    if not existing_files:
        return 1
    
    indices = []
    for file in existing_files:
        basename = os.path.basename(file)
        match = re.match(rf"{file_type}_(\d+)\.opus", basename)
        if match:
            indices.append(int(match.group(1)))
    
    return max(indices) + 1 if indices else 1

def scan_opus_files():
    """扫描所有Opus文件并返回列表（统一使用audio_前缀，不再区分类型）"""
    import glob
    import re
    from datetime import datetime
    
    inquiries = []  # 统一使用inquiries存储所有文件（保持兼容性）
    compares = []  # 保持为空，不再使用
    orders = []  # 保持为空，不再使用
    
    # 优先从file_list.txt读取文本映射（最准确）
    text_map = {}
    if os.path.exists(FILE_LIST_TXT):
        with open(FILE_LIST_TXT, 'r', encoding='utf-8') as f:
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
    
    # 统一扫描所有audio_前缀的文件
    pattern = os.path.join(AUDIO_DIR, "audio_*.opus")
    files = sorted(glob.glob(pattern))
    
    for file_path in files:
        basename = os.path.basename(file_path)
        # 匹配audio_XXX.opus格式
        match = re.match(r'audio_(\d+)\.opus', basename)
        if match:
            index = match.group(1)
            file_stat = os.stat(file_path)
            
            file_info = {
                "index": index,
                "filename": basename,
                "text": text_map.get(basename, ""),
                "file_size": file_stat.st_size,
                "created_time": datetime.fromtimestamp(file_stat.st_ctime).isoformat()
            }
            
            # 统一存储到inquiries（保持兼容性）
            inquiries.append(file_info)
    
    return inquiries, compares, orders

@app.route('/api/opus/list')
def get_opus_list():
    """获取Opus文件列表（统一管理，不区分类型）"""
    try:
        inquiries, compares, orders = scan_opus_files()
        # 合并所有文件，按文件名排序
        all_files = inquiries + compares + orders
        # 按文件名排序（自然排序）
        import re
        def natural_sort_key(filename):
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else 0
        
        all_files.sort(key=lambda x: natural_sort_key(x['filename']))
        
        return jsonify({
            "files": all_files,
            "total": len(all_files)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/opus/delete', methods=['DELETE'])
def delete_opus_file():
    """删除Opus文件（统一管理，不区分类型）"""
    try:
        data = request.get_json() or {}
        filename = data.get('filename')
        
        if not filename:
            return jsonify({"error": "缺少必要参数"}), 400
        
        file_path = os.path.join(AUDIO_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "文件不存在"}), 404
        
        # 删除文件
        os.remove(file_path)
        
        # 尝试从对应的文本文件中删除（如果存在）
        import re
        # 检测文件类型
        match = re.match(r'(\w+)_(\d+)\.opus', filename)
        if match:
            file_type = match.group(1)
            txt_files = {
                "inquiry": INQUIRIES_TXT,
                "compare": COMPARES_TXT,
                "order": ORDERS_TXT
            }
            
            txt_file = txt_files.get(file_type)
            if txt_file and os.path.exists(txt_file):
                # 读取所有行
                with open(txt_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 找到要删除的行（通过文件名中的索引）
                index_to_remove = int(match.group(2)) - 1  # 转换为0-based索引
                if 0 <= index_to_remove < len(lines):
                    lines.pop(index_to_remove)
                    
                    # 写回文件
                    with open(txt_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
        
        # 重新生成file_list.txt
        inquiries, compares, orders = scan_opus_files()
        from generate_batch_tts import generate_file_list
        generate_file_list(
            [(int(f["index"]), f["filename"], f["text"]) for f in inquiries],
            [(int(f["index"]), f["filename"], f["text"]) for f in compares],
            [(int(f["index"]), f["filename"], f["text"]) for f in orders],
            FILE_LIST_TXT
        )
        
        return jsonify({"success": True, "message": "文件已删除"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/opus/upload', methods=['POST'])
def upload_text_file():
    """上传文本文件或直接输入文本生成Opus文件（统一管理，不区分类型）"""
    try:
        texts = []
        
        # 检查是文件上传还是JSON文本输入
        if request.content_type and 'application/json' in request.content_type:
            # JSON格式：直接输入文本
            data = request.get_json() or {}
            texts_list = data.get('texts', [])
            if isinstance(texts_list, list):
                texts = [line.strip() for line in texts_list if line.strip()]
            elif isinstance(texts_list, str):
                # 如果是字符串，按换行分割
                texts = [line.strip() for line in texts_list.split('\n') if line.strip()]
        elif 'file' in request.files:
            # 文件上传
            file = request.files['file']
            
            if file.filename == '':
                return jsonify({"error": "文件名为空"}), 400
            
            # 读取文本文件内容
            for line in file:
                line = line.decode('utf-8').strip()
                if line and not line.startswith('---'):
                    texts.append(line)
        else:
            return jsonify({"error": "请上传文件或输入文本"}), 400
        
        if not texts:
            return jsonify({"error": "文本内容为空"}), 400
        
        # 生成Opus文件
        from generate_tts_audio import synthesize_speech
        import subprocess
        import tempfile
        
        generated_files = []
        # 统一管理，不再区分类型，不追加到文本文件
        
        # 在后台线程中异步生成音频文件（避免请求超时）
        def generate_files_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def generate_files():
                result_files = []
                # 获取所有现有文件的最大编号（不区分类型）
                import glob
                import re
                
                # 扫描所有audio_前缀的opus文件，找到最大编号
                pattern = os.path.join(AUDIO_DIR, "audio_*.opus")
                existing_files = glob.glob(pattern)
                max_index = 0
                
                for file_path in existing_files:
                    basename = os.path.basename(file_path)
                    # 只匹配audio_前缀的文件
                    match = re.match(r'audio_(\d+)\.opus', basename)
                    if match:
                        index = int(match.group(1))
                        if index > max_index:
                            max_index = index
                
                current_index = max_index + 1
                file_type = "audio"  # 统一使用audio前缀
                
                for idx, text in enumerate(texts):
                    # 检查文件是否已存在，如果存在则使用下一个索引
                    while True:
                        filename = f"{file_type}_{current_index:03d}.opus"
                        output_file = os.path.join(AUDIO_DIR, filename)
                        
                        if os.path.exists(output_file):
                            # 文件已存在，使用下一个索引
                            current_index += 1
                            print(f"File {filename} already exists, using next index: {current_index:03d}")
                        else:
                            # 文件不存在，可以使用这个索引
                            break
                    
                    # 生成PCM
                    temp_pcm = os.path.join(tempfile.gettempdir(), f"temp_{current_index}_{idx}.pcm")
                    success = await synthesize_speech(text, temp_pcm, audio_format="raw")
                    
                    if success:
                        # 转换为Opus
                        try:
                            # 再次检查文件是否已存在（防止并发问题）
                            if os.path.exists(output_file):
                                current_index += 1
                                filename = f"{file_type}_{current_index:03d}.opus"
                                output_file = os.path.join(AUDIO_DIR, filename)
                            
                            subprocess.run([
                                "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                                "-i", temp_pcm, "-c:a", "libopus", "-b:a", "32k", "-frame_duration", "60",
                                output_file
                            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            
                            if os.path.exists(temp_pcm):
                                os.remove(temp_pcm)
                            
                            result_files.append({
                                "index": f"{current_index:03d}",
                                "filename": filename,
                                "text": text
                            })
                            
                            # 移动到下一个索引
                            current_index += 1
                            
                            await asyncio.sleep(0.5)  # 避免API限流
                        except Exception as e:
                            print(f"Failed to convert {filename}: {e}")
                            # 即使失败也移动到下一个索引，避免重复尝试
                            current_index += 1
                    else:
                        print(f"Failed to generate PCM for {filename}")
                        # 即使失败也移动到下一个索引
                        current_index += 1
                
                # 重新生成file_list.txt（使用新生成的文件信息 + 已存在的文件）
                # 先读取现有的file_list.txt，保留已存在文件的文本内容
                existing_text_map = {}
                if os.path.exists(FILE_LIST_TXT):
                    with open(FILE_LIST_TXT, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line or line in ["Inquiry Files:", "Compare Files:", "Order Files:"]:
                                continue
                            # 解析格式：001: filename.opus - 文本内容（文本可能为空）
                            match = re.match(r'(\d+):\s+(\w+_\d+\.opus)\s+-\s*(.+)', line)
                            if match:
                                filename = match.group(2)
                                text = match.group(3)
                                if text:  # 只保存非空文本
                                    existing_text_map[filename] = text
                
                # 更新新生成文件的文本内容（覆盖已有内容）
                for file_info in result_files:
                    existing_text_map[file_info["filename"]] = file_info["text"]
                
                # 重新扫描所有文件
                inquiries, compares, orders = scan_opus_files()
                
                # 用existing_text_map中的文本内容覆盖扫描结果（确保新生成的文件有文本）
                for file_list in [inquiries, compares, orders]:
                    for file_info in file_list:
                        if file_info["filename"] in existing_text_map:
                            file_info["text"] = existing_text_map[file_info["filename"]]
                
                # 确保所有新生成的文件都在列表中（如果扫描时遗漏了）
                for file_info in result_files:
                    # 检查是否已经在某个列表中
                    found = False
                    for file_list in [inquiries, compares, orders]:
                        if any(f["filename"] == file_info["filename"] for f in file_list):
                            # 确保文本内容正确
                            for f in file_list:
                                if f["filename"] == file_info["filename"]:
                                    f["text"] = file_info["text"]
                            found = True
                            break
                    
                    # 如果不在任何列表中，添加到inquiries（因为audio_xxx默认归类到inquiries）
                    if not found:
                        file_path = os.path.join(AUDIO_DIR, file_info["filename"])
                        if os.path.exists(file_path):
                            file_stat = os.stat(file_path)
                            inquiries.append({
                                "index": file_info["index"],
                                "filename": file_info["filename"],
                                "text": file_info["text"],
                                "file_size": file_stat.st_size,
                                "created_time": datetime.fromtimestamp(file_stat.st_ctime).isoformat()
                            })
                
                # 生成新的file_list.txt（确保新生成文件的文本内容被保存）
                from generate_batch_tts import generate_file_list
                generate_file_list(
                    [(int(f["index"]), f["filename"], f["text"]) for f in inquiries],
                    [(int(f["index"]), f["filename"], f["text"]) for f in compares],
                    [(int(f["index"]), f["filename"], f["text"]) for f in orders],
                    FILE_LIST_TXT
                )
                
                return result_files
            
            result = loop.run_until_complete(generate_files())
            loop.close()
            return result
        
        # 在后台线程中执行（不阻塞请求）
        import threading
        thread = threading.Thread(target=generate_files_async, daemon=True)
        thread.start()
        
        # 立即返回，告知用户文件正在生成
        return jsonify({
            "success": True,
            "message": f"已开始生成{len(texts)}个文件，请稍后刷新页面查看",
            "generated_files": []  # 实际文件在后台生成
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/opus/file/<filename>')
def get_opus_file(filename):
    """获取Opus音频文件"""
    try:
        file_path = os.path.join(AUDIO_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "文件不存在"}), 404
        
        # 使用正确的MIME类型，并添加CORS头
        response = send_file(file_path, mimetype='audio/ogg')  # Opus通常使用ogg容器
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Accept-Ranges'] = 'bytes'
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/opus/update-text', methods=['POST'])
def update_opus_text():
    """更新Opus文件的文本内容"""
    try:
        data = request.get_json() or {}
        filename = data.get('filename')
        text = data.get('text', '').strip()
        
        if not filename:
            return jsonify({"error": "缺少文件名"}), 400
        
        file_path = os.path.join(AUDIO_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "文件不存在"}), 404
        
        # 重新扫描所有文件
        inquiries, compares, orders = scan_opus_files()
        
        # 找到对应的文件并更新文本
        found = False
        for file_list in [inquiries, compares, orders]:
            for file_info in file_list:
                if file_info["filename"] == filename:
                    file_info["text"] = text
                    found = True
                    break
            if found:
                break
        
        if not found:
            return jsonify({"error": "文件未找到"}), 404
        
        # 重新生成file_list.txt
        from generate_batch_tts import generate_file_list
        generate_file_list(
            [(int(f["index"]), f["filename"], f["text"]) for f in inquiries],
            [(int(f["index"]), f["filename"], f["text"]) for f in compares],
            [(int(f["index"]), f["filename"], f["text"]) for f in orders],
            FILE_LIST_TXT
        )
        
        return jsonify({"success": True, "message": "文本内容已更新"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/opus/batch-update-text', methods=['POST'])
def batch_update_opus_text():
    """批量更新Opus文件的文本内容（按文件名顺序关联文本列表）"""
    try:
        data = request.get_json() or {}
        texts = data.get('texts', [])
        
        if not texts or not isinstance(texts, list):
            return jsonify({"error": "请提供文本列表"}), 400
        
        # 重新扫描所有文件，找出没有文本的文件
        inquiries, compares, orders = scan_opus_files()
        all_files = inquiries + compares + orders
        
        # 找出没有文本的文件，按文件名排序
        files_without_text = [f for f in all_files if not f.get("text") or not f["text"].strip()]
        files_without_text.sort(key=lambda x: x["filename"])
        
        if len(texts) != len(files_without_text):
            return jsonify({
                "error": f"文本数量({len(texts)})与缺少文本的文件数量({len(files_without_text)})不匹配",
                "files_count": len(files_without_text),
                "texts_count": len(texts)
            }), 400
        
        # 按顺序关联文本
        updated_count = 0
        for i, file_info in enumerate(files_without_text):
            if i < len(texts):
                file_info["text"] = texts[i].strip()
                updated_count += 1
        
        # 重新生成file_list.txt
        from generate_batch_tts import generate_file_list
        generate_file_list(
            [(int(f["index"]), f["filename"], f["text"]) for f in inquiries],
            [(int(f["index"]), f["filename"], f["text"]) for f in compares],
            [(int(f["index"]), f["filename"], f["text"]) for f in orders],
            FILE_LIST_TXT
        )
        
        return jsonify({
            "success": True,
            "message": f"已更新{updated_count}个文件的文本内容",
            "updated_count": updated_count
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    emit('connected', {'message': 'Connected to test server'})
    # 发送当前状态
    emit('status_update', test_state)

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print('Client disconnected')

if __name__ == '__main__':
    print("=" * 60)
    print("测试Web服务启动")
    print("=" * 60)
    print(f"访问地址: http://localhost:5000")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)

