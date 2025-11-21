# WebSocket 性能测试项目 - 当前进度与问题列表

## 📋 项目概述

本项目是一个 WebSocket 性能测试工具，用于测试音频流式识别系统的完整流程（STT → LLM → TTS），完全模拟硬件设备的行为。

## ✅ 已完成的工作

### 1. 核心功能实现
- ✅ WebSocket 客户端实现（`websocket_client.py`）
- ✅ 音频编码器实现（`audio_encoder.py`）- 支持 Opus 编码和包分割
- ✅ 测试运行器实现（`test_runner.py`）
- ✅ 指标收集和报告生成（`metrics_collector.py`）
- ✅ 完整的日志系统（`logger.py`）

### 2. 音频处理
- ✅ 讯飞 TTS 音频生成（`generate_tts_audio.py`）
- ✅ Ogg Opus 容器解析和转换
- ✅ PCM 到 Opus 的重新编码
- ✅ Opus 数据包分割（支持单个包发送）

### 3. 设备行为模拟
- ✅ 完全对齐硬件设备的 `start_listen` 消息格式（不包含 `vad_side` 参数）
- ✅ 批量连续发送音频包（模拟 MainLoop 行为）
- ✅ 正确的监听模式支持（auto/manual/realtime）
- ✅ 正确的消息格式和协议实现

### 4. 服务器端调试支持
- ✅ 本地服务器启动脚本（`start_ws_server.bat` / `start_ws_server.sh`）
- ✅ 本地服务器配置文档（`start_local_server.md`）
- ✅ 测试模式支持（白名单 SN，绕过 Redis 认证）

### 5. 问题修复
- ✅ 修复了 Opus 数据包分割问题（从 Ogg 容器提取原始包）
- ✅ 修复了剩余 PCM 数据丢失问题（添加静音填充）
- ✅ 修复了编码参数不匹配问题（bitrate 32kbps, complexity 3）
- ✅ 修复了 `start_listen` 消息格式问题（移除 `vad_side` 参数，完全模拟硬件）

## 🚧 当前进度

### 正在进行的工作
1. **生产环境测试**
   - 测试代码已修改为完全模拟硬件行为
   - 移除了 `vad_side` 参数，与硬件代码一致
   - 等待生产环境测试结果

2. **文档整理**
   - 正在整理和合并相关文档
   - 创建统一的进度和问题列表

## ⚠️ 已知问题

### 问题 1: 生产环境 STT 识别为空
**状态**: 🔴 待解决  
**严重程度**: 高  
**描述**: 
- 生产环境服务器返回 STT 识别结果为空
- 本地测试环境可以正常识别（使用本地 ws_server）
- 问题可能在于生产环境的旧代码不支持某些参数或逻辑

**可能原因**:
1. 生产环境的 ws_server 代码版本较旧，不支持某些参数
2. 生产环境进入服务端 VAD 分支，但 ASR 工作节点不可用
3. 音频数据在服务端 VAD 分支中没有正确解码或发送到 IAT

**已尝试的解决方案**:
- ✅ 移除了 `vad_side` 参数，完全模拟硬件行为
- ✅ 确保音频包逐个发送（每个 WebSocket 消息一个 Opus 包）
- ✅ 本地环境测试成功，STT 识别正常

**下一步**:
- 查看生产环境服务器日志，确认音频数据是否到达服务器
- 确认生产环境 ws_server 代码版本
- 检查生产环境是否有 ASR 工作节点

### 问题 2: 服务端 VAD 分支处理
**状态**: 🟡 部分解决  
**严重程度**: 中  
**描述**:
- 当 `mode == "auto"` 时，`is_vad_chat = true`
- 如果 `vad_side` 为 `undefined`（旧代码不支持此参数），会进入服务端 VAD 分支
- 如果生产环境没有 ASR 工作节点，音频会被丢弃

**当前状态**:
- 测试代码已移除 `vad_side` 参数，完全模拟硬件行为
- 需要确认生产环境是否有 ASR 工作节点

### 问题 3: 音频编码质量
**状态**: ✅ 已解决  
**严重程度**: 中  
**描述**:
- 之前生成的 Opus 音频有杂音问题
- 通过改用 PCM 生成 + FFmpeg 编码的方式解决

**解决方案**:
- ✅ 使用讯飞 TTS API 生成 PCM 格式
- ✅ 使用 FFmpeg 编码为 Opus（参数：`-c:a libopus -b:a 32k -frame_duration 60`）

