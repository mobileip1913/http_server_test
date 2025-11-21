# 音频识别问题调试指南

## 当前问题

从日志 `test_20251104_163352.log` 看到：
- ✅ 音频已成功分割为92个独立的Opus包（99.1%覆盖率）
- ❌ STT识别的文本为空：`Recognized text: `（空）
- ❌ 大模型返回"没听清楚"

## 可能的原因

### 1. Opus包分割不够准确

虽然使用 `opuslib` 解码器验证分割，但可能：
- 分割出的包虽然能解码，但不是真正的Opus包边界
- 解码后的PCM数据不正确或丢失了部分音频

### 2. 音频内容或质量问题

- 讯飞TTS生成的音频可能有问题
- 音频内容可能不够清晰
- 音频文件可能损坏

### 3. 服务器端解码问题

- 服务器使用 `@discordjs/opus` 解码器
- 可能对某些Opus包格式不兼容
- 解码后的PCM数据可能不正确

## 调试步骤

### 步骤1：验证音频文件

```bash
# 检查音频文件是否可以播放
ffplay performance/audio/test_audio.opus

# 或者转换为MP3试听
ffmpeg -i performance/audio/test_audio.opus performance/audio/test_audio_check.mp3
```

### 步骤2：重新生成音频

确保使用正确的文本和参数：

```bash
cd performance
python generate_tts_audio.py "你好啊，我想去故宫"
```

检查生成的音频文件是否可以正常播放。

### 步骤3：检查Opus包分割

```python
# 测试分割逻辑
import sys
sys.path.insert(0, '.')
from audio_encoder import AudioEncoder
from config import Config

encoder = AudioEncoder()
frames = encoder.text_to_opus_frames(Config.TEST_MESSAGE)

# 检查分割结果
print(f"Split into {len(frames)} packets")
print(f"Total bytes: {sum(len(f) for f in frames)}")
print(f"Packet sizes: {[len(f) for f in frames[:10]]}")
```

### 步骤4：服务器端调试

如果可能，检查服务器端日志：
- 查看服务器接收到的音频数据大小
- 查看解码后的PCM数据
- 查看IAT服务的识别结果

## 建议的解决方案

### 方案1：使用ffmpeg重新编码

将连续的Opus数据转换为PCM，然后重新编码为多个独立的Opus包：

```bash
# 转换为PCM
ffmpeg -i test_audio.opus -ar 16000 -ac 1 -f s16le test_audio.pcm

# 然后使用Opus编码器重新编码为多个60ms帧
```

### 方案2：直接发送完整的Opus数据

如果服务器支持，尝试一次性发送整个音频文件（虽然之前尝试过但可能有问题）。

### 方案3：使用不同的音频生成方法

尝试使用其他TTS服务或方法生成音频，确保音频质量。

## 下一步

1. 首先验证音频文件是否可以播放
2. 如果音频可以播放，问题可能在分割逻辑
3. 如果音频无法播放，需要重新生成

