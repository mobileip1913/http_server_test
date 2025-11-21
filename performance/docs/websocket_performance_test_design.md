# WebSocket 性能测试设计文档

## 1. 测试目标

### 1.1 测试目的
评估 WebSocket 服务器在高并发场景下的性能表现，包括：
- 连接建立能力
- 消息传输性能
- 服务器响应时间
- 系统稳定性
- 资源消耗情况

### 1.2 测试场景
- **并发连接数**: 100个并发 WebSocket 连接
- **测试消息**: "你好啊，我今天想去故宫玩"
- **消息类型**: 文本消息（模拟用户输入）
- **测试模式**: 压力测试（负载测试）

## 2. WebSocket 协议分析

### 2.1 连接建立

#### 2.1.1 服务器地址
根据代码分析，WebSocket 服务器地址：
- **WS (非加密)**: `ws://toyaiws.spacechaintech.com:8081`
- **WSS (加密)**: `wss://toyaiws.spacechaintech.com`

#### 2.1.2 连接 URL 参数
连接时需要传递以下查询参数：
```
/?sn={DEVICE_SN}
&sign={DEVICE_SIGN}
&platform=hw
&bid={BOARD_ID}
&fv={FIRMWARE_VERSION}
&fvc={FIRMWARE_VERSION_CODE}
&strategy_id={OTA_STRATEGY_ID}
&uid={DEVICE_UID}
&board_type={BOARD_TYPE}
&recover={RECOVER_FLAG}
&enableP3=2
&tool=idf
&screen={SCREEN_FLAG}
```

**实际示例**：
```
ws://toyaiws.spacechaintech.com:8081/?sn=FC012C2EA0A0&sign=c61505cccb8dc83d8e67450cbd4f32c4&platform=hw&bid=TKAI_BOARD_03_4G_VB6824_EYE_ST7789&fv=0.0.1&fvc=20250908001&strategy_id=0&uid=0&board_type=wifi&recover=0&enableP3=2&tool=idf&screen=1
```

**参数说明**：
- `sn`: 设备序列号（基于 MAC 地址，格式：`XXXXXXXXXXXX`，12位大写十六进制）
  - 示例：`FC012C2EA0A0`
- `sign`: 设备签名（MD5(sn + appkey)，32位小写十六进制）
  - 示例：`c61505cccb8dc83d8e67450cbd4f32c4`
- `platform`: 平台标识（固定值：`hw`）
- `bid`: 板子ID（从板子配置JSON获取，字符串格式）
  - 示例：`TKAI_BOARD_03_4G_VB6824_EYE_ST7789`
- `fv`: 固件版本号（格式：`x.y.z`）
  - 示例：`0.0.1`
- `fvc`: 固件版本代码（通常为日期格式的字符串或数字）
  - 示例：`20250908001`
- `strategy_id`: OTA策略ID（整数，默认0）
  - 示例：`0`
- `uid`: 设备UID（用于自动绑定，整数，未绑定时为0）
  - 示例：`0`
- `board_type`: 板子类型（字符串：`"wifi"` 或 `"ml307"`）
  - 示例：`wifi`
- `recover`: 出厂模式标记（整数：`0`=正常模式，`1`=出厂模式）
  - 示例：`0`
- `enableP3`: 音频播放支持标记（固定值：`2`）
- `tool`: 工具标识（固定值：`idf`）
- `screen`: 屏幕支持标记（整数：`0`=无屏幕，`1`=有屏幕）
  - 示例：`1`

#### 2.1.3 请求头
建立连接时需设置以下 HTTP 头：
```
Authorization: Bearer {ACCESS_TOKEN}
Protocol-Version: 1
Device-Id: {MAC_ADDRESS}
```

**说明**：
- `Authorization`: Bearer token，从 `CONFIG_WEBSOCKET_ACCESS_TOKEN` 获取
- `Protocol-Version`: 固定为 "1"
- `Device-Id`: 设备 MAC 地址（格式：`XX:XX:XX:XX:XX:XX`）

### 2.2 消息格式

#### 2.2.1 客户端发送消息格式
所有文本消息均为 JSON 格式，包含以下字段：

