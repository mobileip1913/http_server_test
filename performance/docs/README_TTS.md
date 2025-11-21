# 使用讯飞TTS生成测试音频

## 概述

为了进行真实的语音识别测试，我们需要使用真实的语音数据而不是静音。本脚本使用讯飞在线语音合成API生成测试音频文件。

## 配置信息

已在代码中配置的讯飞API信息：
- **APPID**: `c7f30371`
- **APIKey**: `50e273869438ea2fc41e44a32167ef6d`
- **APISecret**: `OGIxYmY1OGM2OWZkNTcyMGE4YzM2NTM0`

## 使用方法

### 1. 生成测试音频

运行脚本生成默认测试音频：

```bash
cd performance
python generate_tts_audio.py
```

或者指定自定义文本：

```bash
python generate_tts_audio.py "你好啊，我今天想去故宫玩"
```

### 2. 输出文件

生成的音频文件将保存在：
```
performance/audio/test_audio.opus
```

### 3. 使用生成的音频进行测试

生成的音频文件会自动被测试脚本使用（如果存在）。测试脚本会优先使用 `performance/audio/test_audio.opus`。

如果需要使用其他音频文件，可以通过环境变量指定：

```bash
export AUDIO_FILE_PATH=/path/to/your/audio.opus
python test_runner.py
```

## 音频格式

- **格式**: Opus
- **采样率**: 16kHz
- **声道**: 单声道
- **编码**: 16bit PCM（原始格式），然后编码为Opus

## 注意事项

1. **网络连接**：需要能够访问讯飞API服务器（`wss://tts-api.xfyun.cn`）
2. **API配额**：注意讯飞API的调用次数限制
3. **音频文件大小**：生成的音频文件通常只有几KB到几十KB
4. **音频格式**：生成的音频是Opus格式，可以直接用于测试

## 故障排除

### 问题1：连接失败

**症状**：`Failed to connect to Xunfei TTS API`

**解决**：
- 检查网络连接
- 确认能够访问 `wss://tts-api.xfyun.cn`
- 检查防火墙设置

### 问题2：鉴权失败

**症状**：`TTS API error: code=11200` 或其他错误码

**解决**：
- 检查API密钥是否正确
- 确认APPID是否有效
- 检查API服务是否已开通

### 问题3：音频文件为空

**症状**：生成的文件大小为0或很小

**解决**：
- 检查文本内容是否正确
- 查看日志确认是否收到音频数据
- 重新运行脚本

## 参考文档

- [讯飞在线语音合成API文档](https://www.xfyun.cn/doc/tts/online_tts/API.html)

