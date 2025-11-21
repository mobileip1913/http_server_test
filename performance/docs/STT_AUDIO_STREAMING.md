# STT 音频流式处理机制分析

## 问题

性能测试脚本发送一段语音"我要去故宫"，会分成多个 Opus 包（例如38个包），服务端接收后是否会合并成一个请求去请求 STT？

## 答案

**不会合并成一个请求，而是流式发送多个帧到 STT 服务。**

---

## 详细流程分析

### 1. 测试脚本发送（多个 Opus 包）

```
测试脚本发送：
  Opus包1 (60ms) → WebSocket消息1 (二进制)
  Opus包2 (60ms) → WebSocket消息2 (二进制)
  Opus包3 (60ms) → WebSocket消息3 (二进制)
  ...
  Opus包38 (60ms) → WebSocket消息38 (二进制)
```

**特点**：
- 每个 Opus 包作为**独立的 WebSocket 二进制消息**发送
- 批量连续发送，没有间隔

### 2. 服务端接收（`ws_server/app/event/hw/iat_speak.js`）

```javascript
// 每个 WebSocket 消息触发一次 handle
async handle(req) {
    const binaryData = req._data;  // 一个 Opus 包
    
    // 解码为 PCM
    const pcmData = decoder.decode(binaryData);
    
    // 立即发送到 IAT 服务（不等待，不合并）
    this.context.iatService.sendAudio(pcmData);
}
```

**关键点**：
- ✅ 每个 Opus 包**立即解码**为 PCM
- ✅ 每个 PCM 包**立即调用** `iatService.sendAudio()`
- ❌ **不会等待**所有包到达后再合并
- ❌ **不会合并**成一个大的 PCM 数据块

### 3. IAT 服务流式发送（`ws_server/app/lib/iat/xunfei_iat.js`）

```javascript
sendAudio = (data) => {
    // 如果连接未建立，先缓存
    if (!this.iat_server_connected) {
        this.sendQueue.push(data);  // 缓存队列
        return;
    }
    
    // 连接建立后，立即发送（不合并）
    this.sendPcmFrame(data);
};

sendPcmFrame = (data) => {
    // 保存到 chunkList（用于后续处理）
    data && this.chunkList.push(data);
    
    // 构建帧数据
    let frameDataSection = {
        status: this.iat_status,  // FIRST_FRAME / CONTINUE_FRAME / LAST_FRAME
        format: "audio/L16;rate=16000",
        audio: data.toString("base64"),  // 单个 PCM 包转为 base64
        encoding: "raw",
    };
    
    // 根据状态构建不同的帧格式
    switch (this.iat_status) {
        case XF_IAT_FRAME.STATUS_FIRST_FRAME:
            // 第一帧：包含完整的配置信息
            frame = {
                common: { app_id: xun_fei.appid },
                business: { language: this.language, domain: "iat", ... },
                data: frameDataSection,
            };
            this.iat_status = XF_IAT_FRAME.STATUS_CONTINUE_FRAME;
            break;
        case XF_IAT_FRAME.STATUS_CONTINUE_FRAME:
        case XF_IAT_FRAME.STATUS_LAST_FRAME:
            // 后续帧：只包含音频数据
            frame = { data: frameDataSection };
            break;
    }
    
    // 立即发送到讯飞 IAT WebSocket
    this.iat_ws.send(JSON.stringify(frame));
};
```

**关键点**：
- ✅ **流式发送**：每个 PCM 包立即发送，不等待
- ✅ **状态机**：
  - `STATUS_FIRST_FRAME`：第一帧，包含配置信息
  - `STATUS_CONTINUE_FRAME`：中间帧，只包含音频数据
  - `STATUS_LAST_FRAME`：最后一帧（当收到 `stop_listen` 时）
- ✅ **实时识别**：讯飞 IAT 服务支持流式识别，实时返回中间结果

### 4. 讯飞 IAT 服务处理

讯飞 IAT 服务是**流式识别服务**：

```
客户端发送：
  帧1 (FIRST_FRAME + PCM数据1) → 讯飞 IAT
  帧2 (CONTINUE_FRAME + PCM数据2) → 讯飞 IAT
  帧3 (CONTINUE_FRAME + PCM数据3) → 讯飞 IAT
  ...
  帧38 (CONTINUE_FRAME + PCM数据38) → 讯飞 IAT
  帧39 (LAST_FRAME + 空数据) → 讯飞 IAT（结束标志）

讯飞 IAT 返回：
  中间结果1: "我要"
  中间结果2: "我要去"
  中间结果3: "我要去故宫"
  最终结果: "我要去故宫" (status=2)
```

