# 故障排查指南

本文档合并了所有故障排查相关的说明，包括常见问题、解决方案和调试方法。

## 目录

1. [连接问题](#连接问题)
2. [音频识别问题](#音频识别问题)
3. [服务器响应问题](#服务器响应问题)
4. [消息格式问题](#消息格式问题)
5. [性能问题](#性能问题)
6. [调试技巧](#调试技巧)

---

## 连接问题

### 问题 1: 所有连接都失败

**症状**：
- 所有连接都显示 `connect_status: failed`
- 日志中显示连接错误

**可能原因**：
1. 网络连接问题
2. 服务器地址不正确
3. 服务器拒绝连接
4. 防火墙阻止连接

**解决方法**：
1. 检查网络连接
   ```bash
   ping toyaiws.spacechaintech.com
   ```
2. 验证服务器地址和端口
   ```bash
   # 检查 config.py 中的 WS_SERVER_HOST
   echo $WS_SERVER_HOST
   ```
3. 检查服务器日志查看拒绝原因
4. 尝试使用本地服务器测试
   ```bash
   export WS_SERVER_HOST="ws://localhost:8081"
   ```

### 问题 2: 连接超时

**症状**：
- 连接建立时间很长
- 最终显示连接失败

**可能原因**：
1. 网络延迟高
2. 服务器负载高
3. 超时设置过短

**解决方法**：
1. 增加连接超时时间
   ```bash
   export CONNECT_TIMEOUT="20000"  # 增加到20秒
   ```
2. 检查网络质量
3. 减少并发连接数
   ```bash
   export CONCURRENT_CONNECTIONS="10"
   ```

---

## 音频识别问题

### 问题 1: STT识别结果为空

**症状**：
- 日志显示：`Recognized text: `（空）
- 服务器返回"我没听清楚"的回复

**可能原因**：
1. 音频格式不正确
2. 音频内容质量问题
3. 音频数据包分割问题
4. 服务器端解码失败
5. 生产环境进入服务端VAD分支，但ASR工作节点不可用

**解决方法**：

#### 1. 检查音频文件
```bash
# 验证音频文件是否存在且有效
ffmpeg -i audio/test_audio.opus -f null -
```

#### 2. 检查音频编码参数
```python
# 检查 audio_encoder.py 中的编码参数
# 确保：bitrate=32000, complexity=3, frame_duration=60ms
```

#### 3. 检查Opus包分割
```python
# 确保每个WebSocket消息是一个独立的Opus包
# 检查 audio_encoder.py 中的分割逻辑
```

#### 4. 检查生产环境配置
- 确认生产环境是否有ASR工作节点
- 查看生产环境服务器日志，确认音频数据是否到达
- 确认生产环境ws_server代码版本

#### 5. 使用本地服务器测试
```bash
# 启动本地服务器
cd ws_server
npm run dev

# 测试代码连接到本地
export WS_SERVER_HOST="ws://localhost:8081"
python test_runner.py
```

### 问题 2: 音频数据生成失败

**症状**：
- 日志显示：`无法生成音频数据`
- 测试脚本无法启动

**可能原因**：
1. `ffmpeg` 未安装
2. 讯飞TTS API配置错误
3. 依赖库缺失

**解决方法**：
1. 安装 ffmpeg
   ```bash
   # Linux
   sudo apt install ffmpeg
   
   # Mac
   brew install ffmpeg
   
   # Windows
   # 下载并安装 ffmpeg，添加到 PATH
   ```

2. 检查讯飞TTS配置
   ```python
   # 检查 generate_tts_audio.py 中的配置
   # APPID, API_KEY, API_SECRET
   ```

3. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```

4. 使用文本模式（临时方案）
   ```bash
   export SEND_AUDIO_DATA="false"
   ```

### 问题 3: 音频文件为空或损坏

**症状**：
- 音频文件大小为0字节
- 无法播放音频文件

**可能原因**：
1. TTS生成失败
2. 文件写入权限问题
3. 磁盘空间不足

**解决方法**：
1. 重新生成音频文件
   ```bash
   python generate_tts_audio.py
   ```

2. 检查文件权限
   ```bash
   ls -l audio/test_audio.opus
   ```

3. 检查磁盘空间
   ```bash
   df -h
   ```

---

## 服务器响应问题

### 问题 1: 服务器没有响应

**症状**：
- 连接成功，但服务器没有返回 STT/LLM/TTS 响应
- 日志中只显示连接建立，没有后续消息

**可能原因**：
1. 监听模式不正确
2. 没有发送 `stop_listen` 消息
3. 音频数据太短
4. 服务器端处理延迟或问题
5. 生产环境进入服务端VAD分支，音频被丢弃

**解决方法**：

#### 1. 使用正确的监听模式
```bash
export LISTENING_MODE="auto"  # 推荐使用 auto 模式
```

#### 2. 确保发送 stop_listen
```bash
export SEND_STOP_LISTEN="true"  # 确保服务器知道音频传输完成
```

#### 3. 检查音频数据
```python
# 确保音频数据足够长（至少几秒）
# 检查 audio_encoder.py 生成的帧数
```

#### 4. 查看详细诊断日志
```bash
export LOG_LEVEL="DEBUG"  # 查看连接状态、接收任务状态等详细信息
export DEBUG_MODE="true"  # 先测试单个连接
```

#### 5. 检查服务器端日志
- 确认服务器是否收到请求并开始处理
- 检查是否有错误日志

#### 6. 验证消息格式
- 确保所有消息格式与项目代码完全一致
- 检查 `start_listen` 消息格式（不包含 `vad_side` 参数）

### 问题 2: 消息超时

**症状**：
- 消息发送后没有收到响应（超时）
- 日志显示超时错误

**可能原因**：
1. 服务器响应慢
2. 超时设置过短
3. 消息格式不正确

**解决方法**：
1. 增加超时时间
   ```bash
   export TTS_TIMEOUT="120000"  # 设置为 120 秒
   ```

2. 检查消息格式是否正确
   - 确保与项目代码 100% 一致

3. 查看服务器日志
   - 确认服务器是否收到消息

4. 使用 DEBUG 模式查看详细诊断信息
   ```bash
   export LOG_LEVEL="DEBUG"
   export DEBUG_MODE="true"
   ```

### 问题 3: 收到部分响应

**症状**：
- 收到 STT 响应，但没有 LLM/TTS 响应
- 或者收到 TTS start，但没有 TTS stop

**可能原因**：
1. 服务器处理中断
2. 连接断开
3. 超时设置过短

**解决方法**：
1. 检查连接状态
   - 日志中会显示连接是否在等待期间断开

2. 增加超时时间
   ```bash
   export TTS_TIMEOUT="120000"
   ```

3. 检查服务器日志
   - 确认服务器是否正常处理

---

## 消息格式问题

### 问题 1: 认证失败

**症状**：
- 连接后收到认证失败消息
- 服务器拒绝连接

**可能原因**：
1. 设备SN不正确
2. 签名验证失败
3. 设备未注册

**解决方法**：
1. 检查设备信息配置
   ```python
   # 检查 config.py 中的设备信息
   DEVICE_SN = "FC012C2EA0A0"
   DEVICE_SIGN = "c61505cccb8dc83d8e67450cbd4f32c4"
   ```

2. 使用本地服务器测试（绕过认证）
   ```bash
   export WS_SERVER_HOST="ws://localhost:8081"
   ```

### 问题 2: start_listen 消息格式错误

**症状**：
- 服务器无法处理 start_listen 消息
- 日志显示消息格式错误

**解决方法**：
1. 确保消息格式与硬件代码完全一致
   ```json
   {
     "session_id": "",
     "type": "start_listen",
     "data": {
       "format": "opus",
       "tts_format": "opus",
       "playTag": 1,
       "state": "asr",
       "mode": "auto"
     }
   }
   ```

2. **注意**：不包含 `vad_side` 参数（与硬件代码一致）

---

## 性能问题

### 问题 1: 高并发时连接失败率高

**症状**：
- 100个并发连接时，失败率很高
- 部分连接超时

**解决方法**：
1. 减少并发连接数
   ```bash
   export CONCURRENT_CONNECTIONS="50"
   ```

2. 增加连接超时时间
   ```bash
   export CONNECT_TIMEOUT="20000"
   ```

3. 分批测试
   - 先测试10个连接
   - 逐步增加到50、100

### 问题 2: 响应时间过长

**症状**：
- 平均响应时间很长
- P95/P99 响应时间很高

**可能原因**：
1. 服务器负载高
2. 网络延迟高
3. 音频处理时间长

**解决方法**：
1. 检查服务器负载
2. 检查网络质量
3. 减少音频长度
4. 优化音频编码参数

---

## 调试技巧

### 1. 使用DEBUG模式

```bash
export DEBUG_MODE="true"  # 只发送1个连接
export LOG_LEVEL="DEBUG"  # 详细日志
python test_runner.py
```

### 2. 检查音频文件

```bash
# 验证Opus文件
ffmpeg -i audio/test_audio.opus -f null -

# 转换为WAV试听
ffmpeg -i audio/test_audio.opus audio/test_audio.wav

# 检查文件大小
ls -lh audio/test_audio.opus
```

### 3. 使用本地服务器测试

```bash
# 启动本地服务器
cd ws_server
npm run dev

# 测试代码连接到本地
export WS_SERVER_HOST="ws://localhost:8081"
python test_runner.py
```

### 4. 查看详细日志

```bash
# 查看日志文件
tail -f results/logs/test_*.log

# 查看CSV结果
cat results/csv/test_results_*.csv
```

### 5. 验证消息格式

```python
# 在 websocket_client.py 中添加日志
self.logger.debug(f"Sending message: {message_str}")
```

### 6. 检查网络连接

```bash
# 测试服务器连接
curl -I http://toyaiws.spacechaintech.com:8081

# 测试WebSocket连接（使用wscat）
wscat -c ws://toyaiws.spacechaintech.com:8081
```

---

## 常见错误码

| 错误码 | 含义 | 解决方法 |
|--------|------|---------|
| 1005 | 连接关闭（无状态码） | 检查网络连接和服务器状态 |
| 1006 | 异常关闭 | 检查服务器日志 |
| ConnectionTimeoutError | 连接超时 | 增加 CONNECT_TIMEOUT |
| MessageTimeoutError | 消息超时 | 增加 TTS_TIMEOUT |

---

## 快速诊断清单

1. ✅ 网络连接是否正常？
2. ✅ 服务器地址是否正确？
3. ✅ 音频文件是否存在且有效？
4. ✅ 依赖库是否已安装？
5. ✅ 消息格式是否正确？
6. ✅ 监听模式是否设置正确？
7. ✅ 是否发送了 stop_listen？
8. ✅ 超时设置是否合理？
9. ✅ 日志级别是否足够详细？
10. ✅ 服务器日志是否正常？

---

**最后更新**: 2025-11-05

**注意**: 本文档位于 `performance/docs/` 目录下

