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
    
    def _create_tts_sentence_callback(self, client, test_index: int, test_type: str, test_text: str):
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
            
            # 实时更新测试详情（使用绑定的test_index和test_type，确保每个测试的STT文本只更新到对应的对话项）
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
                                test_type: str, index: int, concurrency_index: int = None) -> dict:
        """重写测试方法，添加实时通知"""
        # 保存当前客户端，用于实时更新
        self.current_client = client
        
        # 为当前测试创建独立的TTS句子回调函数（绑定到当前测试的index和type）
        client._tts_sentence_callback = self._create_tts_sentence_callback(
            client, index, test_type, text
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
            
            # 优先尝试解析新的文本文件格式（支持三种类型）
            inquiries_texts, compares_texts, orders_texts = self.parse_text_files()
            
            # 如果新格式文件不存在，尝试旧格式
            if not inquiries_texts and not compares_texts and not orders_texts:
                inquiries_file = os.path.join(os.path.dirname(__file__), "product_inquiries.txt")
                inquiries_texts_old, purchases_texts_old = self.parse_inquiries_file(inquiries_file)
                inquiries_texts = inquiries_texts_old
                orders_texts = purchases_texts_old  # 将旧格式的 purchases 转换为 orders
            
            if not inquiries_texts:
                inquiries_texts = [f"询问 #{i+1}" for i in range(50)]
            if not compares_texts:
                compares_texts = []
            if not orders_texts:
                orders_texts = [f"购买 #{i+1}" for i in range(50)]
            
            # 计算总测试数
            total_tests = len(inquiries_texts) + len(compares_texts) + len(orders_texts)
            test_state["total"] = total_tests
            
            # 发送测试开始通知（在计算 total_tests 之后）
            emit_test_update("test_started", {
                "start_time": test_state["start_time"],
                "total": total_tests,  # 动态计算：询问 + 对比 + 购买/下单
                "concurrency_count": total_connections_for_notification
            })
            
            # 准备所有测试任务
            # 自动适配：使用实际存在的文件数量，而不是文本文件的行数
            all_test_items = []
            
            # 获取每种类型实际存在的文件索引
            inquiry_indices = self.scan_audio_files("inquiry")
            compare_indices = self.scan_audio_files("compare")
            order_indices = self.scan_audio_files("order")
            if not order_indices:
                order_indices = self.scan_audio_files("purchase")
            
            # 检查是否有测试数量限制
            test_count = settings.get("test_count")
            total_available = len(inquiry_indices) + len(compare_indices) + len(order_indices)
            
            if test_count and test_count > 0:
                # 随机选择指定数量的文件
                selected_items = self._random_select_test_files(
                    inquiry_indices, compare_indices, order_indices,
                    inquiries_texts, compares_texts, orders_texts,
                    test_count
                )
                all_test_items = selected_items
                if len(all_test_items) < test_count:
                    self.logger.info(f"随机选择了 {len(all_test_items)} 个测试任务（设置数量: {test_count}，实际可用: {total_available}）")
                else:
                    self.logger.info(f"随机选择了 {len(all_test_items)} 个测试任务（设置数量: {test_count}）")
            else:
                # 测试所有文件
                self.logger.info(f"测试所有文件，共 {total_available} 个文件（询问: {len(inquiry_indices)}, 对比: {len(compare_indices)}, 下单: {len(order_indices)}）")
                # 获取所有索引的并集，确保所有文件都被测试
                all_indices = set(inquiry_indices + compare_indices + order_indices)
                all_indices = sorted(all_indices)
                
                for index in all_indices:
                    test_item = {"index": index}
                    
                    # 询问
                    if index in inquiry_indices:
                        inquiry_file = self.get_audio_file(index, "inquiry")
                        if inquiry_file:
                            # 使用文本文件中的文本，如果索引超出范围则使用默认文本
                            inquiry_text = inquiries_texts[index - 1] if index <= len(inquiries_texts) else f"询问 #{index}"
                            test_item["inquiry_file"] = inquiry_file
                            test_item["inquiry_text"] = inquiry_text
                    
                    # 对比
                    if index in compare_indices:
                        compare_file = self.get_audio_file(index, "compare")
                        if compare_file:
                            # 使用文本文件中的文本，如果索引超出范围则使用默认文本
                            compare_text = compares_texts[index - 1] if index <= len(compares_texts) else f"对比 #{index}"
                            test_item["compare_file"] = compare_file
                            test_item["compare_text"] = compare_text
                    
                    # 购买/下单
                    if index in order_indices:
                        order_file = self.get_audio_file(index, "order")
                        if order_file:
                            # 使用文本文件中的文本，如果索引超出范围则使用默认文本
                            order_text = orders_texts[index - 1] if index <= len(orders_texts) else f"购买 #{index}"
                            test_item["order_file"] = order_file
                            test_item["order_text"] = order_text
                        else:
                            # 兼容旧格式：尝试 purchase
                            purchase_file = self.get_audio_file(index, "purchase")
                            if purchase_file:
                                order_text = orders_texts[index - 1] if index <= len(orders_texts) else f"购买 #{index}"
                                test_item["purchase_file"] = purchase_file
                                test_item["purchase_text"] = order_text
                    
                    # 至少有一个文件才添加
                    if "inquiry_file" in test_item or "compare_file" in test_item or "order_file" in test_item or "purchase_file" in test_item:
                        all_test_items.append(test_item)
            
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
                            # 测试询问
                            if "inquiry_file" in test_item:
                                inquiry_result = await self.test_single_audio(
                                    client, test_item["inquiry_file"], test_item["inquiry_text"],
                                    "inquiry", test_item["index"], concurrency_index=client.connection_id - 1
                                )
                                self.results.append(inquiry_result)
                                test_state["results"].append(inquiry_result)
                                test_state["progress"] = len(test_state["results"])
                                if inquiry_result["success"]:
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
                                    "summary": test_state["summary"]
                                })
                                await asyncio.sleep(0.2)
                            
                            # 测试对比
                            if "compare_file" in test_item:
                                compare_result = await self.test_single_audio(
                                    client, test_item["compare_file"], test_item["compare_text"],
                                    "compare", test_item["index"], concurrency_index=client.connection_id - 1
                                )
                                self.results.append(compare_result)
                                test_state["results"].append(compare_result)
                                test_state["progress"] = len(test_state["results"])
                                if compare_result["success"]:
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
                                    "summary": test_state["summary"]
                                })
                                await asyncio.sleep(0.2)
                            
                            # 测试购买/下单
                            if "order_file" in test_item:
                                order_result = await self.test_single_audio(
                                    client, test_item["order_file"], test_item["order_text"],
                                    "order", test_item["index"], concurrency_index=client.connection_id - 1
                                )
                                self.results.append(order_result)
                                test_state["results"].append(order_result)
                                test_state["progress"] = len(test_state["results"])
                                if order_result["success"]:
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
                                    "summary": test_state["summary"]
                                })
                                await asyncio.sleep(0.2)
                            elif "purchase_file" in test_item:  # 兼容旧格式
                                purchase_result = await self.test_single_audio(
                                    client, test_item["purchase_file"], test_item["purchase_text"],
                                    "purchase", test_item["index"], concurrency_index=client.connection_id - 1
                                )
                                self.results.append(purchase_result)
                                test_state["results"].append(purchase_result)
                                test_state["progress"] = len(test_state["results"])
                                if purchase_result["success"]:
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
    
    # 性能指标统计（过滤掉无效值：None、负值、异常大的值）
    stt_times = [r.get("stt_time") for r in results if r.get("stt_time") is not None and r.get("stt_time") >= 0 and r.get("stt_time") <= 60000]
    llm_times = [r.get("llm_time") for r in results if r.get("llm_time") is not None and r.get("llm_time") >= 0 and r.get("llm_time") <= 60000]
    tts_start_times = [r.get("tts_start_time") for r in results if r.get("tts_start_time") is not None and r.get("tts_start_time") >= 0 and r.get("tts_start_time") <= 10000]
    tts_durations = [r.get("tts_duration") for r in results if r.get("tts_duration") is not None and r.get("tts_duration") >= 0 and r.get("tts_duration") <= 120000]
    total_response_times = [r.get("total_response_time") for r in results if r.get("total_response_time") is not None and r.get("total_response_time") >= 0 and r.get("total_response_time") <= 120000]
    
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
            "total_response_time": r.get("total_response_time")
        })
    
    report = {
        "test_info": {
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration_seconds,
            "concurrency": settings.get("concurrency", 0),
            "device_count": len(settings.get("device_sns", [])),
            "test_mode": settings.get("test_mode", "normal")
        },
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
            "stt_time": calc_stats(stt_times),
            "llm_time": calc_stats(llm_times),
            "tts_start_time": calc_stats(tts_start_times),
            "tts_duration": calc_stats(tts_durations),
            "total_response_time": calc_stats(total_response_times)
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
        ['测试模式', '急速模式' if test_info.get("test_mode") == 'fast' else '正常模式']
    ]
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
    
    # 性能指标
    story.append(Paragraph("性能指标", heading_style))
    metrics = report.get("performance_metrics", {})
    metric_names = {
        'stt_time': 'STT识别时间',
        'llm_time': 'LLM响应时间',
        'tts_start_time': 'TTS启动时间',
        'tts_duration': 'TTS持续时间',
        'total_response_time': '总响应时间'
    }
    
    for key, name in metric_names.items():
        metric = metrics.get(key)
        if metric and metric.get("count", 0) > 0:
            story.append(Paragraph(f"<b>{name}</b>", normal_style))
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

