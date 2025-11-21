# 文件组织说明

本文档说明了 performance 目录下所有文件的用途和分类。

## 文件分类

### 📁 核心文件（必须保留）

这些文件是测试工具的核心组件，必须保留：

1. **`test_runner.py`** - 主测试运行器
   - 功能：管理并发连接、协调测试流程、生成报告
   - 状态：✅ 核心文件

2. **`websocket_client.py`** - WebSocket 客户端实现
   - 功能：WebSocket 连接、消息发送/接收、事件处理
   - 状态：✅ 核心文件

3. **`audio_encoder.py`** - 音频编码器
   - 功能：Opus 编码、数据包分割、格式转换
   - 状态：✅ 核心文件

4. **`config.py`** - 配置文件
   - 功能：所有配置项定义、环境变量处理
   - 状态：✅ 核心文件

5. **`logger.py`** - 日志系统
   - 功能：日志记录、格式化、文件输出
   - 状态：✅ 核心文件

6. **`metrics_collector.py`** - 指标收集器
   - 功能：性能指标收集、统计计算
   - 状态：✅ 核心文件

7. **`utils.py`** - 工具函数
   - 功能：通用工具函数（百分位数计算等）
   - 状态：✅ 核心文件

### 🛠️ 工具文件（可选保留）

这些文件是辅助工具，可根据需要保留或删除：

1. **`generate_tts_audio.py`** - 讯飞 TTS 音频生成工具
   - 功能：生成测试用的 Opus 音频文件
   - 状态：🟡 工具文件，建议保留

2. **`local_transcribe.py`** - 本地 Whisper 转录工具
   - 功能：使用本地 Whisper 验证音频内容
   - 状态：🟡 工具文件，可选

3. **`raasr_transcribe.py`** - 讯飞 RAASR 转录工具
   - 功能：使用讯飞 RAASR API 转录音频（已废弃，额度不足）
   - 状态：🔴 已废弃，可删除

### 🗑️ 临时调试文件（建议删除）

这些文件是调试过程中创建的临时工具，可以删除：

1. **`analyze_opus_conversion.py`** - Opus 转换分析工具
   - 状态：🔴 临时文件，可删除
   - 说明：功能已集成到 `audio_encoder.py`

2. **`extract_opus_from_ogg.py`** - Ogg 提取工具
   - 状态：🔴 临时文件，可删除
   - 说明：功能已集成到 `audio_encoder.py`

3. **`verify_extracted_opus.py`** - Opus 验证工具
   - 状态：🔴 临时文件，可删除
   - 说明：用于调试，不再需要

4. **`verify_generated_opus.py`** - 生成 Opus 验证工具
   - 状态：🔴 临时文件，可删除
   - 说明：用于调试，不再需要

5. **`decode_opus_to_wav.py`** - Opus 解码工具
   - 状态：🔴 临时文件，可删除
   - 说明：用于调试，不再需要

6. **`split_opus_packets.py`** - Opus 包分割工具
   - 状态：🔴 临时文件，可删除
   - 说明：功能已集成到 `audio_encoder.py`

7. **`generate_mp3.py`** - MP3 生成工具
   - 状态：🟡 可选保留（用于试听）
   - 说明：用于将 Opus 转换为 MP3 试听

### 📄 文档文件

#### 主要文档（必须保留）

1. **`README.md`** - 主文档
   - 功能：使用说明、快速开始、配置说明
   - 状态：✅ 必须保留

2. **`PROJECT_STATUS.md`** - 项目状态文档
   - 功能：当前进度、已完成工作、问题列表
   - 状态：✅ 必须保留（本文档）

3. **`TECHNICAL_NOTES.md`** - 技术说明文档
   - 功能：技术实现细节、设备行为分析、服务器处理机制
   - 状态：✅ 必须保留（合并后的技术文档）

4. **`TROUBLESHOOTING.md`** - 故障排查指南
   - 功能：常见问题、解决方案、调试技巧
   - 状态：✅ 必须保留（合并后的故障排查文档）

#### 已合并的文档（可以删除）

以下文档内容已合并到 `TECHNICAL_NOTES.md` 和 `TROUBLESHOOTING.md`，可以删除：

1. **`DEVICE_VS_TEST_COMPARISON.md`** - 设备对比分析
   - 状态：🔴 已合并到 `TECHNICAL_NOTES.md`，可删除

2. **`SERVER_AUDIO_HANDLING.md`** - 服务器音频处理
   - 状态：🔴 已合并到 `TECHNICAL_NOTES.md`，可删除

3. **`AUDIO_FORMAT_ISSUE.md`** - 音频格式问题
   - 状态：🔴 已合并到 `TECHNICAL_NOTES.md`，可删除

4. **`OPTIMIZATION_SUMMARY.md`** - 优化总结
   - 状态：🔴 已合并到 `TECHNICAL_NOTES.md`，可删除

