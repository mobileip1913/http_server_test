# 设备发送方式 vs 测试脚本对比分析

## 关键发现

### 1. 设备实际发送流程

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

### 2. 测试脚本修复后的实现

**音频处理（已修复）**：
- ✅ 使用 Opus 解码器智能分割连续的 Opus 数据包
- ✅ 将连续的 Opus 数据分割为多个独立的 60ms 帧
- ✅ 例如：5632字节的音频被分割为92个独立的Opus帧

**发送逻辑（已修复）**：
```python
async def send_audio_frames(self, audio_frames: List[bytes], frame_interval_ms: float = 0.0):
    # 批量连续发送所有帧（模拟 MainLoop 的行为）
    for frame in audio_frames:
        await self.websocket.send(frame)  # 二进制发送，没有间隔
        # frame_interval_ms 默认为 0.0，表示批量连续发送
```

**关键修复**：
- ✅ **修复1**：正确分割连续的 Opus 数据包为多个独立的帧
- ✅ **修复2**：移除帧间隔，改为批量连续发送（`frame_interval_ms = 0.0`）
- ✅ **修复3**：使用 Opus 解码器验证分割点，确保每个包都是有效的

### 3. 对比总结

| 项目 | 设备行为 | 测试脚本（修复后） | 状态 |
|------|---------|------------------|------|
| 音频格式 | 多个独立的Opus包 | 多个独立的Opus包 | ✅ 一致 |
| 包大小 | 可变（20-400字节） | 可变（20-400字节） | ✅ 一致 |
| 发送方式 | 批量连续发送，无间隔 | 批量连续发送，无间隔 | ✅ 一致 |
| WebSocket格式 | 二进制（`true`） | 二进制（bytes） | ✅ 一致 |
| 分割方法 | 设备编码时自动分割 | 使用Opus解码器验证分割 | ✅ 等效 |

### 4. 已修复的文件

1. **`audio_encoder.py`**：
   - 启用智能分割逻辑，使用 Opus 解码器验证分割点
   - 将连续的 Opus 数据分割为多个独立的 60ms 帧

2. **`websocket_client.py`**：
   - 修改 `send_audio_frames`，默认 `frame_interval_ms = 0.0`（批量连续发送）
   - 移除帧间隔，模拟 MainLoop 的批量连续发送行为

3. **`config.py`**：
   - 修改 `AUDIO_SEND_INTERVAL_MS` 默认值为 `0.0`（批量连续发送）

## 测试验证

运行测试脚本，验证音频分割和发送：

```bash
cd D:\code\vb_eye_st7789\performance
python -c "from audio_encoder import AudioEncoder; from config import Config; encoder = AudioEncoder(); frames = encoder.text_to_opus_frames(Config.TEST_MESSAGE); print(f'Split into {len(frames)} frames')"
```

**预期结果**：
- 5632字节的音频应该被分割为约92个独立的Opus帧
- 每个帧大小在20-400字节之间
- 发送时批量连续发送，没有间隔

## 注意事项

1. **音频文件**：确保使用 `generate_tts_audio.py` 生成的Opus文件，文本为"你好啊，我想去故宫"，语速30（慢速）
2. **分割验证**：如果分割失败，会回退到单帧发送（但这不是设备的行为）
3. **发送间隔**：可以通过环境变量 `AUDIO_SEND_INTERVAL_MS` 调整（默认0ms表示批量连续发送）

