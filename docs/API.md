# 语音对话测试平台 - API文档

## 1. REST API

### 1.1 测试控制API

#### POST /api/start
开始批量测试

**请求体**:
```json
{
  "concurrency": 10,
  "device_sns": ["SN001", "SN002"],
  "test_mode": "normal",
  "test_count": 15,
  "ws_url": "ws://example.com:8081"
}
```

**参数说明**:
- `concurrency` (int): 并发数（1-100）
- `device_sns` (array): 设备SN列表
- `test_mode` (string): 测试模式（"normal" 或 "fast"）
- `test_count` (int, 可选): 测试数量，留空则测试所有文件
- `ws_url` (string, 可选): WebSocket服务器地址

**响应**:
```json
{
  "status": "started"
}
```

#### POST /api/stop
停止测试

**响应**:
```json
{
  "status": "stopped"
}
```

#### POST /api/single-test
执行单语音测试

**请求体**:
```json
{
  "text": "你好，我想购买人参乌梅片",
  "device_sns": ["SN001"],
  "test_mode": "normal",
  "ws_url": "ws://example.com:8081"
}
```

**参数说明**:
- `text` (string, 必需): 要测试的文字
- `device_sns` (array, 可选): 设备SN列表，留空使用默认配置
- `test_mode` (string): 测试模式（"normal" 或 "fast"）
- `ws_url` (string, 可选): WebSocket服务器地址

**响应**:
```json
{
  "status": "started"
}
```

### 1.2 报告API

#### GET /api/report
获取测试报告（JSON格式）

**响应**:
```json
{
  "test_info": {
    "start_time": "2025-11-21T10:00:00",
    "end_time": "2025-11-21T10:05:00",
    "duration_seconds": 300,
    "concurrency": 10,
    "device_count": 2,
    "test_mode": "normal",
    "test_count": 15,
    "total_opus_files": 30
  },
  "test_environment": {
    "websocket_server": "ws://example.com:8081",
    "device_sns": ["SN001", "SN002"],
    "python_version": "3.9.0",
    "platform": "win32"
  },
  "test_cases": [...],
  "summary": {...},
  "performance_metrics": {...},
  "failure_analysis": {...},
  "timeline": [...]
}
```

#### GET /api/report/pdf
导出PDF报告

**响应**: PDF文件（application/pdf）

#### GET /api/report/csv
导出CSV报告

**响应**: CSV文件（text/csv，UTF-8 BOM编码）

#### GET /api/report/json
导出JSON报告

**响应**: JSON文件（application/json）

### 1.3 状态API

#### GET /api/status
获取测试状态

**响应**:
```json
{
  "is_running": false,
  "progress": 10,
  "total": 15,
  "summary": {
    "total": 10,
    "successful": 8,
    "failed": 2,
    "success_rate": 80.0
  }
}
```

#### GET /api/results
获取测试结果

**响应**:
```json
{
  "results": [...],
  "summary": {...}
}
```

## 2. WebSocket事件

### 2.1 客户端发送事件
无（当前版本客户端不发送事件）

### 2.2 服务器发送事件

#### test_started
测试开始事件

**数据**:
```json
{
  "start_time": "2025-11-21T10:00:00",
  "total": 15,
  "total_opus_files": 30,
  "concurrency_count": 10
}
```

#### test_result
测试结果更新事件

**数据**:
```json
{
  "result": {
    "index": 1,
    "type": "inquiry",
    "success": true,
    "text": "你好，我想购买人参乌梅片",
    "stt_text": "你好，我想购买人参乌梅片",
    "llm_text": "好的，我来为您查找...",
    "stt_latency": 1234.56,
    "llm_latency": 2345.67,
    "tts_latency": 345.67,
    "e2e_response_time": 3926.90
  },
  "current_test": {...}
}
```

#### progress_update
进度更新事件

**数据**:
```json
{
  "progress": 10,
  "total": 15,
  "total_opus_files": 30,
  "summary": {
    "total": 10,
    "successful": 8,
    "failed": 2,
    "success_rate": 80.0
  }
}
```

#### test_completed
测试完成事件

**数据**:
```json
{
  "end_time": "2025-11-21T10:05:00",
  "summary": {...},
  "results": [...]
}
```

#### test_error
测试错误事件

**数据**:
```json
{
  "error": "错误信息"
}
```

#### single_test_start
单语音测试开始事件

**数据**:
```json
{
  "text": "你好，我想购买人参乌梅片",
  "status": "正在生成TTS音频..."
}
```

#### single_test_complete
单语音测试完成事件

