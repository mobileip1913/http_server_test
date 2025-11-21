# 语音对话测试平台 - 开发文档

## 1. 项目架构

### 1.1 技术栈
- **后端**：Python 3.8+, Flask, Flask-SocketIO
- **前端**：HTML5, CSS3, JavaScript (ES6+), Chart.js
- **WebSocket**：websockets (Python), Socket.IO (前端)
- **音频处理**：opuslib, FFmpeg
- **报告生成**：ReportLab (PDF), CSV, JSON

### 1.2 项目结构
```
http_server/
├── web_server.py              # Flask Web服务器主文件
├── test_inquiries.py          # 测试逻辑（询问、对比、下单测试）
├── websocket_client.py        # WebSocket客户端封装
├── config.py                  # 配置文件
├── logger.py                  # 日志工具
├── utils.py                   # 工具函数
├── audio_encoder.py           # 音频编码器
├── generate_tts_audio.py      # 单个TTS音频生成工具
├── generate_batch_tts.py       # 批量TTS音频生成工具
├── start_web_server.py        # 启动脚本
├── start_web.bat              # Windows启动脚本
├── requirements.txt           # Python依赖
├── templates/                 # HTML模板
│   └── test_dashboard.html
├── static/                    # 静态资源
│   ├── css/
│   │   └── dashboard.css
│   └── js/
│       └── dashboard.js
├── audio/                     # 测试音频文件
│   └── inquiries/            # 询问、对比、下单音频文件
├── libs/                      # 外部依赖库
│   └── opus.dll              # Opus库（Windows，自动加载）
└── docs/                      # 文档目录
    ├── REQUIREMENTS.md        # 需求文档
    └── DEVELOPMENT.md         # 开发文档（本文件）
```

## 2. 核心模块说明

### 2.1 Web服务器模块（web_server.py）

#### 2.1.1 主要功能
- Flask Web服务器
- WebSocket实时通信
- 测试任务管理
- 测试报告生成（PDF/CSV/JSON）

#### 2.1.2 关键API端点
- `GET /` - 主页面
- `POST /api/start` - 开始批量测试
- `POST /api/stop` - 停止测试
- `POST /api/single-test` - 执行单语音测试
- `GET /api/report` - 获取测试报告（JSON）
- `GET /api/report/pdf` - 导出PDF报告
- `GET /api/report/csv` - 导出CSV报告
- `GET /api/report/json` - 导出JSON报告

#### 2.1.3 WebSocket事件
- `test_started` - 测试开始
- `test_result` - 测试结果更新
- `progress_update` - 进度更新
- `test_completed` - 测试完成
- `test_error` - 测试错误
- `single_test_start` - 单语音测试开始
- `single_test_complete` - 单语音测试完成
- `single_test_error` - 单语音测试错误

### 2.2 测试逻辑模块（test_inquiries.py）

#### 2.2.1 InquiryTester类
负责执行测试的核心类，主要方法：
- `parse_text_files()` - 解析文本文件
- `scan_audio_files()` - 扫描音频文件
- `_random_select_test_files()` - 随机选择测试文件
- `test_single_audio()` - 执行单个音频测试
- `run_test()` - 运行测试（批量模式）

#### 2.2.2 测试流程
1. 解析文本文件和扫描音频文件
2. 随机选择测试文件（如果设置了test_count）
3. 为每个测试创建WebSocket客户端
4. 发送音频数据
5. 等待并收集响应
6. 计算性能指标
7. 更新测试状态

### 2.3 WebSocket客户端模块（websocket_client.py）

#### 2.3.1 WebSocketClient类
管理WebSocket连接和消息传输，关键属性：
- `send_time` - 发送第一帧音频的时间（毫秒时间戳）
- `stt_response_time` - STT响应时间
- `llm_response_time` - LLM响应时间
- `tts_start_time` - TTS开始时间
- `tts_stop_time` - TTS结束时间

