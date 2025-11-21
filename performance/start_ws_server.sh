#!/bin/bash
# 启动本地 ws_server 服务（Linux/Mac）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_SERVER_DIR="$SCRIPT_DIR/../ws_server"

cd "$WS_SERVER_DIR" || exit 1

echo "========================================"
echo "启动本地 ws_server 服务"
echo "========================================"
echo ""

# 检查 Node.js 是否安装
if ! command -v node &> /dev/null; then
    echo "[错误] 未找到 Node.js，请先安装 Node.js >= 18"
    exit 1
fi

# 检查依赖是否安装
if [ ! -d "node_modules" ]; then
    echo "[警告] node_modules 不存在，正在安装依赖..."
    npm install
    if [ $? -ne 0 ]; then
        echo "[错误] 依赖安装失败"
        exit 1
    fi
fi

# 启动服务器（开发模式）
# 注意：NODE_ENV 已在 start.js 中硬编码为 dev，无需设置环境变量
echo "[信息] 启动服务器（开发模式）..."
echo "[信息] 端口: 8081"
echo "[信息] WebSocket 地址: ws://localhost:8081"
echo ""

node start.js