### 问题 4: Opus 数据包分割
**状态**: ✅ 已解决  
**严重程度**: 高  
**描述**:
- 服务器端的 `@discordjs/opus` 解码器只能解码单个 Opus 包
- 客户端发送连续 Opus 数据会导致解码失败

**解决方案**:
- ✅ 从 Ogg 容器直接提取原始 Opus 包
- ✅ 每个包作为独立的 WebSocket 消息发送
- ✅ 如果无法提取，则从 PCM 重新编码为独立的 Opus 包

### 问题 5: 剩余 PCM 数据丢失
**状态**: ✅ 已解决  
**严重程度**: 中  
**描述**:
- `_generate_raw_opus_from_pcm` 方法只处理完整的 1920 字节帧
- 剩余数据（如 1846 字节）被丢弃

**解决方案**:
- ✅ 添加静音填充，确保剩余数据也被编码
- ✅ 处理覆盖率达到 99.9%

## 📊 测试结果

### 本地环境测试
- ✅ 连接成功
- ✅ STT 识别成功（"你好啊，我想去故宫"）
- ✅ LLM 调用成功
- ✅ TTS 响应成功

### 生产环境测试
- ✅ 连接成功
- ❌ STT 识别为空
- ⚠️ LLM 返回 "didn't hear clearly" 消息
- ⚠️ TTS 播放 "没听清" 提示

## 🔧 技术细节

### 音频格式
- **采样率**: 16kHz
- **声道**: 单声道
- **帧长度**: 60ms (960 samples)
- **编码格式**: Opus
- **编码参数**: 32kbps, complexity 3

### 消息格式
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

**注意**: 不包含 `vad_side` 参数，与硬件代码完全一致。

### 音频发送方式
- 批量连续发送（模拟 MainLoop 行为）
- 每个 Opus 包作为独立的 WebSocket 消息
- 无间隔发送（0ms delay）

## 📝 文件说明

### 核心文件
- `test_runner.py` - 主测试运行器
- `websocket_client.py` - WebSocket 客户端实现
- `audio_encoder.py` - 音频编码器
- `config.py` - 配置文件
- `logger.py` - 日志系统
- `metrics_collector.py` - 指标收集器

### 工具文件
- `generate_tts_audio.py` - 讯飞 TTS 音频生成
- `local_transcribe.py` - 本地 Whisper 转录工具
- `raasr_transcribe.py` - 讯飞 RAASR 转录工具（已废弃，额度不足）

### 临时调试文件（可删除）
- `analyze_opus_conversion.py` - Opus 转换分析
- `extract_opus_from_ogg.py` - Ogg 提取工具
- `verify_extracted_opus.py` - Opus 验证工具
- `verify_generated_opus.py` - 生成 Opus 验证工具
- `decode_opus_to_wav.py` - Opus 解码工具
- `split_opus_packets.py` - Opus 包分割工具（已集成到 audio_encoder.py）
- `generate_mp3.py` - MP3 生成工具（用于试听）

### 文档文件
- `README.md` - 主文档
- `PROJECT_STATUS.md` - 本文档（进度和问题列表）
- `TECHNICAL_NOTES.md` - 技术说明（合并后的技术文档）
- `TROUBLESHOOTING.md` - 故障排查指南（合并后的故障排查文档）

## 🎯 下一步计划

1. **解决生产环境 STT 识别问题**
   - 查看生产环境服务器日志
   - 确认代码版本差异
   - 验证 ASR 工作节点状态

2. **代码清理**
   - 删除临时调试文件
   - 整理文档结构
   - 更新主 README

3. **测试完善**
   - 添加更多测试场景
   - 完善错误处理
   - 添加性能基准测试

## 📚 相关文档

所有文档位于 `docs/` 目录下：

- `README.md` - 完整的使用说明和配置指南
- `TECHNICAL_NOTES.md` - 技术细节和实现说明
- `TROUBLESHOOTING.md` - 故障排查和常见问题
- `FILE_ORGANIZATION.md` - 文件组织说明

**注意**: 本文档位于 `performance/docs/` 目录下

## 🔗 相关资源

- 硬件代码: `main/protocols/protocol.cc`
- 服务器代码: `ws_server/app/event/hw/`
- 音频处理: `main/application.cc`

---

**最后更新**: 2025-11-05  
**状态**: 生产环境测试中

