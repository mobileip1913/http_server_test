# IoT端发送 vs 服务端接收代码对比分析

## 概述

本文档对比分析 IoT 端（主项目）的音频发送代码和服务端（ws_server）的音频接收代码，找出可能导致语音识别失败的关键差异。

---

## 一、IoT端发送代码分析

### 1.1 Opus 编码参数（`main/application.cc`）

```cpp
// 编码器初始化（第486行）
opus_encoder_ = std::make_unique<OpusEncoderWrapper>(
    AUDIO_SAMPLE_RATE,  // 16000 Hz
    1,                  // 单声道
    OPUS_FRAME_DURATION_MS  // 60ms
);

// 复杂度设置（第489-494行）
if (board.GetBoardType() == "ml307") {
    opus_encoder_->SetComplexity(5);  // ML307板：复杂度5
} else {
    opus_encoder_->SetComplexity(3);  // WiFi板：复杂度3
}
```

**关键参数**：
- **采样率**：16000 Hz
- **声道数**：1（单声道）
- **帧长度**：60ms（`OPUS_FRAME_DURATION_MS = 60`）
- **复杂度**：WiFi板=3，ML307板=5
- **比特率**：未明确设置（使用默认值）

### 1.2 音频编码模式

IoT端有两种编码模式：

#### 模式1：`CONFIG_USE_AUDIO_CODEC_ENCODE_OPUS`（硬件编码）

```cpp
// main/application.cc 第1360-1376行
#ifdef CONFIG_USE_AUDIO_CODEC_ENCODE_OPUS
    std::vector<uint8_t> opus;
    if (!ReadAudio(opus, 16000, 30 * 16000 / 1000)) {  // 读取30ms的Opus数据
        return;
    }
    // 直接使用硬件编码的Opus数据，每30ms一个包
    audio_send_queue_.emplace_back(std::move(opus));
#endif
```

**特点**：
- 直接从硬件 codec 读取**已编码的 Opus 数据**
- 每次读取 **30ms** 的 Opus 包（不是60ms）
- 包大小可变（取决于音频内容）

#### 模式2：软件编码（非 `CONFIG_USE_AUDIO_CODEC_ENCODE_OPUS`）

```cpp
// main/application.cc 第660-678行
audio_processor_->OnOutput([this](std::vector<int16_t>&& data) {
    opus_encoder_->Encode(std::move(data), [this](std::vector<uint8_t>&& opus) {
        // 使用软件编码器，每60ms一个包
        audio_send_queue_.emplace_back(std::move(opus));
    });
});
```

**特点**：
- PCM 数据通过软件 Opus 编码器编码
- 每 **60ms** 生成一个 Opus 包
- 使用配置的复杂度（3或5）

### 1.3 音频发送流程（`main/protocols/websocket_protocol.cc`）

```cpp
// 第30-36行：SendAudio 方法
void WebsocketProtocol::SendAudio(const std::vector<uint8_t>& data) {
    if (websocket_ == nullptr || !is_connected_) {
        return;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    websocket_->Send(data.data(), data.size(), true);  // 二进制发送
}
```

**关键点**：
- ✅ 每个 `SendAudio()` 调用对应**一个独立的 WebSocket 二进制消息**
- ✅ 每个消息包含**一个独立的 Opus 包**（30ms 或 60ms）
- ✅ 使用 `true` 参数表示二进制发送

### 1.4 批量发送逻辑（`main/application.cc`）

