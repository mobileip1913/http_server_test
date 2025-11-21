# WebSocket 性能测试工具

基于 Python 的 WebSocket 性能测试工具，用于测试 WebSocket 服务器在高并发场景下的性能表现。

**重要更新**：测试脚本已完全对齐设备行为，包括音频数据分割和发送方式。详见 `TECHNICAL_NOTES.md`。

## 功能特性

- ✅ 支持高并发连接测试（默认 100 个并发连接）
- ✅ 自动记录连接建立时间、消息传输时间、响应时间等指标
- ✅ 支持完整的响应流程跟踪（STT → LLM → TTS）
- ✅ 生成详细的测试报告（CSV、JSON 格式）
- ✅ 实时日志输出
- ✅ 统计信息（平均值、P95、P99 等）
- ✅ **完全模拟设备行为**：正确的Opus数据包分割和批量连续发送

## 安装要求

### Python 版本
- Python 3.8 或更高版本

### 依赖安装

```bash
pip install -r requirements.txt
```

或者手动安装：

```bash
pip install websockets>=12.0 aiohttp>=3.9.0 pandas>=2.0.0 numpy>=1.24.0 opuslib>=2.0.0
```

**注意**：`opuslib` 是必需的，用于正确分割连续的 Opus 数据包。

## 配置

### 环境变量配置

测试脚本支持通过环境变量进行配置：

```bash
# WebSocket 服务器配置
export WS_SERVER_HOST="ws://toyaiws.spacechaintech.com:8081"
export WSS_SERVER_HOST="wss://toyaiws.spacechaintech.com"
export USE_SSL="false"  # 使用 WS 还是 WSS

# 注意：token 验证已移除，不再需要设置 ACCESS_TOKEN
# 如果服务器需要，可以设置：
# export WEBSOCKET_ACCESS_TOKEN="your_token"

# 监听模式配置（重要！）
export LISTENING_MODE="auto"  # realtime|auto|manual，推荐使用 auto
export SEND_STOP_LISTEN="true"  # 是否在发送完音频后发送 stop_listen

# 设备信息（已使用已注册的设备作为默认值，通常无需修改）
# export DEVICE_SN="FC012C2EA0A0"  # 已注册的设备 SN
# export DEVICE_SIGN="c61505cccb8dc83d8e67450cbd4f32c4"
# export BOARD_ID="TKAI_BOARD_03_4G_VB6824_EYE_ST7789"
# export FIRMWARE_VERSION="0.0.1"
# export FIRMWARE_VERSION_CODE="20250908001"
# export STRATEGY_ID="0"
# export DEVICE_UID="0"
# export BOARD_TYPE="wifi"
# export RECOVER="0"
# export SCREEN="1"

# 测试参数
export DEBUG_MODE="true"  # 调试模式：true=只发送1个连接，false=发送100个连接（默认false）
export CONCURRENT_CONNECTIONS="100"  # 并发连接数（仅在DEBUG_MODE=false时生效）
export TEST_MESSAGE="你好啊，我今天想去故宫玩"  # 测试消息

# 音频发送配置
export SEND_AUDIO_DATA="true"  # true=发送Opus音频数据，false=只发送文本消息（快速测试模式）
export AUDIO_FILE_PATH=""  # 可选：预录制的音频文件路径（如果提供，将使用此文件）

# 超时设置（毫秒）
export CONNECT_TIMEOUT="10000"  # 连接超时
export MESSAGE_TIMEOUT="30000"  # 消息超时
export STT_TIMEOUT="5000"  # STT 响应超时
export TTS_TIMEOUT="60000"  # TTS 响应超时

# 日志配置
export LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
export LOG_TO_FILE="true"  # 是否输出到文件
export LOG_TO_CONSOLE="true"  # 是否输出到控制台

# 结果输出目录（可选）
export RESULTS_DIR="results"
```

### 配置文件方式

你也可以直接修改 `config.py` 文件中的默认值。

## 使用方法

### 基本使用

1. **选择运行模式**：
   ```bash
   # 调试模式：只发送1个连接（用于调试）
   export DEBUG_MODE="true"
   python test_runner.py
   
   # 测试模式：发送100个连接（正式测试）
   export DEBUG_MODE="false"
   python test_runner.py
   ```

2. **选择音频模式**（可选）：
   ```bash
   # 模式1：发送音频数据（真实测试，需要 ffmpeg）
   export SEND_AUDIO_DATA="true"
   
   # 模式2：只发送文本消息（快速测试，不需要 ffmpeg）
   export SEND_AUDIO_DATA="false"
   ```

3. **运行测试**：
   ```bash
   python test_runner.py
   ```

### 完整示例

**调试模式（1个连接）**：
```bash
export DEBUG_MODE="true"
export SEND_AUDIO_DATA="true"
python test_runner.py
```

**正式测试（100个连接）**：
```bash
export DEBUG_MODE="false"
export CONCURRENT_CONNECTIONS="100"
export SEND_AUDIO_DATA="true"
python test_runner.py
```

