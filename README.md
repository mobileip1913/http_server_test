# Web测试服务

这是语音对话测试平台的Web服务模块，提供基于Flask的Web界面和实时测试功能。

## 目录结构

```
http_server/
├── web_server.py          # Flask Web服务器主文件
├── test_inquiries.py     # 测试逻辑（询问和购买测试）
├── websocket_client.py   # WebSocket客户端封装
├── config.py             # 配置文件
├── logger.py             # 日志工具
├── utils.py              # 工具函数
├── audio_encoder.py      # 音频编码器
├── start_web_server.py   # 启动脚本
├── start_web.bat         # Windows启动脚本
├── requirements.txt      # Python依赖
├── templates/            # HTML模板
│   └── test_dashboard.html
├── static/               # 静态资源
│   ├── css/
│   │   └── dashboard.css
│   └── js/
│       └── dashboard.js
└── audio/                # 测试音频文件
    └── inquiries/        # 询问和购买音频文件
```

## 功能特性

- **Web界面**: 提供可视化的测试控制面板
- **实时监控**: 通过WebSocket实时显示测试进度和结果
- **并发测试**: 支持多设备并发测试
- **性能分析**: 提供详细的性能指标和统计报告
- **PDF导出**: 支持将测试报告导出为PDF格式

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

**Windows:**
```bash
start_web.bat
```

**Linux/Mac:**
```bash
python start_web_server.py
```

### 访问界面

打开浏览器访问: http://localhost:5000

## 配置说明

主要配置在 `config.py` 中，包括：
- WebSocket服务器地址
- 设备SN列表
- 测试超时时间
- 音频编码参数

## 注意事项

- 确保 `audio/inquiries/` 目录下有测试音频文件
- 根据实际环境修改 `config.py` 中的WebSocket服务器地址
- 测试前确保目标WebSocket服务器可访问

