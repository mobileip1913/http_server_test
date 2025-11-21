# 语音识别失败问题详细分析

## 问题现象

从测试日志 `test_20251110_104043.log` 可以看到：

```
Connection #1: STT response received in 760.72ms | Recognized text: 
Connection #1: TTS sentence_start | Text: 嘿嘿，我没听明白你刚刚说啥，能再说一遍不？
```

**关键问题**：
- STT识别结果为空（`Recognized text: `）
- 服务器返回了"没听明白"的回复，说明服务器收到了音频，但IAT识别失败

## 问题分析

### 1. 音频处理流程

#### 测试脚本端（`performance/audio_encoder.py`）

1. **音频文件加载**：
   - 使用 `performance/audio/test_audio.opus`
   - 检测到是 Ogg Opus 容器格式
   - 转换为 PCM，然后重新编码为裸 Opus 包
   - 生成了 38 个独立的 Opus 包（每个包作为独立的 WebSocket 消息发送）

2. **音频发送**（`performance/websocket_client.py`）：
   ```python
   # 每个 Opus 包作为独立的 WebSocket 二进制消息发送
   for frame in audio_frames:
       await self.websocket.send(frame)  # 二进制发送
   ```

#### 服务端处理（`ws_server/app/event/hw/iat_speak.js`）

服务端有三个处理分支：

```javascript
// 1. 服务端 VAD 模式
if (this.context["is_vad_chat"] && this.context["vad_side"] != "client_side_vad") {
    const pcmData = decoder.decode(binaryData);
    this.context.iatService.sendAudio(pcmData);
}
// 2. Opus 格式 + state == "asr"（正常路径）
else if (this.context["iat_format"] == "opus" && 
         (this.context["state"] == "asr" || ...)) {
    const pcmData = decoder.decode(binaryData);
    this.context.iatService.sendAudio(pcmData);
}
// 3. 其他 Opus 格式（兜底路径，使用文件转换）
else if (this.context["iat_format"] == "opus") {
    // 使用 tkai_opus 工具进行文件转换
    opusToPcm(tmpOpusFile, tmpPcmFile);
    const pcmData = fs.readFileSync(tmpPcmFile);
    this.context.iatService.sendAudio(pcmData);
}
```

### 2. 可能的问题原因

#### 问题1：Opus 解码失败（最可能）

**原因**：
- `@discordjs/opus` 的 `decoder.decode()` 只能解码单个、完整的 Opus 包
- 如果 Opus 包格式不正确、损坏或不符合预期，解码会失败
- **关键**：代码中没有 try-catch 捕获解码异常，如果解码失败会抛出异常，导致后续处理中断

**验证方法**：
- 检查服务端日志是否有解码错误
- 检查是否进入了第三个分支（文件转换路径）

**解决方案**：
1. 在服务端添加 try-catch 捕获解码异常
2. 如果解码失败，自动降级到文件转换路径
3. 记录详细的错误日志

#### 问题2：重新编码的 Opus 包格式不正确

**原因**：
- 测试脚本从 Ogg 容器提取音频后，使用 `opuslib` 重新编码为 Opus 包
- 重新编码的参数可能与设备实际编码参数不一致：
  - 比特率（bitrate）
  - 复杂度（complexity）
  - 帧大小（frame size）
  - 应用模式（application mode）

**当前编码参数**（`audio_encoder.py`）：
```python
encoder.bitrate = 32000  # 32kbps
encoder.complexity = Config.OPUS_COMPLEXITY  # 默认 3
frame_size = 960  # 60ms @ 16kHz
```

**设备实际参数**（需要确认）：
- WiFi 板：`OPUS_COMPLEXITY = 3`
- ML307 板：`OPUS_COMPLEXITY = 5`

**验证方法**：
- 对比设备实际发送的 Opus 包格式
- 检查重新编码的包是否能被 `@discordjs/opus` 正确解码

#### 问题3：音频内容质量问题

**原因**：
- 虽然音频文件存在，但可能是：
  - 静音或音量过低
  - 质量差、有噪声
  - 采样率/声道不匹配

**验证方法**：
- 使用 `ffmpeg` 检查音频文件：
  ```bash
  ffmpeg -i performance/audio/test_audio.opus -af "volumedetect" -f null -
  ```
