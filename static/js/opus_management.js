// Opus文件管理页面JavaScript

let fileData = {
    files: [],
    total: 0
};
let deleteTarget = null;

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadFileList();
});

// 加载文件列表
async function loadFileList() {
    try {
        const response = await fetch('/api/opus/list');
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        fileData = data;
        
        // 更新统计信息
        updateStats();
        
        // 显示文件列表
        renderFileTable();
    } catch (error) {
        showError('加载文件列表失败: ' + error.message);
    }
}

// 更新统计信息
function updateStats() {
    // 统一管理，只显示总数
    const statTotal = document.getElementById('statTotal');
    if (statTotal) {
        statTotal.textContent = fileData.total || 0;
    }
}

// 渲染文件表格
function renderFileTable() {
    const tbody = document.getElementById('fileTableBody');
    const files = fileData.files || [];
    
    if (files.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; padding: 40px; color: var(--text-muted);">
                    暂无文件
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = files.map(file => {
        const hasText = file.text && file.text.trim().length > 0;
        const textPreview = hasText && file.text.length > 50 
            ? escapeHtml(file.text.substring(0, 50)) + '...' 
            : (hasText ? escapeHtml(file.text) : '<span style="color: var(--text-muted); font-style: italic;">（无文本）</span>');
        const fileSize = formatFileSize(file.file_size);
        const fullText = escapeHtml(file.text || '');
        const escapedText = escapeHtml(file.text || '').replace(/'/g, "&#39;").replace(/"/g, "&quot;");
        
        return `
            <tr>
                <td>${file.index}</td>
                <td>${escapeHtml(file.filename)}</td>
                <td>
                    <span class="text-preview" title="${escapedText}">${textPreview}</span>
                    ${hasText && file.text.length > 50 ? '<button class="btn-text" onclick="toggleText(this)">展开</button>' : ''}
                    <div class="text-full" style="display: none;">${fullText}</div>
                </td>
                <td>${fileSize}</td>
                <td>
                    <button class="btn btn-small btn-danger" onclick="deleteFile('${escapeHtml(file.filename)}', '${escapedText}')" style="margin-right: 5px;">
                        删除
                    </button>
                    <button class="btn btn-small btn-primary" onclick="testOpusFile('${escapeHtml(file.filename)}', '${escapedText}')">
                        测试
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// 切换文本展开/收起
function toggleText(btn) {
    const row = btn.closest('tr');
    const preview = row.querySelector('.text-preview');
    const full = row.querySelector('.text-full');
    
    if (full.style.display === 'none') {
        preview.style.display = 'none';
        full.style.display = 'block';
        btn.textContent = '收起';
    } else {
        preview.style.display = 'block';
        full.style.display = 'none';
        btn.textContent = '展开';
    }
}

// HTML转义函数
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// 删除文件
function deleteFile(filename, text) {
    deleteTarget = { filename, text };
    document.getElementById('deleteFileName').textContent = filename;
    document.getElementById('deleteFileText').textContent = text.length > 100 ? text.substring(0, 100) + '...' : text;
    document.getElementById('deleteModal').style.display = 'flex';
}

// 关闭删除确认对话框
function closeDeleteModal() {
    document.getElementById('deleteModal').style.display = 'none';
    deleteTarget = null;
}

// 确认删除
async function confirmDelete() {
    if (!deleteTarget) return;
    
    try {
        const response = await fetch('/api/opus/delete', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: deleteTarget.filename
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        showSuccess('文件已删除');
        closeDeleteModal();
        loadFileList(); // 重新加载列表
    } catch (error) {
        showError('删除失败: ' + error.message);
    }
}

// 播放音频
function playAudio(filename) {
    const audioUrl = `/api/opus/file/${encodeURIComponent(filename)}`;
    const audio = new Audio(audioUrl);
    
    // 添加错误处理
    audio.addEventListener('error', function(e) {
        console.error('Audio playback error:', e);
        showError('播放失败: 浏览器可能不支持Opus格式，或文件已损坏');
    });
    
    audio.addEventListener('loadstart', function() {
        console.log('Audio loading started');
    });
    
    audio.addEventListener('canplay', function() {
        console.log('Audio can play');
    });
    
    audio.play().catch(err => {
        console.error('Play error:', err);
        showError('播放失败: ' + (err.message || '未知错误'));
    });
}

// 切换输入方式
function switchInputMode(mode) {
    const fileMode = document.getElementById('fileInputMode');
    const textMode = document.getElementById('textInputMode');
    
    if (mode === 'file') {
        fileMode.style.display = 'block';
        textMode.style.display = 'none';
    } else {
        fileMode.style.display = 'none';
        textMode.style.display = 'block';
    }
}

// 编辑文本
function editText(filename, currentText) {
    const text = prompt('请输入文本内容：', currentText || '');
    if (text === null) {
        return; // 用户取消
    }
    
    updateText(filename, text.trim());
}

// 更新文本内容
async function updateText(filename, text) {
    try {
        const response = await fetch('/api/opus/update-text', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: filename,
                text: text
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        showSuccess('文本内容已更新');
        loadFileList(); // 重新加载列表
    } catch (error) {
        showError('更新失败: ' + error.message);
    }
}

// 上传文件
async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    
    if (!fileInput.files || fileInput.files.length === 0) {
        showError('请选择文件');
        return;
    }
    
    const file = fileInput.files[0];
    if (!file.name.endsWith('.txt')) {
        showError('只支持.txt文件');
        return;
    }
    
    // 显示进度
    const progressDiv = document.getElementById('uploadProgress');
    const statusSpan = document.getElementById('uploadStatus');
    const percentSpan = document.getElementById('uploadPercent');
    const progressBar = document.getElementById('uploadProgressBar');
    const btnUpload = document.getElementById('btnUpload');
    
    progressDiv.style.display = 'block';
    statusSpan.textContent = '正在上传并生成...';
    percentSpan.textContent = '0%';
    progressBar.style.width = '0%';
    btnUpload.disabled = true;
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch('/api/opus/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            progressDiv.style.display = 'none';
            btnUpload.disabled = false;
            return;
        }
        
        // 更新进度
        statusSpan.textContent = data.message;
        percentSpan.textContent = '100%';
        progressBar.style.width = '100%';
        
        showSuccess(data.message);
        
        // 清空文件输入
        fileInput.value = '';
        
        // 延迟后隐藏进度条并重新加载列表
        setTimeout(() => {
            progressDiv.style.display = 'none';
            btnUpload.disabled = false;
            loadFileList();
        }, 2000);
        
    } catch (error) {
        showError('上传失败: ' + error.message);
        progressDiv.style.display = 'none';
        btnUpload.disabled = false;
    }
}

// 从文本输入生成
async function generateFromText() {
    const textInput = document.getElementById('textInput');
    const text = textInput.value.trim();
    
    if (!text) {
        showError('请输入文本内容');
        return;
    }
    
    // 显示进度
    const progressDiv = document.getElementById('uploadProgress');
    const statusSpan = document.getElementById('uploadStatus');
    const percentSpan = document.getElementById('uploadPercent');
    const progressBar = document.getElementById('uploadProgressBar');
    const btnGenerate = document.getElementById('btnGenerate');
    
    progressDiv.style.display = 'block';
    statusSpan.textContent = '正在生成...';
    percentSpan.textContent = '0%';
    progressBar.style.width = '0%';
    btnGenerate.disabled = true;
    
    try {
        const response = await fetch('/api/opus/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                texts: text.split('\n').filter(line => line.trim())
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            progressDiv.style.display = 'none';
            btnGenerate.disabled = false;
            return;
        }
        
        // 更新进度
        statusSpan.textContent = data.message;
        percentSpan.textContent = '100%';
        progressBar.style.width = '100%';
        
        showSuccess(data.message);
        
        // 清空文本输入
        textInput.value = '';
        
        // 延迟后隐藏进度条并重新加载列表
        setTimeout(() => {
            progressDiv.style.display = 'none';
            btnGenerate.disabled = false;
            loadFileList();
        }, 2000);
        
    } catch (error) {
        showError('生成失败: ' + error.message);
        progressDiv.style.display = 'none';
        btnGenerate.disabled = false;
    }
}

// 显示错误消息
function showError(message) {
    alert('错误: ' + message);
}

// 显示成功消息
function showSuccess(message) {
    // 可以替换为更好的通知组件
    alert('成功: ' + message);
}

// ==================== Opus测试功能 ====================

// 初始化Socket.IO连接
let socket = null;
try {
    socket = io();
} catch (e) {
    console.error('Socket.IO初始化失败:', e);
}

// 当前测试的文件信息
let currentTestFile = null;

// 打开Opus测试模态框
function testOpusFile(filename, text) {
    currentTestFile = { filename, text };
    
    // 设置模态框内容
    document.getElementById('opusTestFilename').value = filename;
    document.getElementById('opusTestText').value = text || '';
    
    // 重置状态
    document.getElementById('opusTestStatus').style.display = 'none';
    document.getElementById('opusTestMetrics').style.display = 'none';
    document.getElementById('opusTestStatusText').textContent = '准备中...';
    document.getElementById('opusTestRequestText').textContent = text || '-';
    document.getElementById('opusTestSTTText').textContent = '-';
    document.getElementById('opusTestLLMText').textContent = '-';
    document.getElementById('btnStartOpusTest').disabled = false;
    document.getElementById('btnStartOpusTest').innerHTML = '<span class="icon">▶</span> 开始测试';
    
    // 显示模态框
    document.getElementById('opusTestModal').classList.add('active');
}

// 关闭Opus测试模态框
function closeOpusTest() {
    document.getElementById('opusTestModal').classList.remove('active');
    currentTestFile = null;
}

// 开始Opus测试
async function startOpusTest() {
    if (!currentTestFile) {
        alert('请选择要测试的文件');
        return;
    }
    
    const deviceSN = document.getElementById('opusTestDeviceSN').value.trim();
    const testMode = document.getElementById('opusTestMode').value;
    
    // 禁用按钮
    const btn = document.getElementById('btnStartOpusTest');
    btn.disabled = true;
    btn.innerHTML = '<span class="icon">⏳</span> 测试中...';
    
    // 显示状态
    document.getElementById('opusTestStatus').style.display = 'block';
    document.getElementById('opusTestStatusText').textContent = '正在连接服务器...';
    document.getElementById('opusTestRequestText').textContent = currentTestFile.text || '-';
    document.getElementById('opusTestSTTText').textContent = '-';
    document.getElementById('opusTestLLMText').textContent = '-';
    
    try {
        // 获取设置中的WebSocket URL（需要从主页面获取，这里先尝试从localStorage获取）
        let wsUrl = '';
        try {
            const settings = localStorage.getItem('testSettings');
            if (settings) {
                const parsed = JSON.parse(settings);
                wsUrl = parsed.wsUrl || '';
            }
        } catch (e) {
            console.warn('无法读取设置:', e);
        }
        
        // 发送测试请求
        const response = await fetch('/api/single-test-from-file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: currentTestFile.filename,
                text: currentTestFile.text || '',
                device_sns: deviceSN ? [deviceSN] : [],
                test_mode: testMode,
                ws_url: wsUrl
            })
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || '测试启动失败');
        }
        
        // 更新状态
        document.getElementById('opusTestStatusText').textContent = '测试进行中...';
        
    } catch (error) {
        console.error('Opus test error:', error);
        alert('测试启动失败: ' + error.message);
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">▶</span> 开始测试';
        document.getElementById('opusTestStatusText').textContent = '测试失败: ' + error.message;
    }
}

// 监听Socket.IO事件（如果Socket.IO可用）
if (socket) {
    // 单语音测试开始事件
    socket.on('single_test_start', (data) => {
        if (data.status) {
            document.getElementById('opusTestStatusText').textContent = data.status;
        } else {
            document.getElementById('opusTestStatusText').textContent = '测试进行中...';
        }
    });
    
    // 单语音测试实时更新
    socket.on('single_test_update', (data) => {
        // 实时更新STT识别结果
        if (data.stt_text) {
            document.getElementById('opusTestSTTText').textContent = data.stt_text;
        }
        
        // 实时更新LLM回复（流式显示）
        if (data.llm_text) {
            const llmTextElement = document.getElementById('opusTestLLMText');
            if (llmTextElement) {
                llmTextElement.textContent = data.llm_text;
            }
        }
    });
    
    // 单语音测试完成事件
    socket.on('single_test_complete', (data) => {
        const result = data.result;
        const btn = document.getElementById('btnStartOpusTest');
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">▶</span> 开始测试';
        
        // 更新状态
        document.getElementById('opusTestStatusText').textContent = result.success ? '测试成功' : '测试失败';
        document.getElementById('opusTestSTTText').textContent = result.stt_text || '-';
        document.getElementById('opusTestLLMText').textContent = result.llm_text || '-';
        
        // 显示性能指标
        document.getElementById('opusTestMetrics').style.display = 'block';
        document.getElementById('opusMetricSTT').textContent = result.stt_latency ? `${result.stt_latency.toFixed(2)} ms` : '-';
        document.getElementById('opusMetricLLM').textContent = result.llm_latency ? `${result.llm_latency.toFixed(2)} ms` : '-';
        document.getElementById('opusMetricTTS').textContent = result.tts_latency ? `${result.tts_latency.toFixed(2)} ms` : '-';
        document.getElementById('opusMetricE2E').textContent = result.e2e_response_time ? `${result.e2e_response_time.toFixed(2)} ms` : '-';
    });
    
    // 单语音测试错误事件
    socket.on('single_test_error', (data) => {
        const btn = document.getElementById('btnStartOpusTest');
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">▶</span> 开始测试';
        document.getElementById('opusTestStatusText').textContent = '错误: ' + (data.error || '未知错误');
        alert('测试失败: ' + (data.error || '未知错误'));
    });
}