5. **`DEBUG_AUDIO_ISSUE.md`** - 音频调试指南
   - 状态：🔴 已合并到 `TROUBLESHOOTING.md`，可删除

6. **`CRITICAL_ISSUE_FOUND.md`** - 关键问题发现
   - 状态：🔴 已合并到 `PROJECT_STATUS.md`，可删除

#### 特殊用途文档（可选保留）

1. **`TEST_LLM_DUPLICATE_PREVENTION.md`** - LLM重复调用防护测试指南
   - 状态：🟡 可选保留（用于测试LLM防重复机制）

2. **`check_start_listen_logic.md`** - start_listen逻辑检查
   - 状态：🟡 可选保留（用于调试start_listen逻辑）

3. **`start_local_server.md`** - 本地服务器启动指南
   - 状态：✅ 建议保留（用于本地调试）

4. **`websocket_performance_test_design.md`** - 设计文档
   - 状态：🟡 可选保留（原始设计文档）

5. **`README_TTS.md`** - TTS音频生成工具使用说明
   - 状态：🟡 可选保留（如果使用TTS工具）

### 📜 配置文件

1. **`requirements.txt`** - Python 依赖
   - 状态：✅ 必须保留

2. **`run_test.bat`** - Windows 测试脚本
   - 状态：🟡 可选保留

3. **`run_test.sh`** - Linux/Mac 测试脚本
   - 状态：🟡 可选保留

4. **`start_ws_server.bat`** - Windows 本地服务器启动脚本
   - 状态：✅ 建议保留

5. **`start_ws_server.sh`** - Linux/Mac 本地服务器启动脚本
   - 状态：✅ 建议保留

### 📁 目录

1. **`audio/`** - 音频文件目录
   - 状态：✅ 必须保留
   - 内容：生成的测试音频文件

2. **`results/`** - 测试结果目录
   - 状态：✅ 必须保留
   - 内容：日志、CSV、JSON 结果文件

3. **`__pycache__/`** - Python 缓存目录
   - 状态：🔴 可删除（会被自动重新生成）

## 清理建议

### 可以安全删除的文件

```bash
# 临时调试文件
rm analyze_opus_conversion.py
rm extract_opus_from_ogg.py
rm verify_extracted_opus.py
rm verify_generated_opus.py
rm decode_opus_to_wav.py
rm split_opus_packets.py

# 已合并的文档
rm DEVICE_VS_TEST_COMPARISON.md
rm SERVER_AUDIO_HANDLING.md
rm AUDIO_FORMAT_ISSUE.md
rm OPTIMIZATION_SUMMARY.md
rm DEBUG_AUDIO_ISSUE.md
rm CRITICAL_ISSUE_FOUND.md

# 已废弃的工具
rm raasr_transcribe.py

# Python 缓存
rm -r __pycache__
```

### 建议保留的文件

- 所有核心文件（7个）
- 主要文档（4个）
- 工具文件（`generate_tts_audio.py`）
- 配置文件（`requirements.txt`）
- 启动脚本（`start_ws_server.*`）

## 文件依赖关系

```
test_runner.py
  ├── websocket_client.py
  │     ├── config.py
  │     ├── logger.py
  │     └── audio_encoder.py
  │           └── (需要 ffmpeg 和 opuslib)
  ├── metrics_collector.py
  └── utils.py

generate_tts_audio.py (独立工具)
local_transcribe.py (独立工具)
```

## 目录结构建议

```
performance/
├── README.md                    # 快速开始指南（根目录）
├── docs/                        # 文档目录
│   ├── README.md               # 完整使用说明
│   ├── PROJECT_STATUS.md       # 项目状态
│   ├── TECHNICAL_NOTES.md      # 技术说明
│   ├── TROUBLESHOOTING.md      # 故障排查
│   └── FILE_ORGANIZATION.md    # 本文档
│
├── requirements.txt             # Python 依赖
├── config.py                    # 配置文件
├── logger.py                    # 日志系统
├── utils.py                     # 工具函数
│
├── test_runner.py               # 主测试运行器
├── websocket_client.py          # WebSocket 客户端
├── audio_encoder.py             # 音频编码器
├── metrics_collector.py         # 指标收集器
│
├── generate_tts_audio.py        # TTS 音频生成工具
├── local_transcribe.py          # 本地转录工具（可选）
│
├── start_ws_server.bat          # Windows 启动脚本
├── start_ws_server.sh           # Linux/Mac 启动脚本
│
├── audio/                       # 音频文件目录
│   └── test_audio.opus          # 测试音频文件
│
└── results/                     # 测试结果目录
    ├── logs/                    # 日志文件
    ├── csv/                     # CSV 结果
    └── json/                    # JSON 结果
```

---

**最后更新**: 2025-11-05

**注意**: 本文档位于 `performance/docs/` 目录下