- 播放音频文件确认内容是否正确

#### 问题4：IAT 服务配置问题

**原因**：
- 在线环境的 IAT 服务可能配置不同
- PCM 数据可能没有正确发送到 IAT 服务
- IAT 服务可能对音频格式有特殊要求

**验证方法**：
- 检查 IAT 服务日志
- 确认 PCM 数据是否正确发送

#### 问题5：音频发送时序问题

**原因**：
- 测试脚本在发送 `start_listen` 后等待 600ms 才开始发送音频
- 但服务端 IAT 服务启动有 500ms 延迟（`setTimeout`）
- 如果音频发送太快，可能 IAT 服务还未准备好

**当前时序**（`websocket_client.py`）：
```python
await self.send_start_listen()
await asyncio.sleep(0.6)  # 等待 600ms
# 然后发送音频帧
```

**验证方法**：
- 检查服务端 IAT 服务是否在音频到达时已启动
- 增加等待时间或确保 IAT 服务已准备好

## 诊断步骤

### 步骤1：检查服务端日志

查看服务端是否有以下错误：
- Opus 解码错误
- IAT 服务连接错误
- PCM 数据发送错误

### 步骤2：验证 Opus 包格式

1. **检查测试脚本生成的 Opus 包**：
   ```python
   # 在 audio_encoder.py 中添加日志
   for i, frame in enumerate(frames):
       print(f"Frame {i}: {len(frame)} bytes")
       # 尝试解码验证
       try:
           pcm = decoder.decode(frame, frame_size)
           print(f"  Decode OK: {len(pcm)} bytes PCM")
       except Exception as e:
           print(f"  Decode FAILED: {e}")
   ```

2. **对比设备实际发送的包**：
   - 抓取设备实际发送的 Opus 包
   - 对比格式差异

### 步骤3：测试音频文件质量

```bash
# 检查音频文件信息
ffmpeg -i performance/audio/test_audio.opus

# 检查音量
ffmpeg -i performance/audio/test_audio.opus -af "volumedetect" -f null -

# 转换为 WAV 试听
ffmpeg -i performance/audio/test_audio.opus test_audio.wav
```

### 步骤4：添加服务端错误处理

在 `ws_server/app/event/hw/iat_speak.js` 中添加 try-catch：

```javascript
else if (
  this.context["iat_format"] == "opus" &&
  (this.context["state"] == "asr" || ...)
) {
  try {
    const pcmData = decoder.decode(binaryData);
    this.context.iatService.sendAudio(pcmData);
  } catch (error) {
    Log.error(`Opus decode failed: ${error.message}, falling back to file conversion`);
    // 降级到文件转换路径
    // ... 文件转换代码
  }
}
```

### 步骤5：验证 IAT 服务

1. **检查 IAT 服务是否正常**：
   - 查看 IAT 服务连接日志
   - 确认 PCM 数据是否发送成功

2. **测试直接发送 PCM**：
   - 跳过 Opus 编码，直接发送 PCM 数据
   - 验证 IAT 服务是否能识别

## 推荐解决方案

### 方案1：修复服务端错误处理（优先）

在 `iat_speak.js` 中添加 try-catch，确保解码失败时能降级处理：

```javascript
else if (
  this.context["iat_format"] == "opus" &&
  (this.context["state"] == "asr" || this.context["state"] == "detect" || this.context["state"] == "double_detect")
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

### 方案2：优化测试脚本音频编码

1. **使用设备实际编码参数**：
   - 确认设备使用的 Opus 编码参数
   - 在测试脚本中使用相同的参数

2. **使用真实的 TTS 音频**：
   - 使用讯飞 TTS 服务生成音频
   - 确保音频质量和格式正确

### 方案3：添加详细日志

在关键位置添加日志：
- Opus 包大小和数量
- 解码成功/失败
- PCM 数据大小
- IAT 服务发送状态

## 总结

**最可能的原因**：
1. Opus 解码失败（没有错误处理，导致静默失败）
2. 重新编码的 Opus 包格式与设备不一致
3. 音频内容质量问题

**建议优先处理**：
1. 在服务端添加 try-catch 错误处理
2. 添加详细日志记录
3. 验证音频文件质量
4. 对比设备实际编码参数