**快速文本测试（无音频，100个连接）**：
```bash
export DEBUG_MODE="false"
export SEND_AUDIO_DATA="false"
python test_runner.py
```

### Windows 使用方式

在 Windows PowerShell 中：

```powershell
# 设置环境变量
$env:DEBUG_MODE="true"  # 调试模式：true=1个连接，false=100个连接
$env:SEND_AUDIO_DATA="true"  # 是否发送音频数据
$env:TEST_MESSAGE="你好啊，我今天想去故宫玩"

# 运行测试
python test_runner.py
```

在 Windows CMD 中：

```cmd
set DEBUG_MODE=true
set SEND_AUDIO_DATA=true
set LISTENING_MODE=auto
set SEND_STOP_LISTEN=true
set TEST_MESSAGE=你好啊，我今天想去故宫玩
set LOG_LEVEL=DEBUG

python test_runner.py
```

## 测试流程

完全模拟实际设备的通信流程：

1. **建立连接**：创建指定数量的并发 WebSocket 连接
   - 设置 HTTP 头：Protocol-Version, Device-Id, Authorization（可选）
   - URL 包含所有设备参数（SN, Sign, Board ID 等）

2. **等待认证**：等待服务器返回 auth 消息（不强制等待）

3. **发送 start_listen**：发送启动音频监听消息
   - 支持三种模式：realtime（持续）、auto（自动）、manual（手动）
   - 默认使用 auto 模式，更符合实际使用场景

4. **发送音频数据**：逐帧发送 Opus 编码的音频数据
   - 每帧间隔 60ms，完全模拟真实设备采集节奏
   - 二进制格式发送，与项目代码完全一致

5. **发送 stop_listen**（可选）：根据监听模式决定是否发送
   - auto 模式：可选发送（服务器可能自动检测VAD）
   - manual 模式：必须发送
   - realtime 模式：不发送（持续监听）

6. **等待响应**：等待服务器返回完整的响应（STT → LLM → TTS）
   - 显示所有接收到的文本内容
   - 支持所有消息类型（abort, interrupt, iot, actions, emoji 等）

7. **收集指标**：记录各项性能指标
8. **生成报告**：导出 CSV 和 JSON 格式的测试报告

## 输出结果

测试完成后，会在 `results/` 目录下生成以下文件：

### 日志文件
- `results/logs/test_YYYYMMDD_HHMMSS.log` - 详细的测试日志

### CSV 文件
- `results/csv/test_results_YYYYMMDD_HHMMSS.csv` - 每个连接的详细指标数据

CSV 包含以下列：
- `connection_id`: 连接ID
- `connect_time`: 连接建立时间（ms）
- `connect_status`: 连接状态（success/failed）
- `send_time`: 消息发送时间（ms）
- `stt_time`: STT响应时间（ms）
- `llm_time`: LLM响应时间（ms）
- `tts_start_time`: TTS开始时间（ms）
- `tts_duration`: TTS持续时间（ms）
- `total_response_time`: 总响应时间（ms）
- `message_size`: 消息大小（bytes）
- `response_size`: 响应大小（bytes）
- `complete`: 是否收到完整响应（true/false）
- `error_type`: 错误类型（如果有）
- `error_message`: 错误消息（如果有）

### JSON 文件
- `results/json/test_results_YYYYMMDD_HHMMSS.json` - 完整的测试结果（包括摘要和详细数据）

JSON 结构：
```json
{
  "test_info": {
    "start_time": "...",
    "end_time": "...",
    "duration": 300,
    "concurrent_connections": 100,
    "test_message": "..."
  },
  "summary": {
    "total_connections": 100,
    "successful_connections": 95,
    "failed_connections": 5,
    "avg_response_time": 1234.5,
    "p95_response_time": 2345.6,
    "p99_response_time": 3456.7,
    "qps": 0.5
  },
  "connections": [...]
}
```

## 测试指标说明

### 连接性能指标
- **连接建立时间**：从发起连接到连接成功的时间
- **连接成功率**：成功建立的连接数 / 总连接数

### 消息传输性能指标
- **消息响应时间 (RTT)**：从发送消息到收到第一个响应的时间
- **完整响应时间**：从发送消息到收到完整响应（TTS结束）的时间
- **QPS (Queries Per Second)**：每秒处理的查询数

### 服务器响应质量指标
- **STT 响应时间**：从发送消息到收到 STT 响应的时间
- **LLM 响应时间**：从收到 STT 到收到 LLM 响应的时间
- **TTS 开始时间**：从收到 LLM 到 TTS 开始的时间
- **TTS 持续时间**：TTS 播放的总时长

### 统计指标
- **平均值**：所有请求的平均响应时间
- **P95**：95% 的请求响应时间低于此值
- **P99**：99% 的请求响应时间低于此值

## 故障排查

### 连接失败

**问题**：所有连接都失败

**可能原因**：
1. 网络连接问题
2. 服务器地址不正确
3. 服务器拒绝连接