**基本结构**：
```json
{
  "session_id": "{SESSION_ID}",
  "type": "{MESSAGE_TYPE}",
  ...
}
```

**用户输入消息**（模拟语音输入转文本）：
根据代码分析，用户输入可以通过以下方式发送：

**方式1：直接发送文本消息**（推荐用于测试）
```json
{
  "session_id": "{SESSION_ID}",
  "type": "start_listen",
  "data": {
    "format": "opus",
    "tts_format": "opus",
    "playTag": 1,
    "state": "asr",
    "mode": "realtime",
    "text": "你好啊，我今天想去故宫玩"
  }
}
```

**方式2：发送音频数据**（二进制帧）
- 通过 WebSocket 二进制帧发送 Opus 编码的音频数据
- 需要先发送 `start_listen` 消息启动监听

#### 2.2.2 服务器响应消息格式

**STT (Speech-to-Text) 响应**：
```json
{
  "type": "stt",
  "text": "你好啊，我今天想去故宫玩"
}
```

**TTS (Text-to-Speech) 响应**：
```json
{
  "type": "tts",
  "state": "start"
}
```

```json
{
  "type": "tts",
  "state": "sentence_start",
  "text": "好的，我来为您查询故宫相关信息..."
}
```

```json
{
  "type": "tts",
  "state": "stop"
}
```

**LLM 响应**：
```json
{
  "type": "llm",
  "emotion": "happy",
  "text": "😀"
}
```

**Auth 响应**：
```json
{
  "type": "auth",
  "code": 0,
  "data": {
    "session_id": "{SESSION_ID}",
    "ota_url": "...",
    ...
  }
}
```

### 2.3 连接流程

1. **建立 WebSocket 连接**
   - 使用完整的 URL 和查询参数
   - 设置必要的 HTTP 头
   - 等待连接成功

2. **等待服务器响应**
   - 连接成功后，服务器会发送 `auth` 类型的消息
   - 从响应中提取 `session_id`

3. **发送用户消息**
   - 使用获取到的 `session_id` 发送用户输入消息
   - 等待服务器 STT 确认
   - 等待服务器 LLM/TTS 响应

4. **接收服务器响应**
   - 监听所有 JSON 消息
   - 记录响应时间
   - 验证响应完整性

## 3. 测试指标设计

### 3.1 连接性能指标

| 指标名称 | 说明 | 计算方法 |
|---------|------|---------|
| **连接建立时间** | 从发起连接到连接成功的时间 | `connect_time = connect_end - connect_start` |
| **连接成功率** | 成功建立的连接数 / 总连接数 | `success_rate = success_count / total_count` |
| **连接失败率** | 失败的连接数 / 总连接数 | `failure_rate = failure_count / total_count` |
| **连接失败原因分布** | 统计各种失败原因的数量和比例 | - |

### 3.2 消息传输性能指标

| 指标名称 | 说明 | 计算方法 |
|---------|------|---------|
| **消息发送时间** | 从发送消息到消息发送完成的时间 | `send_time = send_end - send_start` |
| **消息响应时间 (RTT)** | 从发送消息到收到第一个响应的时间 | `response_time = first_response_time - send_time` |
| **完整响应时间** | 从发送消息到收到完整响应（TTS结束）的时间 | `complete_time = tts_stop_time - send_time` |
| **消息吞吐量** | 每秒发送的消息数 | `throughput = message_count / total_time` |
| **消息大小** | 发送和接收消息的平均大小 | `avg_size = total_bytes / message_count` |

### 3.3 服务器响应质量指标

| 指标名称 | 说明 | 计算方法 |
|---------|------|---------|
| **STT 响应时间** | 从发送消息到收到 STT 响应的时间 | `stt_time = stt_response_time - send_time` |
| **LLM 响应时间** | 从收到 STT 到收到 LLM 响应的时间 | `llm_time = llm_response_time - stt_response_time` |
| **TTS 开始时间** | 从收到 LLM 到 TTS 开始的时间 | `tts_start_time = tts_start_time - llm_response_time` |
| **TTS 持续时间** | TTS 播放的总时长 | `tts_duration = tts_stop_time - tts_start_time` |
| **响应完整性** | 是否收到完整的响应序列 | `complete = has_stt && has_llm && has_tts_start && has_tts_stop` |

