# Opus文件管理功能设计文档

## 1. 功能概述

### 1.1 目标
创建一个Opus文件管理页面，提供可视化的文件管理功能，包括：
- 查看所有Opus文件及其对应的文本内容
- 删除Opus文件
- 上传文本文件并自动生成Opus文件

### 1.2 用户场景
1. **查看文件列表**：测试人员需要查看当前有哪些测试音频文件，以及每个文件对应的文本内容
2. **删除文件**：测试人员发现某个测试音频不合适，需要删除
3. **批量添加文件**：测试人员上传文本文件，系统自动生成对应的Opus音频文件

## 2. 功能设计

### 2.1 页面入口
- 在测试仪表板中，点击"Opus文件: XX"链接，进入管理页面
- 管理页面为独立页面，可通过URL直接访问：`/opus-management`

### 2.2 页面布局

#### 2.2.1 顶部导航栏
- 页面标题："Opus文件管理"
- 返回按钮：返回测试仪表板
- 统计信息：显示总文件数（按类型分类）

#### 2.2.2 文件列表区域
- **分类标签页**：三个标签页（询问、对比、下单）
- **文件列表**：每个标签页下显示对应类型的文件
  - 文件编号（001, 002, ...）
  - 文件名（inquiry_001.opus）
  - 对应文本内容（显示完整文本，可展开/收起）
  - 操作按钮（删除、播放音频）
  - 文件大小、创建时间（可选）

#### 2.2.3 上传区域
- **上传文本文件**：
  - 文件选择器（支持.txt文件）
  - 类型选择（询问/对比/下单）
  - 上传按钮
  - 进度显示（生成进度）
- **批量上传**：支持一次上传多个文件

### 2.3 交互设计

#### 2.3.1 文件列表
- 表格形式展示，每行一个文件
- 文本内容默认显示前50个字符，点击展开显示完整内容
- 删除按钮有确认对话框
- 播放按钮使用HTML5 audio标签播放

#### 2.3.2 上传流程
1. 用户选择文件
2. 选择文件类型（询问/对比/下单）
3. 点击上传
4. 显示进度（"正在生成第X个文件..."）
5. 完成后刷新文件列表

#### 2.3.3 删除流程
1. 用户点击删除按钮
2. 弹出确认对话框（显示文件名和文本内容）
3. 确认后删除文件
4. 更新file_list.txt
5. 刷新文件列表

## 3. 技术设计

### 3.1 后端API设计

#### 3.1.1 获取文件列表
```
GET /api/opus/list
Response: {
    "inquiries": [
        {
            "index": "001",
            "filename": "inquiry_001.opus",
            "text": "你好，我想买点东北大米...",
            "file_size": 12345,
            "created_time": "2025-11-21T10:00:00"
        },
        ...
    ],
    "compares": [...],
    "orders": [...],
    "total": {
        "inquiries": 10,
        "compares": 10,
        "orders": 10,
        "all": 30
    }
}
```

#### 3.1.2 删除文件
```
DELETE /api/opus/delete
Request Body: {
    "filename": "inquiry_001.opus",
    "type": "inquiry"  // inquiry/compare/order
}
Response: {
    "success": true,
    "message": "文件已删除"
}
```

#### 3.1.3 上传文本文件并生成Opus
```
POST /api/opus/upload
Request: multipart/form-data
- file: 文本文件（.txt）
- type: 文件类型（inquiry/compare/order）
- force: 是否强制重新生成（可选，默认false）

Response: {
    "success": true,
    "message": "成功生成X个文件",
    "generated_files": [
        {
            "index": "011",
            "filename": "inquiry_011.opus",
            "text": "文本内容"
        },
        ...
    ]
}
```

#### 3.1.4 获取文件内容（用于播放）
```
GET /api/opus/file/<filename>
Response: 音频文件流（Content-Type: audio/opus）
```

### 3.2 文件名生成规则

#### 3.2.1 自动编号
- 扫描现有文件，找到最大编号
- 新文件编号 = 最大编号 + 1
- 格式：`{type}_{index:03d}.opus`
- 示例：如果已有inquiry_001到inquiry_010，新文件为inquiry_011

