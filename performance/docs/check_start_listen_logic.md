# start_listen 消息逻辑分析

## 测试脚本发送的消息格式
```json
{
  "session_id": "...",
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

## 服务器端处理逻辑（start_listen.js）

### 关键状态设置：
1. `this.context["state"] = data["state"]` → `"asr"` ✅
2. `this.context["is_vad_chat"] = data["mode"] == "auto" || data["mode"] == "realtime"` → `true` ✅（因为mode是"auto"）
3. `this.context["vad_side"]` → **未设置**（因为state不是"detect"）

### IAT服务启动条件（第69行）：
```javascript
if (this.context["start_listen"] && 
    this.context["state"] == "asr" && 
    (!this.context["is_vad_chat"] || this.context["vad_side"] == "client_side_vad")) {
  // 启动IAT服务
}
```

**问题分析：**
- `start_listen = true` ✅
- `state == "asr"` ✅
- `!is_vad_chat || vad_side == "client_side_vad"` → `!true || undefined` → `false || undefined` → **条件不满足** ❌

**结果：** IAT服务**不会启动**！

## 服务器端解码路径（iat_speak.js）

### 路径1（第51-62行）：VAD模式
```javascript
if (this.context["is_vad_chat"] && this.context["vad_side"] != "client_side_vad") {
  // 使用VAD会话
  this.context['vadSession'].sendAudio(binaryData);
  const pcmData = decoder.decode(binaryData);
  this.context.iatService.sendAudio(pcmData);
}
```

**问题：** `is_vad_chat = true`，但`vad_side`未设置（undefined），所以`vad_side != "client_side_vad"`为`true`，会尝试使用VAD会话，但VAD会话可能未初始化！

### 路径2（第63-68行）：直接解码
```javascript
else if (
  this.context["iat_format"] == "opus" &&
  (this.context["state"] == "asr" || this.context["state"] == "detect" || this.context["state"] == "double_detect")
) {
  const pcmData = decoder.decode(binaryData);
  this.context.iatService.sendAudio(pcmData);
}
```

**问题：** 由于路径1的条件满足，不会走到这里！

## 解决方案

### 方案1：修改测试脚本，明确指定vad_side
在start_listen消息中添加：
```json
{
  "data": {
    ...
    "vad_side": "client"  // 明确指定客户端VAD
  }
}
```

这样：
- `vad_side = "client_side_vad"` ✅
- 路径1的条件不满足（`vad_side == "client_side_vad"`）✅
- 会走到路径2，直接解码 ✅

### 方案2：修改测试脚本，使用manual模式
将mode改为"manual"：
```json
{
  "data": {
    ...
    "mode": "manual"
  }
}
```

这样：
- `is_vad_chat = false` ✅
- IAT服务会启动（第69行条件满足）✅
- 路径1的条件不满足（`!is_vad_chat`为true，但路径1需要`is_vad_chat`为true）✅
- 会走到路径2，直接解码 ✅