### 3.4 系统稳定性指标

| 指标名称 | 说明 | 计算方法 |
|---------|------|---------|
| **连接断开率** | 测试过程中断开的连接数 / 总连接数 | `disconnect_rate = disconnect_count / total_count` |
| **错误率** | 发生错误的请求数 / 总请求数 | `error_rate = error_count / total_count` |
| **超时率** | 超时的请求数 / 总请求数 | `timeout_rate = timeout_count / total_count` |
| **重连次数** | 连接断开后重连的总次数 | - |
| **内存使用** | 测试过程中内存使用情况 | - |
| **CPU 使用率** | 测试过程中 CPU 使用情况 | - |

### 3.5 并发性能指标

| 指标名称 | 说明 | 计算方法 |
|---------|------|---------|
| **并发连接峰值** | 同时建立的连接数峰值 | - |
| **并发消息峰值** | 同时处理的消息数峰值 | - |
| **QPS (Queries Per Second)** | 每秒处理的查询数 | `qps = total_queries / total_time` |
| **P95 响应时间** | 95% 的请求响应时间低于此值 | - |
| **P99 响应时间** | 99% 的请求响应时间低于此值 | - |
| **平均响应时间** | 所有请求的平均响应时间 | `avg_response = sum(response_time) / count` |

## 4. 测试数据记录

### 4.1 日志格式

#### 4.1.1 连接日志
```
[CONNECTION] {timestamp} | Connection #{id} | Status: {status} | Duration: {duration}ms | URL: {url}
```

#### 4.1.2 消息日志
```
[MESSAGE] {timestamp} | Connection #{id} | Type: {type} | Direction: {send|recv} | Size: {size}bytes | Duration: {duration}ms
```

#### 4.1.3 响应日志
```
[RESPONSE] {timestamp} | Connection #{id} | Message Type: {message_type} | STT Time: {stt_time}ms | LLM Time: {llm_time}ms | TTS Time: {tts_time}ms | Total: {total_time}ms
```

#### 4.1.4 错误日志
```
[ERROR] {timestamp} | Connection #{id} | Error Type: {error_type} | Error Message: {error_message} | Stack Trace: {stack_trace}
```

#### 4.1.5 统计日志
```
[STATISTICS] {timestamp} | Total Connections: {total} | Active: {active} | Success: {success} | Failed: {failed} | QPS: {qps} | Avg Response: {avg}ms | P95: {p95}ms | P99: {p99}ms
```

### 4.2 数据输出格式

#### 4.2.1 CSV 格式（用于分析）
文件：`test_results_{timestamp}.csv`

列定义：
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
- `error_type`: 错误类型（如果有）
- `error_message`: 错误消息（如果有）

#### 4.2.2 JSON 格式（用于详细分析）
文件：`test_results_{timestamp}.json`

结构：
```json
{
  "test_info": {
    "start_time": "2024-01-01T00:00:00Z",
    "end_time": "2024-01-01T00:05:00Z",
    "duration": 300,
    "concurrent_connections": 100,
    "test_message": "你好啊，我今天想去故宫玩"
  },
  "summary": {
    "total_connections": 100,
    "successful_connections": 95,
    "failed_connections": 5,
    "total_messages": 95,
    "successful_messages": 90,
    "failed_messages": 5,
    "avg_response_time": 1234.5,
    "p95_response_time": 2345.6,
    "p99_response_time": 3456.7,
    "qps": 0.5
  },
  "connections": [
    {
      "id": 1,
      "connect_time": 123.4,
      "status": "success",
      "messages": [
        {
          "send_time": 456.7,
          "stt_time": 234.5,
          "llm_time": 567.8,
          "tts_start_time": 123.4,
          "tts_duration": 3456.7,
          "total_time": 4782.3,
          "complete": true
        }
      ]
    }
  ]
}
```

## 5. 测试脚本设计

### 5.1 技术选型