**特点**：
- ✅ **流式识别**：边接收边识别，实时返回中间结果
- ✅ **动态修正**：后续帧可能修正前面的识别结果（`pgs == "rpl"`）
- ✅ **最终结果**：当收到 `STATUS_LAST_FRAME` 时，返回最终识别结果

---

## 完整流程图

```
测试脚本                         服务端                         讯飞 IAT
   |                               |                               |
   |-- Opus包1 (WebSocket消息1) -->|                               |
   |                               |-- 解码为PCM1                  |
   |                               |-- sendAudio(PCM1)            |
   |                               |                               |-- 帧1 (FIRST_FRAME + PCM1) -->
   |                               |                               |<-- 中间结果1: "我要" --
   |                               |                               |
   |-- Opus包2 (WebSocket消息2) -->|                               |
   |                               |-- 解码为PCM2                  |
   |                               |-- sendAudio(PCM2)            |
   |                               |                               |-- 帧2 (CONTINUE_FRAME + PCM2) -->
   |                               |                               |<-- 中间结果2: "我要去" --
   |                               |                               |
   |-- Opus包3 (WebSocket消息3) -->|                               |
   |                               |-- 解码为PCM3                  |
   |                               |-- sendAudio(PCM3)            |
   |                               |                               |-- 帧3 (CONTINUE_FRAME + PCM3) -->
   |                               |                               |<-- 中间结果3: "我要去故宫" --
   |                               |                               |
   |         ... (继续发送)        |         ... (继续解码和发送)    |         ... (继续识别)        |
   |                               |                               |
   |-- stop_listen --------------→|                               |
   |                               |-- sendAudio("") (空数据)     |
   |                               |                               |-- 帧N (LAST_FRAME + 空) -->
   |                               |                               |<-- 最终结果: "我要去故宫" (status=2) --
   |                               |                               |
   |                               |<-- iatCompleteCallback("我要去故宫") --
   |                               |-- 发送 STT 结果到客户端
```

---

## 关键代码位置

### 1. 接收并解码（`ws_server/app/event/hw/iat_speak.js`）

```javascript
// 第67-68行
const pcmData = decoder.decode(binaryData);
this.context.iatService.sendAudio(pcmData);  // 立即发送，不等待
```

### 2. 流式发送到 IAT（`ws_server/app/lib/iat/xunfei_iat.js`）

```javascript
// 第175-195行：sendAudio 方法
sendAudio = (data) => {
    // 立即发送，不合并
    this.sendPcmFrame(data);
};

// 第196-249行：sendPcmFrame 方法
sendPcmFrame = (data) => {
    // 构建帧并立即发送
    this.iat_ws.send(JSON.stringify(frame));
};
```

### 3. 完成回调（`ws_server/app/event/hw/stop_listen.js`）

```javascript
// 第541行：当收到 stop_listen 时
async iatCompleteCallback(text, chunkList) {
    // text 是最终识别结果："我要去故宫"
    // chunkList 是所有 PCM 包的列表（用于后续处理）
    this.context.ws.send(JSON.stringify({ type: "stt", text: text }));
}
```

---

## 总结

### 回答你的问题

**Q: 服务端接收后是否会合并成一个请求去请求 STT？**

**A: 不会。服务端采用流式处理：**

1. **接收端**：每个 Opus 包立即解码为 PCM，立即调用 `sendAudio()`
2. **发送端**：每个 PCM 包立即发送到讯飞 IAT 服务，作为独立的帧
3. **识别端**：讯飞 IAT 服务是流式识别，实时返回中间结果和最终结果

### 优势

- ✅ **低延迟**：不需要等待所有包到达，边接收边识别
- ✅ **实时反馈**：可以实时返回中间识别结果
- ✅ **动态修正**：后续帧可以修正前面的识别结果
- ✅ **内存效率**：不需要缓存所有音频数据

### 注意事项

- ⚠️ **顺序保证**：必须保证 Opus 包的发送顺序，否则识别会出错
- ⚠️ **连接状态**：如果 IAT 服务连接未建立，会先缓存到 `sendQueue`，连接建立后批量发送
- ⚠️ **结束标志**：必须发送 `STATUS_LAST_FRAME`（空数据）才能获得最终识别结果

