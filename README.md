# 语音对话测试平台

专业的语音对话测试平台，提供基于Flask的Web界面、实时测试监控和完整的测试报告功能。支持商品询问、商品对比、商品下单三种测试场景。

## 功能特性

### 🎯 核心功能
- **Web界面**: 提供可视化的测试控制面板
- **实时监控**: 通过WebSocket实时显示测试进度和结果
- **并发测试**: 支持多设备并发测试
- **三种测试类型**: 支持商品询问、商品对比、商品下单测试
- **随机选择**: 支持从所有音频文件中随机选择指定数量的测试
- **性能分析**: 提供详细的性能指标和统计报告

### 📊 测试报告（专业测试团队使用）
- **PDF报告**: 包含测试信息、环境信息、统计、性能指标、失败分析
- **CSV报告**: 详细的测试用例列表，包含所有测试数据（Excel可打开）
- **JSON报告**: 完整的测试结果数据，便于程序化分析
- **报告内容**:
  - 测试信息和环境信息
  - 总体统计（成功率、吞吐量、各类型测试统计）
  - 性能指标（STT/LLM/TTS延迟、端到端响应时间的统计值）
  - 失败分析和失败用例详情
  - 每个测试用例的完整数据（请求/响应文本、延迟数据、错误信息等）

### 🎤 TTS音频生成工具
- **单个音频生成**: `generate_tts_audio.py` - 快速生成单个测试音频
- **批量音频生成**: `generate_batch_tts.py` - 批量生成多个测试音频文件
- **支持格式**: Opus（测试用）、MP3（播放测试用）

## 目录结构

```
http_server/
├── web_server.py              # Flask Web服务器主文件
├── test_inquiries.py          # 测试逻辑（询问、对比、下单测试）
├── websocket_client.py        # WebSocket客户端封装
├── config.py                  # 配置文件
├── logger.py                  # 日志工具
├── utils.py                   # 工具函数
├── audio_encoder.py           # 音频编码器
├── generate_tts_audio.py     # 单个TTS音频生成工具
├── generate_batch_tts.py      # 批量TTS音频生成工具
├── start_web_server.py        # 启动脚本
├── start_web.bat              # Windows启动脚本
├── requirements.txt           # Python依赖
├── templates/                 # HTML模板
│   └── test_dashboard.html
├── static/                    # 静态资源
│   ├── css/
│   │   └── dashboard.css
│   └── js/
│       └── dashboard.js
├── audio/                     # 测试音频文件
│   └── inquiries/            # 询问、对比、下单音频文件
│       ├── inquiries.txt     # 询问文本文件（可选）
│       ├── compares.txt      # 对比文本文件（可选）
│       ├── orders.txt        # 下单文本文件（可选）
│       ├── file_list.txt     # 音频文件映射文件（自动生成）
│       ├── inquiry_001.opus  # 询问音频文件
│       ├── compare_001.opus  # 对比音频文件
│       └── order_001.opus    # 下单音频文件
└── libs/                      # 外部依赖库
    └── opus.dll              # Opus库（Windows，自动加载）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

**系统依赖**:
- **FFmpeg**: 用于音频格式转换（必须）
- **Opus DLL**: Windows系统需要 `opus.dll`（已包含在 `libs/` 目录，自动加载）

### 2. 准备测试音频文件

#### 方式一：使用批量生成工具（推荐）

```bash
# 方式1：使用三个独立文件（推荐）
# 创建 audio/inquiries/inquiries.txt（每行一个问题）
# 创建 audio/inquiries/compares.txt（每行一个问题）
# 创建 audio/inquiries/orders.txt（每行一个问题）
python generate_batch_tts.py

# 方式2：使用单个文件（指定类型）
python generate_batch_tts.py --input my_questions.txt --type inquiry

# 方式3：使用组合文件（用 "---" 分隔三个部分）
python generate_batch_tts.py --input combined.txt