**数据**:
```json
{
  "result": {
    "success": true,
    "text": "你好，我想购买人参乌梅片",
    "stt_text": "你好，我想购买人参乌梅片",
    "llm_text": "好的，我来为您查找...",
    "stt_latency": 1234.56,
    "llm_latency": 2345.67,
    "tts_latency": 345.67,
    "e2e_response_time": 3926.90
  },
  "text": "你好，我想购买人参乌梅片"
}
```

#### single_test_error
单语音测试错误事件

**数据**:
```json
{
  "error": "错误信息"
}
```

## 3. 数据模型

### 3.1 测试结果模型
```typescript
interface TestResult {
  index: number;              // 测试索引
  type: string;               // 测试类型（inquiry/compare/order/single）
  success: boolean;           // 是否成功
  text: string;              // 请求文本
  stt_text: string;          // STT识别文本
  llm_text: string;          // LLM回复文本
  response_text: string;     // 完整响应文本
  audio_file: string;        // 音频文件路径
  connection_id: number;      // 连接ID
  device_sn: string;         // 设备SN
  stt_latency: number;       // STT延迟（毫秒）
  llm_latency: number;       // LLM延迟（毫秒）
  tts_latency: number;       // TTS延迟（毫秒）
  e2e_response_time: number; // 端到端响应时间（毫秒）
  failure_reason: string;    // 失败原因
  error: string;            // 错误信息
  timestamp: string;         // 时间戳
  sent_messages: number;     // 发送消息数
  received_messages: number; // 接收消息数
  total_sent_bytes: number;  // 发送字节数
  total_received_bytes: number; // 接收字节数
}
```

### 3.2 性能指标模型
```typescript
interface PerformanceMetrics {
  stt_latency: {
    min: number;
    max: number;
    avg: number;
    median: number;
    p95: number;
    p99: number;
    count: number;
  };
  llm_latency: {...};
  tts_latency: {...};
  e2e_response_time: {...};
}
```

### 3.3 测试报告模型
```typescript
interface TestReport {
  test_info: {
    start_time: string;
    end_time: string;
    duration_seconds: number;
    concurrency: number;
    device_count: number;
    test_mode: string;
    test_count: number;
    total_opus_files: number;
  };
  test_environment: {
    websocket_server: string;
    device_sns: string[];
    python_version: string;
    platform: string;
  };
  test_cases: TestResult[];
  summary: {
    total_tests: number;
    successful_tests: number;
    failed_tests: number;
    success_rate: number;
    qps: number;
    inquiry_total: number;
    inquiry_success: number;
    inquiry_success_rate: number;
    compare_total: number;
    compare_success: number;
    compare_success_rate: number;
    order_total: number;
    order_success: number;
    order_success_rate: number;
  };
  performance_metrics: PerformanceMetrics;
  failure_analysis: {
    failure_reasons: {[reason: string]: number};
    failure_rate: number;
  };
  timeline: Array<{
    index: number;
    timestamp: string;
    type: string;
    success: boolean;
    e2e_response_time: number;
  }>;
  export_info?: {
    export_time: string;
    export_format: string;
    version: string;
  };
}
```

## 4. 错误处理

### 4.1 HTTP错误码
- `400` - 请求参数错误
- `500` - 服务器内部错误

### 4.2 错误响应格式
```json
{
  "error": "错误信息"
}
```

## 5. 使用示例

### 5.1 批量测试
```javascript
// 开始测试
fetch('/api/start', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    concurrency: 10,
    device_sns: ['SN001', 'SN002'],
    test_mode: 'normal',
    test_count: 15
  })
});

// 监听WebSocket事件
socket.on('test_started', (data) => {
  console.log('测试开始', data);
});

socket.on('test_result', (data) => {
  console.log('测试结果', data);
});

socket.on('test_completed', (data) => {
  console.log('测试完成', data);
});
```

### 5.2 单语音测试
```javascript
// 执行单语音测试
fetch('/api/single-test', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    text: '你好，我想购买人参乌梅片',
    test_mode: 'normal'
  })
});

// 监听WebSocket事件
socket.on('single_test_start', (data) => {
  console.log('单语音测试开始', data);
});

socket.on('single_test_complete', (data) => {
  console.log('单语音测试完成', data);
});
```

### 5.3 导出报告
```javascript
// 导出PDF
window.open('/api/report/pdf');

// 导出CSV
const link = document.createElement('a');
link.href = '/api/report/csv';
link.download = '测试报告.csv';
link.click();

// 导出JSON
const link = document.createElement('a');
link.href = '/api/report/json';
link.download = '测试报告.json';
link.click();
```

