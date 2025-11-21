@echo off
REM 启动本地 ws_server 服务（Windows）

cd /d "%~dp0\..\ws_server"

echo ========================================
echo 启动本地 ws_server 服务
echo ========================================
echo.

REM 检查 Node.js 是否安装
where node >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js >= 18
    pause
    exit /b 1
)

REM 检查依赖是否安装
if not exist "node_modules" (
    echo [警告] node_modules 不存在，正在安装依赖...
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)

REM 启动服务器（开发模式）
REM 注意：NODE_ENV 已在 start.js 中硬编码为 dev，无需设置环境变量
echo [信息] 启动服务器（开发模式）...
echo [信息] 端口: 8081
echo [信息] WebSocket 地址: ws://localhost:8081
echo.

node start.js

pause

