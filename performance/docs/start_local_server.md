# 启动本地 ws_server 服务

## 前置要求
1. Node.js >= 18
2. 已安装 ws_server 的依赖（npm install）

## 启动步骤

### 1. 进入 ws_server 目录
```bash
cd ws_server
```

### 2. 启动服务器（开发模式）
```bash
npm run dev
```

或者直接运行：
```bash
NODE_ENV=dev node start.js
```

**Windows PowerShell:**
```powershell
$env:NODE_ENV="dev"; node start.js
```

### 3. 服务器配置
- 端口：8081（在 config/dev.js 中配置）
- WebSocket 地址：`ws://localhost:8081`

### 4. 验证服务器启动
服务器启动后会显示：
- 服务器端口信息
- Redis 连接状态
- 其他初始化信息

## 测试脚本配置

测试脚本已默认连接到本地服务器：`ws://localhost:8081`

如果需要连接远程服务器，设置环境变量：
```bash
export WS_SERVER_HOST=ws://toyaiws.spacechaintech.com:8081
```

**Windows PowerShell:**
```powershell
$env:WS_SERVER_HOST="ws://toyaiws.spacechaintech.com:8081"
```

## 运行测试

在另一个终端窗口运行：
```bash
cd performance
python test_runner.py
```

## 查看日志

服务器端日志会直接输出到控制台，可以看到：
- 接收到的音频数据大小
- Opus 解码结果
- IAT 服务状态
- STT 识别结果
- LLM 调用
- TTS 事件

## 注意事项

1. **Redis 连接**：确保 Redis 服务可用（config/dev.js 中配置）
2. **依赖服务**：确保 IAT、LLM、TTS 等服务的 API 密钥已配置
3. **端口冲突**：确保 8081 端口未被占用