# 强制重新生成所有文件
python generate_batch_tts.py --force
```

#### 方式二：使用单个音频生成工具

```bash
# 生成默认文本的Opus文件
python generate_tts_audio.py

# 生成自定义文本的Opus文件
python generate_tts_audio.py 你好，我想购买人参乌梅片

# 生成MP3文件（用于播放测试）
python generate_tts_audio.py 测试语音合成 --mp3
```

### 3. 启动服务

**Windows:**
```bash
start_web.bat
```

**Linux/Mac:**
```bash
python start_web_server.py
```

### 4. 访问界面

打开浏览器访问: http://localhost:5000

## 使用说明

### Web界面操作

1. **配置测试参数**:
   - 点击"设置"按钮
   - 配置设备SN列表（每行一个）
   - 设置并发数（1-100）
   - 选择测试模式（正常模式/急速模式）
   - 设置测试数量（可选，留空则测试所有文件）
   - 配置WebSocket服务器地址（可选）

2. **开始测试**:
   - 点击"开始测试"按钮
   - 在"实时对话流"面板查看每个测试的对话过程
   - 顶部统计卡片显示总体测试情况

3. **查看报告**:
   - 测试完成后（或测试过程中），点击"查看报告"按钮
   - 可以导出PDF、CSV或JSON格式的报告
   - PDF报告：适合打印和查看
   - CSV报告：适合Excel分析和数据处理
   - JSON报告：适合程序化分析和集成

4. **停止测试**:
   - 测试过程中可随时点击"停止测试"按钮

### TTS音频生成工具使用

#### `generate_tts_audio.py` - 单个音频生成

**基本用法**:
```bash
# 使用默认文本生成Opus
python generate_tts_audio.py

# 指定文本生成Opus
python generate_tts_audio.py 你好，我想购买人参乌梅片

# 生成MP3格式
python generate_tts_audio.py --mp3
python generate_tts_audio.py 测试文本 --mp3
```

**输出文件**:
- `audio/test_audio.opus` - Opus格式（测试用）
- `audio/test_audio.mp3` - MP3格式（播放测试用）

#### `generate_batch_tts.py` - 批量音频生成

**方式一：使用三个独立文件（推荐）**
```bash
# 创建以下文件（每行一个问题）:
# - audio/inquiries/inquiries.txt
# - audio/inquiries/compares.txt
# - audio/inquiries/orders.txt

python generate_batch_tts.py
```

**方式二：使用单个文件（指定类型）**
```bash
# 读取单个文件作为询问类型
python generate_batch_tts.py --input my_questions.txt --type inquiry

# 读取单个文件作为对比类型
python generate_batch_tts.py --input my_questions.txt --type compare

# 读取单个文件作为下单类型
python generate_batch_tts.py --input my_questions.txt --type order
```

**方式三：使用组合文件**
```bash
# 创建 combined.txt，格式如下：
# 询问问题1
# 询问问题2
# ---
# 对比问题1
# 对比问题2
# ---
# 下单问题1
# 下单问题2