#### 3.2.2 编号查找逻辑
```python
def get_next_index(audio_dir, file_type):
    """获取下一个可用的文件编号"""
    pattern = f"{file_type}_*.opus"
    existing_files = glob.glob(os.path.join(audio_dir, pattern))
    if not existing_files:
        return 1
    
    indices = []
    for file in existing_files:
        basename = os.path.basename(file)
        match = re.match(rf"{file_type}_(\d+)\.opus", basename)
        if match:
            indices.append(int(match.group(1)))
    
    return max(indices) + 1 if indices else 1
```

### 3.3 文件更新逻辑

#### 3.3.1 删除文件后
1. 删除物理文件
2. 从对应的文本文件中删除对应行（如果存在）
3. 重新生成file_list.txt

#### 3.3.2 生成文件后
1. 生成Opus文件
2. 追加到对应的文本文件（inquiries.txt/compares.txt/orders.txt）
3. 更新file_list.txt

### 3.4 前端实现

#### 3.4.1 页面结构
- HTML模板：`templates/opus_management.html`
- CSS样式：复用dashboard.css，新增管理页面样式
- JavaScript：`static/js/opus_management.js`

#### 3.4.2 主要功能函数
- `loadFileList()`: 加载文件列表
- `deleteFile(filename, type)`: 删除文件
- `uploadFile(file, type)`: 上传并生成文件
- `playAudio(filename)`: 播放音频
- `updateFileList()`: 刷新文件列表

## 4. 数据流设计

### 4.1 文件列表加载流程
```
前端请求 → GET /api/opus/list
后端扫描audio/inquiries/目录
读取file_list.txt（如果存在）
解析inquiries.txt, compares.txt, orders.txt
返回JSON数据
前端渲染表格
```

### 4.2 文件删除流程
```
用户点击删除 → 确认对话框
确认后 → DELETE /api/opus/delete
后端删除文件 → 更新文本文件 → 更新file_list.txt
返回成功 → 前端刷新列表
```

### 4.3 文件上传流程
```
用户选择文件 → 选择类型 → 点击上传
POST /api/opus/upload
后端解析文本文件（每行一个文本）
循环生成Opus文件（调用generate_tts_audio.py）
更新文本文件 → 更新file_list.txt
返回生成结果 → 前端刷新列表
```

## 5. 错误处理

### 5.1 文件不存在
- 返回404错误
- 前端显示"文件不存在"

### 5.2 生成失败
- 记录失败的文件和原因
- 返回部分成功的结果
- 前端显示成功和失败的统计

### 5.3 文件格式错误
- 验证文件扩展名（.txt）
- 验证文件编码（UTF-8）
- 返回友好的错误提示

## 6. 性能考虑

### 6.1 文件列表加载
- 如果文件数量很大（>100），考虑分页
- 文本内容默认只显示摘要，点击展开

### 6.2 批量生成
- 异步处理，使用后台任务
- 实时返回进度（WebSocket或轮询）
- 支持取消操作

## 7. 安全考虑

### 7.1 文件上传
- 验证文件类型（只允许.txt）
- 限制文件大小（如10MB）
- 验证文件内容（防止恶意代码）

### 7.2 文件删除
- 确认对话框防止误删
- 记录删除日志（可选）

## 8. 未来扩展

### 8.1 功能扩展
- 文件编辑（修改文本内容，重新生成音频）
- 文件重命名
- 批量删除
- 文件搜索和过滤
- 导入/导出功能

### 8.2 性能优化
- 文件列表缓存
- 异步生成进度显示
- 文件预览（音频波形图）

## 9. 实现优先级

### Phase 1（核心功能）
1. ✅ 文件列表展示
2. ✅ 删除文件
3. ✅ 上传文本文件生成Opus

### Phase 2（增强功能）
1. 播放音频
2. 文件搜索
3. 批量操作

### Phase 3（高级功能）
1. 文件编辑
2. 导入/导出
3. 统计分析