**推荐方案**：
- **语言**: Python 3.8+
- **WebSocket 库**: `websockets` 或 `websocket-client`
- **并发框架**: `asyncio` (异步并发) 或 `concurrent.futures` (线程池)
- **HTTP 客户端**: `aiohttp` (异步) 或 `requests` (同步)
- **日志库**: `logging` + `json`
- **数据分析**: `pandas` (用于 CSV 分析)
- **可视化**: `matplotlib` 或 `plotly` (可选)

**备选方案**：
- **Node.js**: 使用 `ws` 库，原生支持异步
- **Go**: 使用 `gorilla/websocket`，性能优异

### 5.2 脚本架构

```
performance/
├── websocket_performance_test_design.md  # 本文档
├── test_runner.py                       # 主测试脚本
├── websocket_client.py                  # WebSocket 客户端封装
├── metrics_collector.py                  # 指标收集器
├── logger.py                             # 日志记录器
├── config.py                             # 配置文件
├── utils.py                              # 工具函数
├── requirements.txt                      # Python 依赖
├── results/                              # 测试结果目录
│   ├── logs/                            # 日志文件
│   ├── csv/                             # CSV 结果
│   └── json/                             # JSON 结果
└── README.md                             # 使用说明
```

### 5.3 核心功能模块

#### 5.3.1 WebSocket 客户端封装 (`websocket_client.py`)
- 连接管理（建立、重连、关闭）
- 消息发送和接收
- 错误处理
- 心跳保活（可选）

#### 5.3.2 指标收集器 (`metrics_collector.py`)
- 实时指标收集
- 统计计算（平均值、P95、P99等）
- 数据导出（CSV、JSON）

#### 5.3.3 日志记录器 (`logger.py`)
- 分级日志（DEBUG、INFO、WARNING、ERROR）
- 文件输出和标准输出
- 日志轮转

#### 5.3.4 测试运行器 (`test_runner.py`)
- 并发控制
- 测试流程编排
- 结果汇总和报告生成

## 6. 测试执行计划

### 6.1 测试环境准备

**硬件要求**：
- CPU: 4核心以上
- 内存: 8GB 以上
- 网络: 稳定的网络连接（建议带宽 100Mbps+）

**软件要求**：
- Python 3.8+
- 依赖库安装（见 `requirements.txt`）

**配置准备**：
- WebSocket 服务器地址
  - WS: `ws://toyaiws.spacechaintech.com:8081`
  - WSS: `wss://toyaiws.spacechaintech.com`
- Access Token（用于 Authorization 头）
- 设备信息（SN、Sign、Board ID 等）
  - 示例设备信息：
    - SN: `FC012C2EA0A0`
    - Sign: `c61505cccb8dc83d8e67450cbd4f32c4`
    - Board ID: `TKAI_BOARD_03_4G_VB6824_EYE_ST7789`
    - Firmware Version: `0.0.1`
    - Firmware Version Code: `20250908001`
    - Board Type: `wifi`
    - Screen: `1`
- 测试参数（并发数、消息内容等）

### 6.2 测试步骤

1. **环境检查**
   - 验证网络连接
   - 验证服务器可访问性
   - 检查依赖库

2. **预热测试**（可选）
   - 少量连接测试（5-10个）
   - 验证连接和消息流程正常

3. **正式测试**
   - 启动 100 个并发连接
   - 每个连接发送测试消息
   - 收集所有指标数据
   - 持续监控系统状态

4. **结果分析**
   - 生成统计报告
   - 分析性能瓶颈
   - 生成可视化图表（可选）

### 6.3 测试时间规划

- **准备时间**: 10-15 分钟
- **预热测试**: 2-3 分钟
- **正式测试**: 5-10 分钟（取决于服务器响应速度）
- **结果分析**: 10-15 分钟

**总计**: 约 30-45 分钟

## 7. 风险控制

### 7.1 潜在风险

1. **服务器过载**
   - 风险：100个并发连接可能导致服务器过载
   - 缓解：监控服务器状态，必要时降低并发数

2. **网络问题**
   - 风险：网络不稳定导致连接失败
   - 缓解：使用稳定的网络环境，记录网络错误

3. **资源耗尽**
   - 风险：测试客户端资源（内存、文件句柄）耗尽
   - 缓解：限制并发数，及时释放资源

4. **数据丢失**
   - 风险：测试数据未正确记录
   - 缓解：实时写入日志，定期备份