#### 2.3.2 时间戳记录逻辑
```python
# 发送音频前
self.send_time = time.time() * 1000  # 毫秒时间戳

# 收到STT响应
if not self.has_stt and self.send_time:
    self.stt_response_time = time.time() * 1000
    self.has_stt = True

# 收到LLM响应
if not self.has_llm:
    self.llm_response_time = time.time() * 1000
    self.has_llm = True

# 收到TTS start
if state == "start" and not self.has_tts_start:
    self.tts_start_time = time.time() * 1000
    self.has_tts_start = True

# 收到TTS stop
elif state == "stop" and not self.has_tts_stop:
    self.tts_stop_time = time.time() * 1000
    self.has_tts_stop = True
```

#### 2.3.3 延迟计算
```python
# STT服务延迟
stt_latency = stt_response_time - send_time

# LLM服务延迟
llm_latency = llm_response_time - stt_response_time

# TTS服务延迟
tts_latency = tts_start_time - llm_response_time

# 端到端响应时间
e2e_response_time = tts_stop_time - send_time
```

### 2.4 音频编码模块（audio_encoder.py）

#### 2.4.1 主要功能
- Opus音频编码
- Ogg容器解析
- 音频包分割
- 自动加载opus.dll

#### 2.4.2 DLL加载机制
```python
# 自动从项目目录加载opus.dll
dll_paths = [
    os.path.join(os.path.dirname(__file__), 'opus.dll'),
    os.path.join(os.path.dirname(__file__), 'libs', 'opus.dll')
]
for dll_path in dll_paths:
    if os.path.exists(dll_path):
        os.add_dll_directory(os.path.dirname(dll_path))
        break
```

### 2.5 TTS音频生成模块

#### 2.5.1 generate_tts_audio.py
- 单个音频生成工具
- 调用讯飞TTS API
- 支持Opus和MP3格式

#### 2.5.2 generate_batch_tts.py
- 批量音频生成工具
- 支持三种文件模式
- 自动生成映射文件

## 3. 数据流程

### 3.1 批量测试流程
```
用户配置 → 开始测试 → 解析文件 → 随机选择 → 创建客户端
    ↓
发送音频 → 记录send_time → 等待STT响应 → 记录stt_response_time
    ↓
等待LLM响应 → 记录llm_response_time → 等待TTS开始 → 记录tts_start_time
    ↓
等待TTS结束 → 记录tts_stop_time → 计算延迟 → 更新状态
    ↓
所有测试完成 → 生成报告
```

### 3.2 单语音测试流程
```
用户输入文字 → 调用TTS API → 生成PCM → 转换为Opus
    ↓
执行测试 → 记录时间戳 → 计算延迟 → 显示结果
    ↓
添加到对话流
```

### 3.3 延迟计算流程
```
发送音频（send_time）
    ↓
STT响应（stt_response_time）
    ↓ 计算：stt_latency = stt_response_time - send_time
LLM响应（llm_response_time）
    ↓ 计算：llm_latency = llm_response_time - stt_response_time
TTS开始（tts_start_time）
    ↓ 计算：tts_latency = tts_start_time - llm_response_time
TTS结束（tts_stop_time）
    ↓ 计算：e2e_response_time = tts_stop_time - send_time
```

## 4. 关键实现细节

### 4.1 测试完成判断
确保每个对话完成后再进行下一个：
```python
# 必须等待完整的TTS stop响应
if client.has_tts_stop and tts_stop_valid:
    # 测试完成
    result["success"] = True
else:
    # 继续等待或标记失败
    result["success"] = False
```

### 4.2 时间戳验证
确保时间戳属于当前测试：
```python
# 验证时间戳是否属于本次测试
if client.send_time >= send_start_time_ms - 2000 and \
   client.stt_response_time >= send_start_time_ms - 2000:
    # 时间戳有效
    stt_latency_ms = client.stt_response_time - client.send_time
```