**解决方法**：
1. 检查网络连接
2. 验证服务器地址和端口
3. 检查服务器日志查看拒绝原因

### 音频数据生成失败

**问题**：无法生成音频数据

**可能原因**：
1. `ffmpeg` 未安装
2. `SEND_AUDIO_DATA=true` 但系统缺少依赖

**解决方法**：
1. 安装 ffmpeg：`sudo apt install ffmpeg` (Linux) 或 `brew install ffmpeg` (Mac)
2. 或者使用文本模式：`export SEND_AUDIO_DATA="false"`
3. 或者提供预录制的音频文件：`export AUDIO_FILE_PATH="/path/to/audio.opus"`

### 服务器没有响应

**问题**：连接成功，但服务器没有返回 STT/LLM/TTS 响应

**可能原因**：
1. 监听模式不正确（使用了 `realtime` 但没有持续发送音频）
2. 没有发送 `stop_listen` 消息（服务器不知道音频传输已完成）
3. 音频数据太短（只有1帧，可能不足以触发完整对话）
4. 服务器端处理延迟或问题

**解决方法**：
1. **使用正确的监听模式**：
   ```bash
   export LISTENING_MODE="auto"  # 推荐使用 auto 模式
   ```
2. **确保发送 stop_listen**：
   ```bash
   export SEND_STOP_LISTEN="true"  # 确保服务器知道音频传输完成
   ```
3. **查看详细诊断日志**：
   ```bash
   export LOG_LEVEL="DEBUG"  # 查看连接状态、接收任务状态等详细信息
   export DEBUG_MODE="true"  # 先测试单个连接
   ```
4. **检查连接状态**：日志中会显示连接是否在等待期间断开
5. **检查服务器端日志**：确认服务器是否收到请求并开始处理
6. **验证消息格式**：确保所有消息格式与项目代码完全一致（已优化）

### 消息超时

**问题**：消息发送后没有收到响应（超时）

**可能原因**：
1. 服务器响应慢
2. 超时设置过短
3. 消息格式不正确

**解决方法**：
1. 增加超时时间（`export TTS_TIMEOUT="120000"` 设置为 120 秒）
2. 检查消息格式是否正确（已优化，完全匹配项目代码）
3. 查看服务器日志
4. 使用 DEBUG 模式查看详细诊断信息

### 依赖安装问题

**问题**：`pip install` 失败

**解决方法**：
```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者使用 conda
conda install websockets aiohttp pandas numpy
```

## 注意事项

1. **Token 验证**：已完全移除，不再需要设置任何 token
2. **并发数**：建议从较小的并发数开始测试（如 10、50），逐步增加
3. **网络环境**：确保网络连接稳定，避免网络问题影响测试结果
4. **服务器负载**：高并发测试可能对服务器造成较大负载，请谨慎使用
5. **资源限制**：大量并发连接会消耗系统资源，注意监控系统资源使用情况

## 项目结构

```
performance/
├── README.md                      # 本文件
├── requirements.txt               # Python 依赖
├── config.py                      # 配置文件
├── logger.py                      # 日志记录器
├── utils.py                       # 工具函数
├── websocket_client.py            # WebSocket 客户端
├── metrics_collector.py           # 指标收集器
├── audio_encoder.py               # 音频编码器（Opus数据包分割和编码）
├── test_runner.py                 # 主测试脚本
├── generate_tts_audio.py          # 讯飞TTS音频生成工具（生成Opus格式）
├── generate_mp3.py                # MP3音频生成工具（用于试听）
├── websocket_performance_test_design.md  # 设计文档
├── DEVICE_VS_TEST_COMPARISON.md   # 设备发送方式对比分析（重要！）
├── README_TTS.md                  # TTS音频生成工具使用说明
├── AUDIO_FORMAT_ISSUE.md          # 音频格式问题说明
├── OPTIMIZATION_SUMMARY.md        # 优化总结
├── audio/                         # 音频文件目录
│   ├── test_audio.opus            # Opus格式测试音频
│   └── test_audio.mp3             # MP3格式测试音频（用于试听）
└── results/                       # 测试结果目录
    ├── logs/                      # 日志文件
    ├── csv/                       # CSV 结果
    └── json/                      # JSON 结果
```

## 许可证

本项目遵循项目主许可证。

## 相关文档

所有文档位于 `docs/` 目录下：

- **`PROJECT_STATUS.md`** - 查看当前项目进度、已完成工作和问题列表
- **`TECHNICAL_NOTES.md`** - 查看技术实现细节、设备行为分析和服务器处理机制
- **`TROUBLESHOOTING.md`** - 查看故障排查指南和常见问题解决方案
- **`FILE_ORGANIZATION.md`** - 查看文件组织说明和清理建议

**注意**: 本文档位于 `performance/docs/` 目录下，是完整的使用说明。performance 根目录下的 `README.md` 是快速开始指南。

## 支持

如有问题或建议，请参考上述文档或联系项目维护者。