### 7.2 异常处理

- **连接失败**: 记录失败原因，重试机制（可选）
- **消息超时**: 设置超时阈值，记录超时情况
- **响应错误**: 记录错误详情，继续其他测试
- **程序崩溃**: 异常捕获，保存已收集数据

## 8. 扩展测试场景

### 8.1 不同消息长度测试
- 短消息（10字以内）
- 中等消息（10-50字）
- 长消息（50-200字）
- 超长消息（200字以上）

### 8.2 不同并发级别测试
- 10并发
- 50并发
- 100并发
- 200并发
- 500并发（压力测试）

### 8.3 长时间稳定性测试
- 持续运行 1 小时
- 持续运行 24 小时
- 监控内存泄漏
- 监控连接稳定性

### 8.4 不同网络环境测试
- 本地网络（低延迟）
- 公网环境（正常延迟）
- 高延迟网络（模拟）
- 不稳定网络（模拟丢包）

## 9. 报告模板

### 9.1 执行摘要
- 测试目的
- 测试时间
- 测试结果概述
- 关键指标汇总

### 9.2 详细结果
- 连接性能分析
- 消息传输性能分析
- 服务器响应质量分析
- 系统稳定性分析
- 并发性能分析

### 9.3 问题发现
- 发现的问题列表
- 问题严重程度
- 问题复现步骤
- 建议修复方案

### 9.4 结论和建议
- 性能评估结论
- 优化建议
- 后续测试计划

## 10. 附录

### 10.1 参考代码位置
- WebSocket 协议实现: `main/protocols/websocket_protocol.cc`
- 协议头文件: `main/protocols/websocket_protocol.h`
- 协议基类: `main/protocols/protocol.h` / `main/protocols/protocol.cc`
- WebSocket 文档: `docs/websocket.md`

### 10.2 配置参数说明

**代码配置参数**：
- `WS_SERVER_HOST`: WebSocket 服务器地址（WS），定义在 `main/application.h`
  - 默认值：`ws://toyaiws.spacechaintech.com:8081`
- `WSS_SERVER_HOST`: WebSocket 服务器地址（WSS），定义在 `main/application.h`
  - 默认值：`wss://toyaiws.spacechaintech.com`
- `CONFIG_WEBSOCKET_ACCESS_TOKEN`: 访问令牌（Kconfig 配置）
- `CONFIG_APP_SIGN_KEY`: 应用签名密钥（用于生成设备签名，Kconfig 配置）

**URL 查询参数**（实际连接时使用）：
- `sn`: 设备序列号（12位大写十六进制，基于 MAC 地址）
- `sign`: 设备签名（32位小写十六进制 MD5 哈希：MD5(sn + CONFIG_APP_SIGN_KEY)）
- `platform`: 固定值 `hw`
- `bid`: 板子ID（从板子配置JSON获取）
- `fv`: 固件版本号（格式：x.y.z）
- `fvc`: 固件版本代码（日期格式字符串）
- `strategy_id`: OTA策略ID（整数，默认0）
- `uid`: 设备UID（整数，未绑定时为0）
- `board_type`: 板子类型（`wifi` 或 `ml307`）
- `recover`: 出厂模式标记（0=正常，1=出厂模式）
- `enableP3`: 音频播放支持（固定值：2）
- `tool`: 工具标识（固定值：idf）
- `screen`: 屏幕支持标记（0=无屏幕，1=有屏幕）

**实际连接示例**：
```
ws://toyaiws.spacechaintech.com:8081/?sn=FC012C2EA0A0&sign=c61505cccb8dc83d8e67450cbd4f32c4&platform=hw&bid=TKAI_BOARD_03_4G_VB6824_EYE_ST7789&fv=0.0.1&fvc=20250908001&strategy_id=0&uid=0&board_type=wifi&recover=0&enableP3=2&tool=idf&screen=1
```

### 10.3 相关文档
- 项目分析文档: `docs/project_analysis.md`
- WebSocket 协议文档: `docs/websocket.md`

---

**文档版本**: 1.0  
**创建日期**: 2024-12-XX  
**最后更新**: 2024-12-XX

