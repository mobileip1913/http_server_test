// WebSocket连接
const socket = io();

// 状态管理
let testState = {
    isRunning: false,
    progress: 0,
    total: 0,
    results: [],
    summary: {
        total: 0,
        successful: 0,
        failed: 0,
        success_rate: 0.0
    }
};

// 并发状态管理
let concurrencyState = {
    requestCount: 0,  // 实际请求数量
    blocks: [],  // 每个方块的状态: waiting, responding, success, failed
    blockMap: {},  // 映射: "index-type" -> block元素，用于快速查找
    pendingStatusUpdates: {}  // 待处理的状态更新: "index-type" -> status，用于处理事件乱序
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    setupSocketListeners();
    loadStatus();
    loadSettings();
    
    // 点击模态框外部关闭
    const settingsModal = document.getElementById('settingsModal');
    if (settingsModal) {
        settingsModal.addEventListener('click', function(e) {
            if (e.target === this || e.target.classList.contains('settings-modal-overlay')) {
                closeSettings();
            }
        });
    }
    
    // ESC键关闭设置或报告
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeSettings();
            closeReport();
        }
    });
    
    // 点击报告模态框外部关闭
    const reportModal = document.getElementById('reportModal');
    if (reportModal) {
        reportModal.addEventListener('click', function(e) {
            if (e.target === this || e.target.classList.contains('settings-modal-overlay')) {
                closeReport();
            }
        });
    }
});

// 设置WebSocket监听
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('test_started', (data) => {
        console.log('Test started', data);
        updateUIForTestStart();
        // 清空并发状态指示器，准备接收新的请求
        clearConcurrencyIndicator();
    });

    socket.on('test_start', (data) => {
        console.log('Test start', data);
        addConversationItem(data, 'running');
        // 添加新的请求方块（等待响应状态），并绑定到测试的index和type
        addConcurrencyBlock('waiting', data.index, data.type);
        
        // 检查是否有待处理的状态更新
        const testKey = getTestKey(data.index, data.type);
        if (concurrencyState.pendingStatusUpdates[testKey]) {
            const pendingStatus = concurrencyState.pendingStatusUpdates[testKey];
            updateConcurrencyBlockByTest(data.index, data.type, pendingStatus);
            delete concurrencyState.pendingStatusUpdates[testKey];
        }
    });

    socket.on('test_result', (data) => {
        console.log('Test result', data);
        // 确保result对象存在且包含必要字段
        if (data && data.result) {
            updateConversationItem(data.result, data.current_test);
            // 根据测试的index和type更新对应的方块状态
            const status = data.result.success ? 'success' : 'failed';
            updateConcurrencyBlockByTest(data.result.index, data.result.type, status);
        }
    });

    socket.on('progress_update', (data) => {
        console.log('Progress update', data);
        updateProgress(data.progress, data.total);
        updateSummary(data.summary);
    });

    socket.on('test_completed', (data) => {
        console.log('Test completed', data);
        updateUIForTestComplete();
        // 更新统计信息（如果后端发送了summary）
        if (data.summary) {
            updateSummary(data.summary);
        }
        // 显示报告按钮（只要有测试结果，即使为0也显示，因为报告可能包含测试信息）
        const btnReport = document.getElementById('btnReport');
        if (btnReport) {
            btnReport.style.display = 'inline-flex';
        }
    });

    socket.on('test_error', (data) => {
        console.error('Test error', data);
        showError(data.error);
        updateUIForTestComplete();
        // 即使出错也显示报告按钮（可能有一些结果）
        const btnReport = document.getElementById('btnReport');
        if (btnReport && testState.summary.total > 0) {
            btnReport.style.display = 'inline-flex';
        }
    });

    socket.on('status_update', (data) => {
        console.log('Status update', data);
        addStatusMessage(data.message);
    });

    socket.on('test_detail_update', (data) => {
        console.log('Test detail update', data);
        // 实时更新对话流中的LLM回答
        updateConversationItemLLM(data);
        // 如果开始收到LLM响应（有新句子或累积文本），根据测试的index和type更新对应的方块为响应中状态（黄色）
        if (data.index && data.type && (data.llm_sentence || (data.llm_text && data.llm_text.trim()))) {
            updateConcurrencyBlockByTest(data.index, data.type, 'responding');
        }
    });
}

// 加载状态
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        testState = status;
        updateUI();
    } catch (error) {
        console.error('Failed to load status', error);
    }
}