python generate_batch_tts.py --input combined.txt
```

**参数说明**:
- `--force`: 强制重新生成所有文件（即使文件已存在）
- `--input <file>`: 指定输入文件路径
- `--type <inquiry|compare|order>`: 指定文件类型（与 `--input` 一起使用）

**输出文件**:
- `audio/inquiries/inquiry_001.opus`, `inquiry_002.opus`, ...
- `audio/inquiries/compare_001.opus`, `compare_002.opus`, ...
- `audio/inquiries/order_001.opus`, `order_002.opus`, ...
- `audio/inquiries/file_list.txt` - 自动生成的映射文件

## 测试报告说明

### PDF报告
包含以下内容：
- 测试信息（开始/结束时间、持续时间、并发数、设备数量、测试模式）
- 测试环境（WebSocket服务器、设备SN列表、Python版本、运行平台）
- 总体统计（总测试数、成功/失败数、成功率、吞吐量、各类型测试统计）
- 性能指标（STT/LLM/TTS延迟、端到端响应时间的平均值、中位数、P95、P99、最小值、最大值）
- 失败分析（失败原因统计和占比）
- 失败测试用例详情（前20个，完整列表在CSV/JSON中）

### CSV报告
包含完整的测试数据，适合Excel分析：
- 测试信息和环境信息
- 总体统计和性能指标
- 失败分析
- **详细测试用例列表**（每个测试的完整信息）:
  - 测试ID、时间戳、类型、索引、状态
  - 请求文本、STT文本、LLM文本
  - 音频文件、连接ID、设备SN
  - STT/LLM/TTS延迟、端到端响应时间
  - 失败原因、错误信息
  - 发送/接收消息数和字节数

### JSON报告
包含完整的测试结果数据，适合程序化分析：
- 所有PDF和CSV报告中的数据
- 完整的测试用例列表（JSON格式）
- 导出元数据（导出时间、格式、版本）

## 配置说明

主要配置在 `config.py` 中，包括：
- WebSocket服务器地址
- 设备SN列表
- 测试超时时间
- 音频编码参数

### 讯飞TTS API配置

TTS音频生成使用的API密钥在 `generate_tts_audio.py` 中配置：
```python
XFYUN_APPID = "c7f30371"
XFYUN_API_KEY = "50e273869438ea2fc41e44a32167ef6d"
XFYUN_API_SECRET = "OGIxYmY1OGM2OWZkNTcyMGE4YzM2NTM0"
```

## 性能指标说明

测试报告中的性能指标从专业测试角度设计：

- **STT服务延迟**: 从发送音频到收到STT识别结果的时间
- **LLM服务延迟**: 从收到STT结果到收到LLM响应的时间
- **TTS服务延迟**: 从收到LLM响应到收到TTS开始的时间
- **端到端响应时间**: 从发送音频到收到完整TTS响应的时间

每个指标都提供：平均值、中位数、P95、P99、最小值、最大值、样本数

## 注意事项

1. **音频文件准备**:
   - 确保 `audio/inquiries/` 目录下有测试音频文件
   - 音频文件命名格式：`inquiry_XXX.opus`, `compare_XXX.opus`, `order_XXX.opus`
   - 可以使用 `generate_batch_tts.py` 批量生成

2. **系统依赖**:
   - 必须安装 FFmpeg（用于音频格式转换）
   - Windows系统需要 `opus.dll`（已包含在 `libs/` 目录，自动加载）

3. **网络连接**:
   - 测试前确保目标WebSocket服务器可访问
   - TTS音频生成需要访问讯飞TTS API

4. **测试配置**:
   - 根据实际环境修改 `config.py` 中的WebSocket服务器地址
   - 或在Web界面中配置WebSocket服务器地址

5. **测试数量设置**:
   - 如果设置了测试数量，系统会从所有音频文件中随机选择
   - 三种类型（询问、对比、下单）平均分配，有余数随机分配
   - 留空则测试所有找到的音频文件

## 常见问题

### Q: 如何只生成一种类型的音频文件？
A: 使用 `generate_batch_tts.py --input <file> --type <inquiry|compare|order>`

### Q: 可以只读一个文件吗？
A: 可以。脚本支持三种方式：
1. 只创建 `inquiries.txt`（或 `compares.txt` 或 `orders.txt`）中的一个
2. 使用 `--input` 指定单个文件，配合 `--type` 指定类型
3. 使用组合文件，但只填写一个部分

### Q: 测试报告在哪里？
A: 在Web界面中点击"查看报告"按钮，可以查看和导出PDF/CSV/JSON格式的报告。

### Q: CSV报告在Excel中打开中文乱码？
A: CSV文件使用UTF-8 BOM编码，Excel应该能正确显示。如果仍有问题，可以在Excel中选择"数据" -> "从文本/CSV导入"，选择UTF-8编码。

## 技术支持

如有问题，请检查：
1. 日志文件中的错误信息
2. Web界面中的错误提示
3. 测试报告中的失败分析