### 4.3 随机选择算法
```python
# 计算每种类型应该选多少个（平均分配）
base_count = actual_test_count // 3
remainder = actual_test_count % 3

# 分配基础数量
inquiry_count = base_count
compare_count = base_count
order_count = base_count

# 有余数的话随机分配到某个类型
if remainder > 0:
    types = ['inquiry', 'compare', 'order']
    selected_types = random.sample(types, remainder)
    # 分配余数
```

### 4.4 报告生成
```python
# 生成报告数据
report = generate_test_report(results, summary, start_time, end_time, settings)

# 包含内容：
# - test_info: 测试信息
# - test_environment: 测试环境
# - test_cases: 详细测试用例列表
# - summary: 总体统计
# - performance_metrics: 性能指标
# - failure_analysis: 失败分析
# - timeline: 时间线数据
```

## 5. 配置说明

### 5.1 配置文件（config.py）
- `WS_SERVER_HOST` - WebSocket服务器地址（ws://）
- `WSS_SERVER_HOST` - WebSocket服务器地址（wss://）
- `USE_SSL` - 是否使用SSL
- `DEFAULT_DEVICE_SN` - 默认设备SN

### 5.2 环境变量
- `XFYUN_APPID` - 讯飞APPID（可选，默认使用代码中的值）
- `XFYUN_API_KEY` - 讯飞API Key（可选）
- `XFYUN_API_SECRET` - 讯飞API Secret（可选）

### 5.3 音频文件组织
```
audio/inquiries/
├── inquiries.txt          # 询问文本文件（每行一个问题）
├── compares.txt           # 对比文本文件
├── orders.txt             # 下单文本文件
├── file_list.txt          # 映射文件（自动生成）
├── inquiry_001.opus      # 询问音频文件
├── compare_001.opus       # 对比音频文件
└── order_001.opus         # 下单音频文件
```

## 6. 开发指南

### 6.1 添加新功能
1. 在相应模块中添加功能代码
2. 更新API端点（如需要）
3. 更新前端界面（如需要）
4. 更新文档

### 6.2 调试技巧
- 查看日志文件：`results/logs/`
- 使用浏览器开发者工具查看WebSocket消息
- 检查时间戳记录是否正确
- 验证延迟计算是否准确

### 6.3 测试建议
1. 先使用单语音测试验证功能
2. 再使用批量测试验证性能
3. 检查报告数据是否完整
4. 验证延迟计算是否准确

## 7. 常见问题

### 7.1 时间戳不准确
- 确保使用毫秒时间戳（`time.time() * 1000`）
- 验证时间戳是否属于当前测试
- 检查是否有时间戳被重复使用

### 7.2 测试未完成就进入下一个
- 确保等待完整的TTS stop响应
- 检查测试完成判断逻辑
- 增加等待时间（如果需要）

### 7.3 延迟计算异常
- 检查时间戳记录是否正确
- 验证时间戳单位是否一致（毫秒）
- 过滤异常值（负值、过大值）

### 7.4 Opus库加载失败
- 确保opus.dll在libs/目录下
- 检查Python版本（需要3.8+）
- 验证DLL加载路径

## 8. 性能优化

### 8.1 并发测试优化
- 使用异步IO（asyncio）
- 合理设置并发数
- 避免过多并发导致服务器压力

### 8.2 报告生成优化
- 使用流式生成（PDF）
- 批量处理数据（CSV）
- 缓存计算结果

### 8.3 内存优化
- 及时清理临时文件
- 使用生成器处理大量数据
- 限制并发连接数

## 9. 未来改进方向

### 9.1 功能增强
- 支持更多测试类型
- 支持自定义测试脚本
- 支持测试用例管理

### 9.2 性能优化
- 支持分布式测试
- 优化报告生成速度
- 支持实时报告更新

### 9.3 用户体验
- 改进UI设计
- 添加更多可视化图表
- 支持测试结果对比