```cpp
// MainLoop 中的发送逻辑（参考文档）
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

**关键点**：
- ✅ **批量连续发送**队列中的所有 Opus 包
- ✅ **没有间隔**，连续发送
- ✅ 每个包作为独立的 WebSocket 消息

---

## 二、服务端接收代码分析

### 2.1 WebSocket 消息接收（`ws_server/sky/kernel/sky.js`）

```javascript
// 第138-157行
ws.on("message", async (data) => {
    let message = data;
    if (Buffer.isBuffer(data)) {
        message = data.toString('utf8');  // 将 Buffer 转为字符串
    }

    if (message.startsWith("{") && message.endsWith("}")) {
        // JSON消息
        const req = new Msg(JSON.parse(message));
        this.handleEvent(platform, req, baseEevent.context);
    } else {
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
- ✅ 每个 WebSocket 消息的二进制数据被当作**一个独立的音频数据包**
- ✅ 直接传递原始 Buffer，没有大小限制

### 2.2 Opus 解码处理（`ws_server/app/event/hw/iat_speak.js`）

```javascript
// 第7-9行：初始化解码器
const { OpusEncoder } = require("@discordjs/opus");
const decoder = new OpusEncoder(16000, 1);  // 16kHz, 单声道

// 第41-88行：处理音频数据
async handle(req) {
    const binaryData = req._data;  // 获取Buffer

    // 分支1：服务端 VAD 模式
    if (this.context["is_vad_chat"] && this.context["vad_side"] != "client_side_vad") {
        const pcmData = decoder.decode(binaryData);
        this.context.iatService.sendAudio(pcmData);
    }
    // 分支2：Opus 格式 + state == "asr"（正常路径）
    else if (
        this.context["iat_format"] == "opus" &&
        (this.context["state"] == "asr" || 
         this.context["state"] == "detect" || 
         this.context["state"] == "double_detect")
    ) {
        const pcmData = decoder.decode(binaryData);  // ⚠️ 没有错误处理！
        this.context.iatService.sendAudio(pcmData);
    }
    // 分支3：其他 Opus 格式（兜底路径，使用文件转换）
    else if (this.context["iat_format"] == "opus") {
        // 使用 tkai_opus 工具进行文件转换
        saveBufferToFile(binaryData, tmpOpusFile);
        opusToPcm(tmpOpusFile, tmpPcmFile);
        const pcmData = fs.readFileSync(tmpPcmFile);
        this.context.iatService.sendAudio(pcmData);
    }
    // 分支4：PCM 格式
    else {
        this.context.iatService.sendAudio(binaryData);
    }
}
```

**关键发现**：
- ⚠️ **没有 try-catch 错误处理**：如果 `decoder.decode()` 失败，会抛出异常，导致后续处理中断
- ⚠️ **`@discordjs/opus` 的限制**：`decoder.decode()` 只能解码**单个、完整的 Opus 包**
- ✅ 如果解码失败，应该进入分支3（文件转换），但当前代码没有这个机制

---

## 三、关键差异对比

| 项目 | IoT端（发送） | 服务端（接收） | 是否匹配 |
|------|--------------|---------------|---------|
| **Opus 采样率** | 16000 Hz | 16000 Hz | ✅ 匹配 |
| **声道数** | 1（单声道） | 1（单声道） | ✅ 匹配 |
| **帧长度** | 30ms（硬件编码）或 60ms（软件编码） | 未限制 | ✅ 匹配 |
| **复杂度** | WiFi=3, ML307=5 | 未验证 | ⚠️ 可能不匹配 |
| **比特率** | 未明确设置（默认） | 未验证 | ⚠️ 可能不匹配 |
| **发送方式** | 每个包作为独立的 WebSocket 二进制消息 | 每个消息被当作一个 Opus 包 | ✅ 匹配 |
| **错误处理** | N/A | ❌ **没有 try-catch** | ❌ **不匹配** |
| **解码器** | N/A | `@discordjs/opus` | ✅ 标准库 |

---

## 四、潜在问题分析

### 4.1 问题1：解码失败没有错误处理（最严重）

**问题**：
- 服务端 `decoder.decode(binaryData)` 如果失败会抛出异常
- 没有 try-catch，导致异常中断后续处理
- 即使 Opus 包格式正确，如果解码器状态异常也可能失败

**影响**：
- 音频数据无法解码为 PCM
- IAT 服务收不到 PCM 数据
- 导致识别结果为空

**解决方案**：
```javascript
try {
    const pcmData = decoder.decode(binaryData);
    this.context.iatService.sendAudio(pcmData);
} catch (error) {
    Log.error(`Opus decode failed: ${error.message}, falling back to file conversion`);
    // 降级到文件转换路径
    // ... 文件转换代码
}
```

### 4.2 问题2：Opus 编码参数可能不匹配

**问题**：
- IoT端使用复杂度3（WiFi）或5（ML307）
- 测试脚本使用复杂度3，但可能比特率不同
- 如果编码参数不匹配，解码可能失败

**影响**：
- 解码器可能无法正确解码
- 即使解码成功，音频质量可能下降

**验证方法**：
- 对比设备实际发送的 Opus 包格式
- 检查测试脚本生成的 Opus 包格式

### 4.3 问题3：帧长度不一致

**问题**：
- IoT端硬件编码模式：30ms 包
- IoT端软件编码模式：60ms 包
- 测试脚本：60ms 包

**影响**：
- 如果服务端期望特定帧长度，可能有问题
- 但 `@discordjs/opus` 应该支持可变帧长度

**验证**：
- 确认设备实际使用的编码模式
- 确认服务端是否对帧长度有要求

---

## 五、ws_server vs ws_server1 对比

### 5.1 `iat_speak.js` 对比

**结果**：两个版本**完全相同**，没有差异。

### 5.2 `sky.js` 对比

**结果**：两个版本**完全相同**，没有差异。

### 5.3 其他关键文件

需要进一步检查其他文件是否有差异，但核心的音频处理逻辑应该是一致的。

---

## 六、测试脚本 vs IoT端对比

### 6.1 编码参数对比

| 参数 | IoT端 | 测试脚本 | 是否匹配 |
|------|-------|---------|---------|
| 采样率 | 16000 Hz | 16000 Hz | ✅ |
| 声道数 | 1 | 1 | ✅ |
| 帧长度 | 30ms 或 60ms | 60ms | ⚠️ 可能不匹配 |
| 复杂度 | 3（WiFi）或 5（ML307） | 3 | ⚠️ 可能不匹配 |
| 比特率 | 默认 | 32kbps | ⚠️ 可能不匹配 |

### 6.2 发送方式对比

| 项目 | IoT端 | 测试脚本 | 是否匹配 |
|------|-------|---------|---------|
| 发送方式 | 每个包作为独立的 WebSocket 消息 | 每个包作为独立的 WebSocket 消息 | ✅ |
| 发送间隔 | 无间隔，批量连续发送 | 无间隔，批量连续发送 | ✅ |
| 二进制发送 | `true` | 自动识别为二进制 | ✅ |

---

## 七、推荐解决方案

### 7.1 立即修复：添加错误处理（优先级最高）

在 `ws_server/app/event/hw/iat_speak.js` 中添加 try-catch：

```javascript
else if (
  this.context["iat_format"] == "opus" &&
  (this.context["state"] == "asr" || 
   this.context["state"] == "detect" || 
   this.context["state"] == "double_detect")
) {
  try {
    const pcmData = decoder.decode(binaryData);
    this.context.iatService.sendAudio(pcmData);
  } catch (error) {
    Log.error(`Opus decode failed for ${binaryData.length} bytes: ${error.message}`);
    // 降级到文件转换路径
    const tmpFileName = generateRandomString(16);
    const tmpOpusFile = path.join("/tmp", tmpFileName + ".opus");
    const tmpPcmFile = path.join("/tmp", tmpFileName + ".pcm");
    try {
      saveBufferToFile(binaryData, tmpOpusFile);
      opusToPcm(tmpOpusFile, tmpPcmFile);
      const pcmData = fs.readFileSync(tmpPcmFile);
      this.context.iatService.sendAudio(pcmData);
    } finally {
      if (fs.existsSync(tmpOpusFile)) fs.unlinkSync(tmpOpusFile);
      if (fs.existsSync(tmpPcmFile)) fs.unlinkSync(tmpPcmFile);
    }
  }
}
```

### 7.2 优化测试脚本：匹配设备编码参数

1. **确认设备实际编码模式**：
   - 检查设备是否使用 `CONFIG_USE_AUDIO_CODEC_ENCODE_OPUS`
   - 确认帧长度是 30ms 还是 60ms

2. **调整测试脚本编码参数**：
   - 如果设备使用复杂度5，测试脚本也应该使用5
   - 确认比特率是否匹配

### 7.3 添加详细日志

在关键位置添加日志：
- Opus 包大小和数量
- 解码成功/失败
- PCM 数据大小
- IAT 服务发送状态

---

## 八、总结

### 核心问题

1. **服务端缺少错误处理**：`decoder.decode()` 失败时没有 try-catch，导致静默失败
2. **编码参数可能不匹配**：测试脚本的编码参数可能与设备不一致
3. **帧长度可能不一致**：设备可能使用 30ms 包，测试脚本使用 60ms 包

### 最可能的原因

**服务端解码失败但没有错误处理**，导致：
- 解码异常被静默忽略
- IAT 服务收不到 PCM 数据
- 识别结果为空

### 建议

1. **立即修复**：在服务端添加 try-catch 错误处理
2. **验证**：检查设备实际编码参数，调整测试脚本
3. **监控**：添加详细日志，便于问题定位

