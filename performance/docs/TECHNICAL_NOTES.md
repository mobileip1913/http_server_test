# 技术实现说明

本文档合并了所有技术实现相关的说明，包括设备行为分析、服务器处理机制、音频格式问题等。

## 目录

1. [设备发送方式分析](#设备发送方式分析)
2. [服务器音频处理机制](#服务器音频处理机制)
3. [音频格式和编码](#音频格式和编码)
4. [代码优化总结](#代码优化总结)

---

## 设备发送方式分析

### 设备实际发送流程

**音频采集和编码**：
- `AudioLoop` 每 **10ms** 调用一次 `OnAudioInput()`
- `OnAudioInput()` 中每 **30ms** 读取一次 PCM 数据（480 samples = `30 * 16000 / 1000`）
- 对于 `CONFIG_USE_AUDIO_CODEC_ENCODE_OPUS` 模式：
  - `ReadAudio(opus, 16000, 30 * 16000 / 1000)` 读取的是**已经编码好的Opus数据**
  - 每次读取约30ms的Opus数据包（大小可变，通常20-400字节）
  - 直接加入 `audio_send_queue_` 队列
- 对于非 `CONFIG_USE_AUDIO_CODEC_ENCODE_OPUS` 模式：
  - PCM 数据通过 `audio_processor_->OnOutput()` 传递给 `opus_encoder_->Encode()`
  - Opus 编码器每 **60ms** 生成一个 Opus 包（`OPUS_FRAME_DURATION_MS = 60`）
  - 编码后的 Opus 包被加入 `audio_send_queue_` 队列

**发送逻辑（MainLoop）**：
```cpp
if (bits & SEND_AUDIO_EVENT) {
    std::unique_lock<std::mutex> lock(mutex_);
    auto packets = std::move(audio_send_queue_);  // 取出队列中所有包
    for (auto& opus : packets) {
        if(protocol_){
            protocol_->SendAudio(std::move(opus));  // 连续发送，没有间隔！
        }
    }
}
```

**WebSocket发送实现**：
```cpp
void WebsocketProtocol::SendAudio(const std::vector<uint8_t>& data) {
    if (websocket_ == nullptr || !is_connected_) {
        return;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    websocket_->Send(data.data(), data.size(), true);  // 二进制发送
}
```

**关键点**：
- ✅ 设备是**批量连续发送**队列中的所有 Opus 包，**没有间隔**
- ✅ 每个 Opus 包是独立的帧（30ms或60ms，取决于编码模式）
- ✅ 包大小是**可变的**（取决于音频内容，通常20-400字节）
- ✅ 发送方式是**二进制**（`websocket_->Send(data.data(), data.size(), true)`）

### 测试脚本实现

**音频处理**：
- ✅ 使用 Opus 解码器智能分割连续的 Opus 数据包
- ✅ 将连续的 Opus 数据分割为多个独立的 60ms 帧
- ✅ 从 Ogg 容器直接提取原始 Opus 包（优先）
- ✅ 如果无法提取，则从 PCM 重新编码为独立的 Opus 包

**发送逻辑**：
```python
async def send_audio_frames(self, audio_frames: List[bytes], frame_interval_ms: float = 0.0):
    # 批量连续发送所有帧（模拟 MainLoop 的行为）
    for frame in audio_frames:
        await self.websocket.send(frame)  # 二进制发送，没有间隔
```

### 对比总结

| 项目 | 设备行为 | 测试脚本 | 状态 |
|------|---------|---------|------|
| 音频格式 | 多个独立的Opus包 | 多个独立的Opus包 | ✅ 一致 |
| 包大小 | 可变（20-400字节） | 可变（20-400字节） | ✅ 一致 |
| 发送方式 | 批量连续发送，无间隔 | 批量连续发送，无间隔 | ✅ 一致 |
| WebSocket格式 | 二进制（`true`） | 二进制（bytes） | ✅ 一致 |
| 消息格式 | 不包含 `vad_side` | 不包含 `vad_side` | ✅ 一致 |

---

## 服务器音频处理机制

### WebSocket消息处理（`ws_server/sky/kernel/sky.js`）

```javascript
ws.on("message", async (data) => {
    if (message.startsWith("{") && message.endsWith("}")) {
      // JSON消息
      const req = new Msg(JSON.parse(message));
      this.handleEvent(platform, req, baseEevent.context);
    }else{
      // 二进制音频数据！发送到 iat_speak 事件
      const req = new Msg({
          type: "iat_speak",
          data: data,  // 直接传递Buffer，data是原始Buffer
      });
      this.handleEvent(platform, req, baseEevent.context);
    }
});
```

**关键点**：
- 每个WebSocket消息的二进制数据会被当作一个独立的音频数据包
- 没有大小限制，直接传递原始Buffer

### 音频解码处理（`ws_server/app/event/hw/iat_speak.js`）

```javascript
const decoder = new OpusEncoder(16000, 1);  // @discordjs/opus

async handle(req) {
    const binaryData = req._data;  // 获取Buffer

    // 如果是Opus格式且state==asr
    if (this.context["iat_format"] == "opus" && 
        (this.context["state"] == "asr" || ...)) {
      const pcmData = decoder.decode(binaryData);  // 解码整个Buffer
      this.context.iatService.sendAudio(pcmData);
    }
}
```

**关键发现**：
- `@discordjs/opus` 的 `decoder.decode()` 方法**只能解码单个Opus包**
- 如果传入连续的多个Opus包，解码会失败或只解码第一个包
- **每个WebSocket消息必须是一个完整的、独立的Opus包**

### IAT服务发送（`ws_server/app/lib/iat/xunfei_iat.js`）

```javascript
sendPcmFrame = (data) => {
    // 将PCM数据转为base64，发送给讯飞IAT
    let frameDataSection = {
      status: this.iat_status,
      format: "audio/L16;rate=16000",
      audio: data.toString("base64"),  // PCM转为base64
      encoding: "raw",
    };
    this.iat_ws.send(JSON.stringify(frame));
}
```

### 服务端VAD分支处理

当 `mode == "auto"` 时：
- `is_vad_chat = true`
- 如果 `vad_side` 为 `undefined`（旧代码不支持此参数），会进入服务端VAD分支
- 如果生产环境没有ASR工作节点，音频会被丢弃

**解决方案**：
- 测试代码已移除 `vad_side` 参数，完全模拟硬件行为
- 需要确认生产环境是否有ASR工作节点

---

## 音频格式和编码

### 音频格式参数

- **采样率**: 16kHz
- **声道**: 单声道
- **帧长度**: 60ms (960 samples)
- **编码格式**: Opus
- **编码参数**: 32kbps, complexity 3

### 音频生成流程

1. **使用讯飞TTS API生成PCM格式**
   - 文本："你好啊，我想去故宫"
   - 输出格式：PCM，16kHz，单声道

2. **使用FFmpeg编码为Opus**
   ```bash
   ffmpeg -f s16le -ar 16000 -ac 1 -i input.pcm \
          -c:a libopus -b:a 32k -frame_duration 60 output.opus
   ```
   - 参数：`-c:a libopus -b:a 32k -frame_duration 60`
   - 输出：Ogg Opus 容器格式

3. **提取或重新编码为原始Opus包**
   - 优先：从Ogg容器直接提取原始Opus包
   - 备选：转换为PCM，然后重新编码为独立的Opus包

### 问题解决历程

#### 问题1: 剩余PCM数据丢失
**问题**: `_generate_raw_opus_from_pcm` 只处理完整的1920字节帧，剩余数据被丢弃  
**解决**: ✅ 添加静音填充，确保剩余数据也被编码

#### 问题2: 编码参数不匹配
**问题**: 客户端编码参数与服务器期望不一致  
**解决**: ✅ 设置 `bitrate=32000`, `complexity=3`

#### 问题3: Ogg容器格式问题
**问题**: FFmpeg生成的是Ogg容器，不是原始Opus包  
**解决**: ✅ 从Ogg容器提取原始Opus包，或从PCM重新编码

#### 问题4: 音频质量问题
**问题**: 生成的Opus音频有杂音  
**解决**: ✅ 改用PCM生成 + FFmpeg编码的方式

---

## 代码优化总结

### 1. 监听模式选择 ✅

**优化**：
- 添加了 `LISTENING_MODE` 配置项（默认 `auto`）
- 支持三种模式：
  - `realtime`: 持续监听模式（AlwaysOn）- 不会自动停止
  - `auto`: 自动停止模式（AutoStop）- 服务器通过VAD自动检测并处理（**推荐用于测试**）
  - `manual`: 手动停止模式（ManualStop）- 必须发送 `stop_listen`

### 2. stop_listen 消息发送逻辑 ✅

**优化**：
- 根据监听模式智能决定是否发送 `stop_listen`：
  - `auto`: 可选发送（服务器可能自动检测VAD，但发送可以确保服务器开始处理）
  - `manual`: 必须发送
  - `realtime`: 不发送（持续监听）

### 3. 消息格式完全对齐硬件 ✅

**优化**：
- `start_listen` 消息格式与硬件代码完全一致
- 不包含 `vad_side` 参数（与 `main/protocols/protocol.cc:86` 一致）

### 4. HTTP 头优化 ✅

**优化**：
- `Device-Id`: 从 SN 正确生成 MAC 地址格式（FC:01:2C:2E:A0:A0）
- `Protocol-Version`: 设置为 "1"
- `Authorization`: 可选，如果设置了 `WEBSOCKET_ACCESS_TOKEN` 环境变量则添加

### 5. 消息接收处理完善 ✅

**新增支持的消息类型**：
- `hello`: 服务器 hello 消息
- `abort`: 服务器主动打断
- `interrupt`: 服务器主动中断
- `iot`: IoT 控制消息
- `actions`: 服务器下发的动作规则
- `emoji`: 表情消息

### 6. 日志优化 ✅

**优化**：
- 大幅减少日志输出（从 3500+ 行减少到 137 行，减少约 96%）
- 移除冗余的调试日志
- 保留关键信息（STT/LLM/TTS 响应内容）
- 添加诊断日志（连接状态、接收任务状态）

---

## 关键原则

1. **每个WebSocket消息必须是一个完整的、独立的Opus包**
2. **批量连续发送，没有间隔**（模拟MainLoop行为）
3. **消息格式必须与硬件代码完全一致**（不包含 `vad_side` 参数）
4. **音频编码参数必须匹配**（32kbps, complexity 3, 60ms帧）

---

**最后更新**: 2025-11-05

**注意**: 本文档位于 `performance/docs/` 目录下

