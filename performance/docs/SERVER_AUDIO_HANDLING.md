# 服务器音频处理机制分析

## 服务器接收音频数据的方式

### 1. WebSocket消息处理（`ws_server/sky/kernel/sky.js`）

```javascript
ws.on("message", async (data) => {
    let message = data;
    if (Buffer.isBuffer(data)) {
        message = data.toString('utf8'); // 将 Buffer 转为字符串
    }

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

### 2. 音频解码处理（`ws_server/app/event/hw/iat_speak.js`）

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

### 3. IAT服务发送（`ws_server/app/lib/iat/xunfei_iat.js`）

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

## 设备发送方式

### 设备代码分析

```cpp
// MainLoop中批量发送
for (auto& opus : packets) {
    protocol_->SendAudio(std::move(opus));  // 每个调用对应一个WebSocket消息
}

// WebsocketProtocol::SendAudio
void WebsocketProtocol::SendAudio(const std::vector<uint8_t>& data) {
    websocket_->Send(data.data(), data.size(), true);  // 二进制发送
}
```

**关键点**：
- 每个 `SendAudio()` 调用对应**一个独立的WebSocket二进制消息**
- 每个消息包含**一个独立的Opus包**
- 批量连续发送，没有间隔

## 问题根源

### 错误做法：一次性发送整个音频文件

如果一次性发送5632字节的连续Opus数据：
- 服务器会尝试将整个5632字节作为单个Opus包解码
- `decoder.decode()` 只能解码单个包，导致解码失败或只解码第一个包
- 结果：服务器无法识别音频内容

### 正确做法：分割为多个独立的Opus包

需要：
1. 将连续的Opus数据分割为多个独立的Opus包
2. **每个包作为一个独立的WebSocket消息发送**
3. 批量连续发送（没有间隔）

## 测试脚本修复方案

### 1. 音频分割（`audio_encoder.py`）

- 使用 `opuslib` 解码器验证分割点
- 将连续的Opus数据分割为多个独立的Opus包
- 每个包必须是有效的、可解码的Opus包

### 2. 发送方式（`websocket_client.py`）

- 每个Opus包作为一个独立的WebSocket消息发送
- 批量连续发送所有包，没有间隔
- 模拟设备的行为：`for (auto& opus : packets) { SendAudio(opus); }`

## 总结

| 项目 | 设备行为 | 服务器期望 | 测试脚本（修复后） |
|------|---------|-----------|------------------|
| 消息格式 | 每个WebSocket消息一个Opus包 | 每个WebSocket消息一个Opus包 | ✅ 每个WebSocket消息一个Opus包 |
| 包大小 | 可变（20-400字节） | 单个Opus包（可变大小） | ✅ 可变（20-400字节） |
| 发送方式 | 批量连续发送，无间隔 | 接收多个消息 | ✅ 批量连续发送，无间隔 |
| 解码方式 | - | decoder.decode() 单个包 | ✅ 分割为独立包 |

**核心原则**：**每个WebSocket消息必须是一个完整的、独立的Opus包**

