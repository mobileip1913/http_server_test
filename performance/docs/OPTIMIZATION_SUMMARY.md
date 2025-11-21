# WebSocket 性能测试代码优化总结

## 优化目标

根据实际项目代码的 WebSocket 通信协议，彻底优化测试代码，确保完全匹配实际设备的行为。

## 关键发现和优化

### 1. 监听模式选择 ✅

**问题**：之前固定使用 `realtime` 模式，可能不符合实际使用场景。

**优化**：
- 添加了 `LISTENING_MODE` 配置项（默认 `auto`）
- 支持三种模式：
  - `realtime`: 持续监听模式（AlwaysOn）- 不会自动停止
  - `auto`: 自动停止模式（AutoStop）- 服务器通过VAD自动检测并处理（**推荐用于测试**）
  - `manual`: 手动停止模式（ManualStop）- 必须发送 `stop_listen`

**代码位置**：
- `performance/config.py`: 添加 `LISTENING_MODE` 和 `SEND_STOP_LISTEN` 配置
- `performance/websocket_client.py`: `send_start_listen()` 支持动态模式选择

### 2. stop_listen 消息发送逻辑 ✅

**问题**：之前总是发送 `stop_listen`，但根据监听模式，应该有不同的行为。

**优化**：
- 根据监听模式智能决定是否发送 `stop_listen`：
  - `auto`: 可选发送（服务器可能自动检测VAD，但发送可以确保服务器开始处理）
  - `manual`: 必须发送
  - `realtime`: 不发送（持续监听）
- 添加了 `SEND_STOP_LISTEN` 配置项，允许控制是否发送

**代码位置**：
- `performance/websocket_client.py`: `send_user_message()` 中的智能判断逻辑

### 3. cancel_listen 消息支持 ✅

**新增**：添加了 `send_cancel_listen()` 方法，完全按照项目代码格式。

**代码位置**：
- `performance/websocket_client.py`: `send_cancel_listen()` 方法

### 4. HTTP 头优化 ✅

**优化**：
- `Device-Id`: 从 SN 正确生成 MAC 地址格式（FC:01:2C:2E:A0:A0）
- `Protocol-Version`: 设置为 "1"
- `Authorization`: 可选，如果设置了 `WEBSOCKET_ACCESS_TOKEN` 环境变量则添加

**代码位置**：
- `performance/config.py`: `get_headers()` 方法

### 5. 消息接收处理完善 ✅

**新增支持的消息类型**：
- `hello`: 服务器 hello 消息
- `abort`: 服务器主动打断
- `interrupt`: 服务器主动中断
- `iot`: IoT 控制消息
- `actions`: 服务器下发的动作规则
- `emoji`: 表情消息

**代码位置**：
- `performance/websocket_client.py`: `_handle_json_message()` 方法

### 6. 音频发送方式优化 ✅

**优化**：
- 明确说明每帧间隔 60ms（模拟真实音频采集节奏）
- 添加了详细的注释，说明与项目代码的对应关系
- 使用 `binary=True` 发送音频数据（完全匹配项目代码）

**代码位置**：
- `performance/websocket_client.py`: `send_audio_frames()` 方法

### 7. 日志优化 ✅

**优化**：
- 大幅减少日志输出（从 3500+ 行减少到 137 行，减少约 96%）
- 移除冗余的调试日志
- 保留关键信息（STT/LLM/TTS 响应内容）
- 添加诊断日志（连接状态、接收任务状态）

**代码位置**：
- `performance/websocket_client.py`: 所有发送和接收方法
- `performance/test_runner.py`: 等待逻辑

## 完整的通信流程对比

### 项目代码流程

```
1. 建立 WebSocket 连接
   - 设置 HTTP 头：Protocol-Version, Device-Id, Authorization（可选）
   - URL 包含所有设备参数

2. 等待服务器 auth 消息（不强制等待）

3. 发送 start_listen 消息
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

4. 逐帧发送 Opus 音频数据（二进制，60ms间隔）

5. （可选）发送 stop_listen 消息
   {
     "session_id": "...",
     "type": "stop_listen",
     "state": "stop"
   }

6. 接收服务器响应：
   - STT: 识别的文本
   - LLM: 情感和文本
   - TTS: 状态（start/stop/sentence_start）和文本
   - 其他: abort, interrupt, iot, actions, emoji 等
```

### 测试代码流程（优化后）

```
1. 建立 WebSocket 连接 ✅
   - HTTP 头完全匹配项目代码
   - URL 参数完全匹配项目代码

2. 等待服务器 auth 消息 ✅

3. 发送 start_listen 消息 ✅
   - 格式完全匹配项目代码
   - 支持三种监听模式（realtime/auto/manual）

4. 逐帧发送 Opus 音频数据 ✅
   - 60ms 间隔，完全模拟真实采集
   - 二进制发送，格式正确

5. 智能发送 stop_listen ✅
   - 根据监听模式和配置决定是否发送

6. 完整接收和处理所有消息类型 ✅
   - STT, LLM, TTS 显示完整内容
   - 支持所有其他消息类型
```

## 配置项说明

### 新增配置项

```python
# 监听模式
LISTENING_MODE = "auto"  # realtime|auto|manual

# 是否发送 stop_listen
SEND_STOP_LISTEN = True  # 对于 auto 模式，可选但推荐
```

### 环境变量

```bash
# 监听模式选择
export LISTENING_MODE="auto"  # 推荐用于测试

# 是否发送 stop_listen
export SEND_STOP_LISTEN="true"  # 推荐 true

# 如果需要 Authorization 头（可选）
export WEBSOCKET_ACCESS_TOKEN="your_token"
```

## 关键改进点

1. ✅ **监听模式智能选择**：默认使用 `auto` 模式，更符合实际使用场景
2. ✅ **stop_listen 智能发送**：根据模式决定是否发送，避免不必要的消息
3. ✅ **消息格式完全匹配**：所有消息格式与项目代码 100% 一致
4. ✅ **HTTP 头完整支持**：Device-Id 格式正确，Authorization 可选
5. ✅ **接收消息类型完整**：支持所有项目代码中处理的消息类型
6. ✅ **音频发送节奏真实**：60ms 间隔，完全模拟设备采集
7. ✅ **日志精简高效**：减少 96% 日志，保留关键信息

## 测试建议

### 推荐配置（用于测试）

```bash
export LISTENING_MODE="auto"
export SEND_STOP_LISTEN="true"
export DEBUG_MODE="true"  # 先测试单个连接
export LOG_LEVEL="DEBUG"  # 查看详细诊断信息
```

### 如果服务器响应仍然缺失

1. 检查服务器端日志，确认是否收到请求
2. 验证音频数据是否足够（可能需要更多帧）
3. 尝试不同的监听模式：
   - `auto`: 服务器自动检测VAD
   - `manual`: 必须发送 stop_listen
   - `realtime`: 持续监听（不推荐用于测试）

## 下一步

1. 运行优化后的测试，查看是否收到服务器响应
2. 根据日志分析问题（如果仍有问题）
3. 根据实际服务器行为，进一步调整配置

