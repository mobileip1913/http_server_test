# WebSocket 性能测试工具

基于 Python 的 WebSocket 性能测试工具，用于测试 WebSocket 服务器在高并发场景下的性能表现。

**重要更新**：测试脚本已完全对齐设备行为，包括音频数据分割和发送方式。详见 `docs/TECHNICAL_NOTES.md`。

## 功能特性

- ✅ 支持高并发连接测试（默认 100 个并发连接）
- ✅ 自动记录连接建立时间、消息传输时间、响应时间等指标
- ✅ 支持完整的响应流程跟踪（STT → LLM → TTS）
- ✅ 生成详细的测试报告（CSV、JSON 格式）
- ✅ 实时日志输出
- ✅ 统计信息（平均值、P95、P99 等）
- ✅ **完全模拟设备行为**：正确的Opus数据包分割和批量连续发送

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行测试

```bash
# 调试模式（1个连接）
export DEBUG_MODE="true"
python test_runner.py

# 正式测试（100个连接）
export DEBUG_MODE="false"
python test_runner.py
```

### 3. 查看结果

测试结果保存在 `results/` 目录：
- `results/logs/` - 详细日志
- `results/csv/` - CSV 格式结果
- `results/json/` - JSON 格式结果

## 配置

### 环境变量

```bash
# 服务器地址
export WS_SERVER_HOST="ws://toyaiws.spacechaintech.com:8081"

# 调试模式
export DEBUG_MODE="true"  # true=1个连接, false=100个连接

# 是否发送音频
export SEND_AUDIO_DATA="true"  # true=发送音频, false=只发送文本

# 监听模式
export LISTENING_MODE="auto"  # realtime|auto|manual

# 是否发送 stop_listen
export SEND_STOP_LISTEN="true"

# 测试消息
export TEST_MESSAGE="你好啊，我想去故宫"
```

### 配置文件

也可以直接修改 `config.py` 文件中的默认值。

## 项目结构

```
performance/
├── README.md                      # 本文件（快速开始）
├── requirements.txt               # Python 依赖
├── config.py                      # 配置文件
├── logger.py                      # 日志系统
├── utils.py                       # 工具函数
│
├── test_runner.py                 # 主测试脚本
├── websocket_client.py            # WebSocket 客户端
├── audio_encoder.py               # 音频编码器
├── metrics_collector.py           # 指标收集器
│
├── generate_tts_audio.py          # TTS 音频生成工具
├── local_transcribe.py            # 本地转录工具（可选）
│
├── start_ws_server.bat            # Windows 本地服务器启动脚本
├── start_ws_server.sh             # Linux/Mac 本地服务器启动脚本
│
├── docs/                          # 文档目录
│   ├── README.md                  # 详细使用说明
│   ├── PROJECT_STATUS.md          # 项目状态和问题列表
│   ├── TECHNICAL_NOTES.md         # 技术实现说明
│   ├── TROUBLESHOOTING.md         # 故障排查指南
│   ├── FILE_ORGANIZATION.md       # 文件组织说明
│   └── ...                        # 其他文档
│
├── audio/                         # 音频文件目录
│   └── test_audio.opus            # 测试音频文件
│
└── results/                       # 测试结果目录
    ├── logs/                      # 日志文件
    ├── csv/                       # CSV 结果
    └── json/                      # JSON 结果
```

## 相关文档

所有详细文档都在 `docs/` 目录下：

- **`docs/README.md`** - 完整的使用说明和配置指南
- **`docs/PROJECT_STATUS.md`** - 当前项目进度、已完成工作和问题列表
- **`docs/TECHNICAL_NOTES.md`** - 技术实现细节、设备行为分析和服务器处理机制
- **`docs/TROUBLESHOOTING.md`** - 故障排查指南和常见问题解决方案
- **`docs/FILE_ORGANIZATION.md`** - 文件组织说明和清理建议

## 支持

如有问题或建议，请参考 `docs/` 目录下的相关文档或联系项目维护者。