// 开始测试
async function startTest() {
    try {
        // 重置所有页面状态
        resetTestState();
        
        // 获取当前设置
        const settings = {
            concurrency: testSettings.concurrency || 10,
            device_sns: testSettings.deviceSns || [],
            test_mode: testSettings.testMode || 'normal',
            ws_url: testSettings.wsUrl || '',  // 如果为空，后端使用默认值
            test_count: testSettings.testCount || null  // 测试数量，null表示测试所有文件
        };
        
        // 验证设置
        if (!settings.device_sns || settings.device_sns.length === 0) {
            alert('请先在设置中配置至少一个设备SN');
            openSettings();
            return;
        }
        
        // 调试：打印发送的设置
        console.log('发送测试设置:', settings);
        console.log('并发数:', settings.concurrency);
        console.log('SN列表:', settings.device_sns);
        console.log('测试模式:', settings.test_mode);
        
        const response = await fetch('/api/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        if (response.ok) {
            document.getElementById('btnStart').disabled = true;
            document.getElementById('btnStop').disabled = false;
            // resetTestState() 已经清空了对话，这里不需要再次调用
        } else {
            const data = await response.json();
            alert('启动测试失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        console.error('Failed to start test', error);
        alert('启动测试失败: ' + error.message);
    }
}

// 停止测试
async function stopTest() {
    try {
        const response = await fetch('/api/stop', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            document.getElementById('btnStart').disabled = false;
            document.getElementById('btnStop').disabled = true;
        }
    } catch (error) {
        console.error('Failed to stop test', error);
    }
}

// 更新UI
function updateUI() {
    updateProgress(testState.progress, testState.total);
    updateSummary(testState.summary);
    
    if (testState.is_running) {
        document.getElementById('btnStart').disabled = true;
        document.getElementById('btnStop').disabled = false;
    } else {
        document.getElementById('btnStart').disabled = false;
        document.getElementById('btnStop').disabled = true;
    }
}

// 更新进度
function updateProgress(progress, total) {
    const percentage = total > 0 ? (progress / total * 100) : 0;
    document.getElementById('progressFill').style.width = percentage + '%';
    document.getElementById('progressText').textContent = `${progress} / ${total}`;
}

// 更新统计
function updateSummary(summary) {
    document.getElementById('statTotal').textContent = summary.total || 0;
    document.getElementById('statSuccess').textContent = summary.successful || 0;
    document.getElementById('statFailed').textContent = summary.failed || 0;
    document.getElementById('statRate').textContent = (summary.success_rate || 0).toFixed(1) + '%';
}

// 存储每个测试的LLM文本，用于流式显示
let testLlmTexts = {};

// 生成测试的唯一键（避免代码重复）
function getTestKey(index, type) {
    return `${index}-${type}`;
}

// 实时更新对话流中的LLM回答（流式显示）
function updateConversationItemLLM(data) {
    if (!data || !data.index || !data.type) return;
    
    let item = document.getElementById(`conversation-${data.index}-${data.type}`);
    // 如果对话项不存在，可能是test_start事件还没到达，先创建它
    if (!item) {
        addConversationItem({
            index: data.index,
            type: data.type,
            text: data.text || '',
            timestamp: new Date().toISOString()
        }, 'running');
        item = document.getElementById(`conversation-${data.index}-${data.type}`);
        if (!item) return;  // 如果还是创建失败，直接返回
    }
    
    // 获取LLM文本和STT文本
    const llmText = data.llm_text && data.llm_text.trim() ? data.llm_text : '';
    const llmSentence = data.llm_sentence && data.llm_sentence.trim() ? data.llm_sentence : '';
    const sttText = data.stt_text && data.stt_text.trim() ? data.stt_text : '';
    const testKey = getTestKey(data.index, data.type);
    
    // 更新提问部分（如果有STT识别结果）
    if (sttText) {
        const inputSection = item.querySelector('.input-section .section-content.input-text');
        if (inputSection) {
            // 更新提问内容为STT识别结果
            inputSection.textContent = sttText;
        }
    }
    
    // 更新LLM部分（流式显示）- 使用已存在的LLM部分，不重复创建
    const llmSection = item.querySelector('.llm-section');
    if (llmSection) {
        // 获取内容容器（应该已经存在，因为addConversationItem中已创建）
        let contentDiv = llmSection.querySelector('.section-content');
        if (!contentDiv) {
            // 如果不存在，创建它
            contentDiv = document.createElement('div');
            contentDiv.className = 'section-content';
            llmSection.appendChild(contentDiv);
        }
        
        if (contentDiv) {
            // 流式显示：如果有新句子，追加显示
            if (llmSentence) {
                const currentText = contentDiv.textContent || '';
                // 如果当前文本为空或者是"等待响应中..."，直接显示新句子
                if (!currentText || currentText.trim() === '等待响应中...') {
                    contentDiv.textContent = llmSentence;
                } else {
                    // 检查新句子是否已存在，避免重复追加
                    const sentences = currentText.split(/\s+/);
                    const newSentenceWords = llmSentence.trim().split(/\s+/);
                    const lastSentenceWords = sentences.slice(-newSentenceWords.length);
                    const isDuplicate = lastSentenceWords.length === newSentenceWords.length &&
                        lastSentenceWords.every((word, i) => word === newSentenceWords[i]);
                    
                    if (!isDuplicate) {
                        // 追加新句子（用空格分隔）
                        contentDiv.textContent = currentText + ' ' + llmSentence;
                    }
                }
            } else if (llmText) {
                // 如果没有新句子但有累积文本，且当前没有流式内容，显示累积文本（用于最终完整显示）
                const currentText = contentDiv.textContent || '';
                if (!currentText || currentText.trim() === '等待响应中...') {
                    contentDiv.textContent = llmText;
                }
                // 如果已有流式内容，不覆盖，保持流式显示效果
            }
        }
        
        // 更新缓存的文本
        if (llmText) {
            testLlmTexts[testKey] = llmText;
        }
    }
    
    // STT识别结果已经更新到"提问"部分，不需要单独的STT部分
}

// 添加对话项
function addConversationItem(test, status) {
    const list = document.getElementById('conversationList');
    
    // 移除空状态
    const emptyState = list.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    // 检查是否已存在
    const existingItem = document.getElementById(`conversation-${test.index}-${test.type}`);
    if (existingItem) {
        // 如果已存在，只更新状态
        return;
    }

    const item = document.createElement('div');
    item.className = `conversation-item ${test.type} ${status}`;
    item.id = `conversation-${test.index}-${test.type}`;
    
    // 支持三种类型：inquiry（询问）、compare（对比）、order/purchase（购买/下单）
    let badgeClass, badgeText;
    if (test.type === 'inquiry') {
        badgeClass = 'badge-inquiry';
        badgeText = '询问';
    } else if (test.type === 'compare') {
        badgeClass = 'badge-compare';
        badgeText = '对比';
    } else if (test.type === 'order' || test.type === 'purchase') {
        badgeClass = 'badge-purchase';
        badgeText = '购买';
    } else {
        badgeClass = 'badge-purchase';
        badgeText = '购买';
    }
    const statusBadge = status === 'running' ? '<span class="conversation-badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;">⏳ 测试中</span>' : '';
    
    // 获取用户输入（优先使用STT识别结果）
    const questionText = (test.stt_text && test.stt_text.trim()) 
        ? test.stt_text 
        : (test.text || '');
    
    item.innerHTML = `
        <div class="conversation-header">
            <div class="conversation-title">
                <span class="conversation-badge ${badgeClass}">${badgeText}</span>
                <span>#${test.index.toString().padStart(3, '0')}</span>
                ${statusBadge}
            </div>
            <div class="conversation-time">${new Date(test.timestamp || new Date()).toLocaleTimeString()}</div>
        </div>
        <div class="conversation-content">
            <div class="conversation-section input-section">
                <div class="section-label">📝 提问</div>
                <div class="section-content input-text">${escapeHtml(questionText)}</div>
            </div>
            <div class="conversation-section llm-section">
                <div class="section-label">🤖 LLM返回</div>
                <div class="section-content">等待响应中...</div>
            </div>
        </div>
    `;

    list.insertBefore(item, list.firstChild);
    
    // 限制显示数量
    const items = list.querySelectorAll('.conversation-item');
    if (items.length > 50) {
        items[items.length - 1].remove();
    }
}

// 更新对话项
function updateConversationItem(result, currentTest) {
    const item = document.getElementById(`conversation-${result.index}-${result.type}`);
    if (!item) {
        // 如果项目不存在，创建一个新的
        addConversationItem({
            index: result.index,
            type: result.type,
            text: result.text || '',
            timestamp: result.timestamp || new Date().toISOString()
        }, result.success ? 'completed' : 'failed');
        // 重新获取项目
        const newItem = document.getElementById(`conversation-${result.index}-${result.type}`);
        if (newItem) {
            updateConversationItemContent(newItem, result);
        }
        return;
    }

    updateConversationItemContent(item, result);
}

// 更新对话项内容（分离出来以便复用）
function updateConversationItemContent(item, result) {
    // 确保result.success是布尔值
    const isSuccess = result.success === true || result.success === 'true' || result.success === 1;
    const statusClass = isSuccess ? 'success' : 'failed';
    item.className = `conversation-item ${result.type} ${statusClass}`;

    // 支持三种类型：inquiry（询问）、compare（对比）、order/purchase（购买/下单）
    let badgeClass, badgeText;
    if (result.type === 'inquiry') {
        badgeClass = 'badge-inquiry';
        badgeText = '询问';
    } else if (result.type === 'compare') {
        badgeClass = 'badge-compare';
        badgeText = '对比';
    } else if (result.type === 'order' || result.type === 'purchase') {
        badgeClass = 'badge-purchase';
        badgeText = '购买';
    } else {
        badgeClass = 'badge-purchase';
        badgeText = '购买';
    }
    const statusBadge = isSuccess ? '<span class="conversation-badge badge-success">✓ 成功</span>' : 
                        '<span class="conversation-badge badge-failed">✗ 失败</span>';

    // 获取用户输入（优先使用STT识别结果）
    const questionText = (result.stt_text && result.stt_text.trim()) 
        ? result.stt_text 
        : (result.text || '');
    
    // 获取LLM返回内容
    const llmText = result.llm_text && result.llm_text.trim() ? result.llm_text : '';

    // 构建内容HTML
    let contentHtml = `
        <div class="conversation-section input-section">
            <div class="section-label">📝 提问</div>
            <div class="section-content input-text">${escapeHtml(questionText)}</div>
        </div>`;

    // LLM返回结果 - 确保始终显示，即使测试已完成
    // 先尝试从已存在的LLM部分获取内容（保留流式显示的内容）
    let existingLlmText = '';
    const existingLlmSection = item.querySelector('.llm-section');
    if (existingLlmSection) {
        const llmContentDiv = existingLlmSection.querySelector('.section-content');
        if (llmContentDiv && llmContentDiv.textContent && llmContentDiv.textContent.trim() !== '等待响应中...') {
            existingLlmText = llmContentDiv.textContent.trim();
        }
    }
    
    // 也尝试从缓存中获取（如果之前通过test_detail_update更新过）
    const testKey = getTestKey(result.index, result.type);
    const cachedLlmText = testLlmTexts[testKey] || '';
    
    // 优先使用result中的llm_text，其次使用已存在的文本，最后使用缓存的文本
    const finalLlmText = llmText || existingLlmText || cachedLlmText;
    
    // 始终在contentHtml中包含LLM部分
    contentHtml += `
        <div class="conversation-section llm-section">
            <div class="section-label">🤖 LLM返回</div>
            <div class="section-content">${finalLlmText ? escapeHtml(finalLlmText) : '等待响应中...'}</div>
        </div>`;

    // 错误信息
    if (result.error) {
        contentHtml += `
        <div class="conversation-section">
            <div class="section-label">❌ 错误信息</div>
            <div class="section-content error">${escapeHtml(result.error)}</div>
        </div>`;
    }

    item.innerHTML = `
        <div class="conversation-header">
            <div class="conversation-title">
                <span class="conversation-badge ${badgeClass}">${badgeText}</span>
                <span>#${result.index.toString().padStart(3, '0')}</span>
                ${statusBadge}
            </div>
            <div class="conversation-time">${new Date(result.timestamp || new Date()).toLocaleTimeString()}</div>
        </div>
        <div class="conversation-content">
            ${contentHtml}
        </div>
    `;
}

// 清空对话
function clearConversation() {
    const list = document.getElementById('conversationList');
    list.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">💭</div>
            <div class="empty-text">等待测试开始...</div>
        </div>
    `;
    // 清空并发状态指示器
    clearConcurrencyIndicator();
    // 清空STT文本缓存
    testSttTexts = {};
    // 清空LLM文本缓存
    testLlmTexts = {};
}

// 添加状态消息
function addStatusMessage(message) {
    const list = document.getElementById('conversationList');
    const emptyState = list.querySelector('.empty-state');
    if (emptyState) {
        emptyState.querySelector('.empty-text').textContent = message;
    }
}

// 显示错误
function showError(error) {
    alert('测试错误: ' + error);
}

// 重置测试状态（包括统计信息）
function resetTestState() {
    // 重置统计信息
    updateSummary({
        total: 0,
        successful: 0,
        failed: 0,
        success_rate: 0.0
    });
    
    // 重置进度条
    updateProgress(0, 0);
    
    // 清空对话
    clearConversation();
    
    // 清空并发状态指示器
    clearConcurrencyIndicator();
    
    // 隐藏报告按钮（测试开始时）
    const btnReport = document.getElementById('btnReport');
    if (btnReport) {
        btnReport.style.display = 'none';
    }
}

// 更新UI为测试开始
function updateUIForTestStart() {
    document.getElementById('btnStart').disabled = true;
    document.getElementById('btnStop').disabled = false;
    // 重置测试状态（包括统计信息）
    resetTestState();
}

// 更新UI为测试完成
function updateUIForTestComplete() {
    document.getElementById('btnStart').disabled = false;
    document.getElementById('btnStop').disabled = true;
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 添加新的并发方块（当有新请求时）
function addConcurrencyBlock(status = 'waiting', testIndex = null, testType = null) {
    const blocksContainer = document.getElementById('concurrencyBlocks');
    const countElement = document.getElementById('concurrencyCount');
    
    if (!blocksContainer || !countElement) return;
    
    // 创建新方块
    const block = document.createElement('div');
    block.className = `concurrency-block status-${status}`;
    const index = concurrencyState.requestCount;
    block.setAttribute('data-index', index);
    
    // 如果提供了testIndex和testType，创建唯一标识符并存储映射
    if (testIndex !== null && testType !== null) {
        const testKey = `${testIndex}-${testType}`;
        block.setAttribute('data-test-key', testKey);
        concurrencyState.blockMap[testKey] = block;
    }
    
    const statusText = {
        'waiting': '等待响应',
        'responding': '响应中',
        'success': '成功',
        'failed': '失败'
    };
    const displayIndex = testIndex !== null ? testIndex : (index + 1);
    block.setAttribute('title', `测试 #${displayIndex} (${testType || '未知'}): ${statusText[status] || status}`);
    
    // 根据类型设置data-type属性（支持三种类型）
    if (testType === 'inquiry' || testType === 'compare' || testType === 'order' || testType === 'purchase') {
        block.setAttribute('data-type', testType);
    }
    
    // 添加点击事件，定位到对应的对话项
    if (testIndex !== null && testType !== null) {
        block.style.cursor = 'pointer';
        block.addEventListener('click', function() {
            scrollToConversationItem(testIndex, testType);
        });
    }
    
    blocksContainer.appendChild(block);
    
    // 更新状态
    concurrencyState.requestCount++;
    concurrencyState.blocks.push(status);
    
    // 更新计数
    countElement.textContent = concurrencyState.requestCount;
    
    // 更新自适应大小
    updateConcurrencyBlockSize(concurrencyState.requestCount);
}

// 更新方块大小（自适应）
function updateConcurrencyBlockSize(count) {
    const blocksContainer = document.getElementById('concurrencyBlocks');
    if (!blocksContainer) return;
    
    blocksContainer.setAttribute('data-count', count);
    
    // 根据数量设置大小类别
    let size = 'small';
    if (count <= 10) {
        size = 'large';
    } else if (count <= 30) {
        size = 'medium';
    } else if (count <= 50) {
        size = 'small';
    } else {
        size = 'tiny';
    }
    
    blocksContainer.setAttribute('data-size', size);
}

// 滚动到对应的对话项
function scrollToConversationItem(testIndex, testType) {
    const itemId = `conversation-${testIndex}-${testType}`;
    const item = document.getElementById(itemId);
    if (item) {
        // 滚动到该元素
        item.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // 添加高亮效果（可选）
        item.style.transition = 'background-color 0.3s';
        item.style.backgroundColor = 'rgba(59, 130, 246, 0.2)';
        setTimeout(() => {
            item.style.backgroundColor = '';
        }, 2000);
    } else {
        // 如果对话项还不存在，尝试查找最近的
        const list = document.getElementById('conversationList');
        if (list && list.firstChild) {
            list.firstChild.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

// 根据测试的index和type更新对应的方块状态
function updateConcurrencyBlockByTest(testIndex, testType, status) {
    if (testIndex === null || testIndex === undefined || testType === null || testType === undefined) {
        // 如果没有提供testIndex和testType，回退到更新最后一个方块
        updateLastConcurrencyBlock(status);
        return;
    }
    
    const testKey = `${testIndex}-${testType}`;
    const block = concurrencyState.blockMap[testKey];
    
    if (!block) {
        // 如果找不到对应的方块，可能是测试开始事件还没到达，先缓存状态更新
        console.warn(`Block not found for test ${testKey}, status: ${status}, caching update`);
        concurrencyState.pendingStatusUpdates[testKey] = status;
        return;
    }
    
    // 获取方块的索引
    const blocksContainer = document.getElementById('concurrencyBlocks');
    if (!blocksContainer) return;
    
    const index = Array.from(blocksContainer.children).indexOf(block);
    if (index === -1) return;
    
    // 更新状态
    if (index < concurrencyState.blocks.length) {
        concurrencyState.blocks[index] = status;
    }
    
    // 移除所有状态类
    block.classList.remove('status-waiting', 'status-responding', 'status-success', 'status-failed');
    
    // 添加新状态类
    block.classList.add(`status-${status}`);
    
    // 更新提示文本
    const statusText = {
        'waiting': '等待响应',
        'responding': '响应中',
        'success': '成功',
        'failed': '失败'
    };
    block.setAttribute('title', `测试 #${testIndex} (${testType}): ${statusText[status] || status}`);
}

// 更新最后一个方块的状态（保留作为备用方法）
function updateLastConcurrencyBlock(status) {
    const blocksContainer = document.getElementById('concurrencyBlocks');
    if (!blocksContainer || blocksContainer.children.length === 0) return;
    
    const lastBlock = blocksContainer.children[blocksContainer.children.length - 1];
    if (!lastBlock) return;
    
    const index = blocksContainer.children.length - 1;
    
    // 更新状态
    if (index < concurrencyState.blocks.length) {
        concurrencyState.blocks[index] = status;
    }
    
    // 移除所有状态类
    lastBlock.classList.remove('status-waiting', 'status-responding', 'status-success', 'status-failed');
    
    // 添加新状态类
    lastBlock.classList.add(`status-${status}`);
    
    // 更新提示文本
    const statusText = {
        'waiting': '等待响应',
        'responding': '响应中',
        'success': '成功',
        'failed': '失败'
    };
    const testKey = lastBlock.getAttribute('data-test-key');
    if (testKey) {
        const [testIndex, testType] = testKey.split('-');
        lastBlock.setAttribute('title', `测试 #${testIndex} (${testType}): ${statusText[status] || status}`);
    } else {
        lastBlock.setAttribute('title', `请求 #${index + 1}: ${statusText[status] || status}`);
    }
}

// 清空并发状态指示器
function clearConcurrencyIndicator() {
    const blocksContainer = document.getElementById('concurrencyBlocks');
    const countElement = document.getElementById('concurrencyCount');
    
    if (blocksContainer) {
        blocksContainer.innerHTML = '';
    }
    if (countElement) {
        countElement.textContent = '0';
    }
    
    concurrencyState.requestCount = 0;
    concurrencyState.blocks = [];
    concurrencyState.blockMap = {};
    concurrencyState.pendingStatusUpdates = {};
}

// 设置相关功能
let testSettings = {
    concurrency: 10,
    deviceSns: [
        "FC012C2EA0D4",
        "FC012C2EA174",
        "FC012C2EA0E8",
        "FC012C2EA134",
        "FC012C2EA114",
        "FC012C2EA0A0",
        "FC012C2EA108",
        "FC012C2E9E18",
        "FC012C2E9E34",
        "FC012C2E9E2C"
    ],
    testMode: "normal",  // 默认正常模式
    wsUrl: "",  // WebSocket服务器地址，为空则使用默认值
    testCount: null  // 测试数量，null表示测试所有文件
};

// 从localStorage加载设置
function loadSettings() {
    const saved = localStorage.getItem('testSettings');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            testSettings = { ...testSettings, ...parsed };
            // 更新UI
            if (document.getElementById('concurrencyInput')) {
                document.getElementById('concurrencyInput').value = testSettings.concurrency || 10;
            }
            if (document.getElementById('deviceSnsInput')) {
                document.getElementById('deviceSnsInput').value = (testSettings.deviceSns || []).join('\n');
            }
            if (document.getElementById('testModeSelect')) {
                document.getElementById('testModeSelect').value = testSettings.testMode || 'normal';
            }
            if (document.getElementById('wsUrlInput')) {
                document.getElementById('wsUrlInput').value = testSettings.wsUrl || '';
            }
            if (document.getElementById('testCountInput')) {
                document.getElementById('testCountInput').value = testSettings.testCount || '';
            }
        } catch (e) {
            console.error('Failed to load settings:', e);
        }
    }
}

// 保存设置到localStorage
function saveSettingsToStorage() {
    localStorage.setItem('testSettings', JSON.stringify(testSettings));
}

// 打开设置页面
function openSettings() {
    const modal = document.getElementById('settingsModal');
    if (modal) {
        modal.classList.add('active');
        // 加载当前设置到表单
        document.getElementById('concurrencyInput').value = testSettings.concurrency || 10;
        document.getElementById('deviceSnsInput').value = (testSettings.deviceSns || []).join('\n');
        document.getElementById('testModeSelect').value = testSettings.testMode || 'normal';
        document.getElementById('wsUrlInput').value = testSettings.wsUrl || '';
        document.getElementById('testCountInput').value = testSettings.testCount || '';
    }
}

// 关闭设置页面
function closeSettings() {
    const modal = document.getElementById('settingsModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// 保存设置
function saveSettings() {
    const concurrency = parseInt(document.getElementById('concurrencyInput').value);
    const deviceSnsText = document.getElementById('deviceSnsInput').value.trim();
    const testMode = document.getElementById('testModeSelect').value;
    const wsUrl = document.getElementById('wsUrlInput').value.trim();
    const testCountText = document.getElementById('testCountInput').value.trim();
    const testCount = testCountText ? parseInt(testCountText) : null;
    
    // 验证并发数
    if (isNaN(concurrency) || concurrency < 1 || concurrency > 100) {
        alert('并发数必须在1-100之间');
        return;
    }
    
    // 解析SN列表（去除空格，转换为大写）
    const deviceSns = deviceSnsText
        .split('\n')
        .map(sn => sn.trim().toUpperCase())
        .filter(sn => sn.length > 0);
    
    if (deviceSns.length === 0) {
        alert('请至少输入一个设备SN');
        return;
    }
    
    if (deviceSns.length > concurrency) {
        alert(`设备SN数量(${deviceSns.length})不能超过并发数(${concurrency})`);
        return;
    }
    
    // 验证测试模式
    if (testMode !== 'normal' && testMode !== 'fast') {
        alert('测试模式无效');
        return;
    }
    
    // 验证WebSocket URL（如果填写了）
    if (wsUrl && !wsUrl.match(/^(ws|wss):\/\/.+/)) {
        alert('WebSocket地址格式不正确，应以 ws:// 或 wss:// 开头');
        return;
    }
    
    // 验证测试数量（如果填写了）
    if (testCount !== null) {
        if (isNaN(testCount) || testCount < 1) {
            alert('测试数量必须是大于0的整数');
            return;
        }
    }
    
    // 保存设置
    testSettings.concurrency = concurrency;
    testSettings.deviceSns = deviceSns;
    testSettings.testMode = testMode;
    testSettings.wsUrl = wsUrl;
    testSettings.testCount = testCount;
    saveSettingsToStorage();
    
    // 调试：打印保存的设置
    console.log('保存的设置:', testSettings);
    console.log('并发数:', testSettings.concurrency);
    console.log('SN列表:', testSettings.deviceSns);
    console.log('测试模式:', testSettings.testMode);
    console.log('WebSocket URL:', testSettings.wsUrl || '使用默认值');
    
    // 关闭设置页面
    closeSettings();
    
    // 显示成功提示
    showNotification('设置已保存', 'success');
}

// 显示通知
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    const bgColor = type === 'success' ? 'var(--success-color)' : 
                   type === 'error' ? 'var(--danger-color)' : 'var(--info-color)';
    
    notification.style.cssText = `
        position: fixed;
        top: 30%;
        left: 50%;
        transform: translate(-50%, -50%);
        padding: 16px 24px;
        background: ${bgColor};
        color: white;
        border-radius: 10px;
        box-shadow: var(--shadow-lg);
        z-index: 2000;
        font-weight: 600;
        min-width: 200px;
        text-align: center;
        opacity: 0;
        transition: opacity 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    // 淡入动画
    setTimeout(() => {
        notification.style.opacity = '1';
    }, 10);
    
    // 1秒后快速淡化消失
    setTimeout(() => {
        notification.style.transition = 'opacity 0.5s ease';
        notification.style.opacity = '0';
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 500);
    }, 1000);
}

// 报告相关功能
let reportCharts = {};  // 存储图表实例

// 显示报告
async function showReport() {
    const modal = document.getElementById('reportModal');
    if (modal) {
        modal.classList.add('active');
        
        // 显示加载状态
        const reportContent = document.getElementById('reportContent');
        reportContent.innerHTML = '<div class="loading-state">正在生成报告...</div>';
        
        try {
            // 获取报告数据
            const response = await fetch('/api/report');
            if (!response.ok) {
                throw new Error('获取报告失败');
            }
            
            const report = await response.json();
            
            // 渲染报告
            renderReport(report);
        } catch (error) {
            console.error('Failed to load report:', error);
            reportContent.innerHTML = `<div class="error-state">加载报告失败: ${error.message}</div>`;
        }
    }
}

// 关闭报告
function closeReport() {
    const modal = document.getElementById('reportModal');
    if (modal) {
        modal.classList.remove('active');
        // 销毁所有图表
        Object.values(reportCharts).forEach(chart => {
            if (chart) chart.destroy();
        });
        reportCharts = {};
    }
}

// 导出PDF报告
function exportReportPDF() {
    // 创建下载链接
    const link = document.createElement('a');
    link.href = '/api/report/pdf';
    link.download = `测试报告_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // 显示提示
    showNotification('PDF报告正在下载...', 'success');
}

// 渲染报告
function renderReport(report) {
    const reportContent = document.getElementById('reportContent');
    
    if (!report || !report.summary) {
        reportContent.innerHTML = '<div class="error-state">报告数据为空</div>';
        return;
    }
    
    let html = `
        <div class="report-container">
            <!-- 测试信息 -->
            <div class="report-section">
                <h3 class="report-section-title">📋 测试信息</h3>
                <div class="report-info-grid">
                    <div class="report-info-item">
                        <span class="info-label">开始时间:</span>
                        <span class="info-value">${formatDateTime(report.test_info.start_time)}</span>
                    </div>
                    <div class="report-info-item">
                        <span class="info-label">结束时间:</span>
                        <span class="info-value">${formatDateTime(report.test_info.end_time)}</span>
                    </div>
                    <div class="report-info-item">
                        <span class="info-label">持续时间:</span>
                        <span class="info-value">${formatDuration(report.test_info.duration_seconds)}</span>
                    </div>
                    <div class="report-info-item">
                        <span class="info-label">并发数:</span>
                        <span class="info-value">${report.test_info.concurrency}</span>
                    </div>
                    <div class="report-info-item">
                        <span class="info-label">设备数量:</span>
                        <span class="info-value">${report.test_info.device_count}</span>
                    </div>
                    <div class="report-info-item">
                        <span class="info-label">测试模式:</span>
                        <span class="info-value">${report.test_info.test_mode === 'fast' ? '急速模式' : '正常模式'}</span>
                    </div>
                </div>
            </div>
            
            <!-- 总体统计 -->
            <div class="report-section">
                <h3 class="report-section-title">📊 总体统计</h3>
                <div class="report-stats-grid">
                    <div class="report-stat-card">
                        <div class="stat-card-icon">📈</div>
                        <div class="stat-card-content">
                            <div class="stat-card-label">总测试数</div>
                            <div class="stat-card-value">${report.summary.total_tests}</div>
                        </div>
                    </div>
                    <div class="report-stat-card success">
                        <div class="stat-card-icon">✅</div>
                        <div class="stat-card-content">
                            <div class="stat-card-label">成功</div>
                            <div class="stat-card-value">${report.summary.successful_tests}</div>
                            <div class="stat-card-rate">${report.summary.success_rate}%</div>
                        </div>
                    </div>
                    <div class="report-stat-card failed">
                        <div class="stat-card-icon">❌</div>
                        <div class="stat-card-content">
                            <div class="stat-card-label">失败</div>
                            <div class="stat-card-value">${report.summary.failed_tests}</div>
                            <div class="stat-card-rate">${(100 - report.summary.success_rate).toFixed(2)}%</div>
                        </div>
                    </div>
                    <div class="report-stat-card">
                        <div class="stat-card-icon">⚡</div>
                        <div class="stat-card-content">
                            <div class="stat-card-label">吞吐量 (QPS)</div>
                            <div class="stat-card-value">${report.summary.qps}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 性能指标 -->
            <div class="report-section">
                <h3 class="report-section-title">⚡ 性能指标</h3>
                <div class="performance-metrics">
                    ${renderPerformanceMetrics(report.performance_metrics)}
                </div>
            </div>
            
            <!-- 失败分析 -->
            <div class="report-section">
                <h3 class="report-section-title">🔍 失败分析</h3>
                <div class="failure-analysis">
                    ${renderFailureAnalysis(report.failure_analysis)}
                </div>
            </div>
            
            <!-- 图表 -->
            <div class="report-section">
                <h3 class="report-section-title">📈 可视化图表</h3>
                <div class="charts-container">
                    <div class="chart-wrapper">
                        <canvas id="responseTimeChart"></canvas>
                    </div>
                    <div class="chart-wrapper">
                        <canvas id="successRateChart"></canvas>
                    </div>
                    <div class="chart-wrapper">
                        <canvas id="failureReasonChart"></canvas>
                    </div>
                    <div class="chart-wrapper">
                        <canvas id="timelineChart"></canvas>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    reportContent.innerHTML = html;
    
    // 渲染图表
    renderCharts(report);
}

// 格式化时间（毫秒转换为易读格式）
function formatTime(ms) {
    if (ms === null || ms === undefined || isNaN(ms) || ms < 0) {
        return 'N/A';
    }
    
    if (ms < 1000) {
        return `${ms.toFixed(0)} ms`;
    } else if (ms < 60000) {
        return `${(ms / 1000).toFixed(2)} s`;
    } else if (ms < 3600000) {
        const minutes = Math.floor(ms / 60000);
        const seconds = ((ms % 60000) / 1000).toFixed(1);
        return `${minutes}分 ${seconds}秒`;
    } else {
        const hours = Math.floor(ms / 3600000);
        const minutes = Math.floor((ms % 3600000) / 60000);
        return `${hours}小时 ${minutes}分钟`;
    }
}

// 渲染性能指标
function renderPerformanceMetrics(metrics) {
    const metricNames = {
        'stt_time': 'STT识别时间',
        'llm_time': 'LLM响应时间',
        'tts_start_time': 'TTS启动时间',
        'tts_duration': 'TTS持续时间',
        'total_response_time': '总响应时间'
    };
    
    let html = '<div class="metrics-grid">';
    
    for (const [key, name] of Object.entries(metricNames)) {
        const metric = metrics[key];
        if (metric && metric.count > 0) {
            html += `
                <div class="metric-card">
                    <div class="metric-header">${name}</div>
                    <div class="metric-values">
                        <div class="metric-row">
                            <span class="metric-label">平均值:</span>
                            <span class="metric-value">${formatTime(metric.avg)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">中位数:</span>
                            <span class="metric-value">${formatTime(metric.median)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">P95:</span>
                            <span class="metric-value">${formatTime(metric.p95)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">P99:</span>
                            <span class="metric-value">${formatTime(metric.p99)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">最小值:</span>
                            <span class="metric-value">${formatTime(metric.min)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">最大值:</span>
                            <span class="metric-value">${formatTime(metric.max)}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">样本数:</span>
                            <span class="metric-value">${metric.count}</span>
                        </div>
                    </div>
                </div>
            `;
        }
    }
    
    html += '</div>';
    return html;
}

// 渲染失败分析
function renderFailureAnalysis(analysis) {
    if (!analysis.failure_reasons || Object.keys(analysis.failure_reasons).length === 0) {
        return '<div class="no-failures">🎉 没有失败记录！</div>';
    }
    
    let html = '<div class="failure-reasons">';
    const totalFailures = Object.values(analysis.failure_reasons).reduce((a, b) => a + b, 0);
    
    for (const [reason, count] of Object.entries(analysis.failure_reasons)) {
        const percentage = ((count / totalFailures) * 100).toFixed(2);
        html += `
            <div class="failure-reason-item">
                <div class="failure-reason-header">
                    <span class="failure-reason-text">${reason}</span>
                    <span class="failure-reason-count">${count} (${percentage}%)</span>
                </div>
                <div class="failure-reason-bar">
                    <div class="failure-reason-bar-fill" style="width: ${percentage}%"></div>
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    return html;
}

// 渲染图表
function renderCharts(report) {
    // 响应时间分布图
    if (report.performance_metrics.total_response_time) {
        const metric = report.performance_metrics.total_response_time;
        const ctx1 = document.getElementById('responseTimeChart');
        if (ctx1) {
            // 将毫秒转换为秒
            const dataInSeconds = [
                metric.min / 1000,
                metric.avg / 1000,
                metric.median / 1000,
                metric.p95 / 1000,
                metric.p99 / 1000,
                metric.max / 1000
            ];
            
            reportCharts.responseTime = new Chart(ctx1, {
                type: 'bar',
                data: {
                    labels: ['最小值', '平均值', '中位数', 'P95', 'P99', '最大值'],
                    datasets: [{
                        label: '响应时间 (s)',
                        data: dataInSeconds,
                        backgroundColor: 'rgba(102, 126, 234, 0.6)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: '响应时间分布',
                            color: '#f1f5f9'
                        },
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} s`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: '#cbd5e1',
                                callback: function(value) {
                                    return value.toFixed(2) + ' s';
                                }
                            },
                            grid: { color: 'rgba(203, 213, 225, 0.1)' }
                        },
                        x: {
                            ticks: { color: '#cbd5e1' },
                            grid: { color: 'rgba(203, 213, 225, 0.1)' }
                        }
                    }
                }
            });
        }
    }
    
    // 成功率饼图
    const ctx2 = document.getElementById('successRateChart');
    if (ctx2) {
        reportCharts.successRate = new Chart(ctx2, {
            type: 'doughnut',
            data: {
                labels: ['成功', '失败'],
                datasets: [{
                    data: [report.summary.successful_tests, report.summary.failed_tests],
                    backgroundColor: ['#10b981', '#ef4444'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: '成功率分布',
                        color: '#f1f5f9'
                    },
                    legend: {
                        position: 'bottom',
                        labels: { color: '#cbd5e1' }
                    }
                }
            }
        });
    }
    
    // 失败原因饼图
    if (report.failure_analysis.failure_reasons && Object.keys(report.failure_analysis.failure_reasons).length > 0) {
        const ctx3 = document.getElementById('failureReasonChart');
        if (ctx3) {
            const reasons = Object.keys(report.failure_analysis.failure_reasons);
            const counts = Object.values(report.failure_analysis.failure_reasons);
            reportCharts.failureReason = new Chart(ctx3, {
                type: 'pie',
                data: {
                    labels: reasons,
                    datasets: [{
                        data: counts,
                        backgroundColor: [
                            '#ef4444', '#f59e0b', '#f97316', '#eab308', '#84cc16',
                            '#22c55e', '#10b981', '#14b8a6', '#06b6d4', '#3b82f6'
                        ],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: '失败原因分布',
                            color: '#f1f5f9'
                        },
                        legend: {
                            position: 'bottom',
                            labels: { color: '#cbd5e1' }
                        }
                    }
                }
            });
        }
    }
    
    // 时间线图
    if (report.timeline && report.timeline.length > 0) {
        const ctx4 = document.getElementById('timelineChart');
        if (ctx4) {
            const timeline = report.timeline;
            const labels = timeline.map((_, i) => `测试 #${i + 1}`);
            // 将毫秒转换为秒
            const responseTimes = timeline.map(t => (t.total_response_time || 0) / 1000);
            const successData = timeline.map(t => t.success ? 1 : 0);
            
            reportCharts.timeline = new Chart(ctx4, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: '响应时间 (s)',
                            data: responseTimes,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            yAxisID: 'y',
                            tension: 0.4
                        },
                        {
                            label: '成功 (1=成功, 0=失败)',
                            data: successData,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            yAxisID: 'y1',
                            tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        title: {
                            display: true,
                            text: '测试时间线',
                            color: '#f1f5f9'
                        },
                        legend: {
                            labels: { color: '#cbd5e1' }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    if (context.dataset.yAxisID === 'y') {
                                        return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} s`;
                                    }
                                    return context.dataset.label + ': ' + context.parsed.y;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            ticks: {
                                color: '#cbd5e1',
                                callback: function(value) {
                                    return value.toFixed(2) + ' s';
                                }
                            },
                            grid: { color: 'rgba(203, 213, 225, 0.1)' }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            ticks: { color: '#cbd5e1' },
                            grid: { drawOnChartArea: false }
                        },
                        x: {
                            ticks: { color: '#cbd5e1', maxRotation: 45, minRotation: 45 },
                            grid: { color: 'rgba(203, 213, 225, 0.1)' }
                        }
                    }
                }
            });
        }
    }
}

// 格式化日期时间
function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('zh-CN');
    } catch {
        return isoString;
    }
}

// 格式化持续时间
function formatDuration(seconds) {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}小时 ${minutes}分钟 ${secs}秒`;
    } else if (minutes > 0) {
        return `${minutes}分钟 ${secs}秒`;
    } else {
        return `${secs}秒`;
    }
}

