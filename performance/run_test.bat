@echo off
REM WebSocket 性能测试快速启动脚本 (Windows)

echo WebSocket Performance Test Runner
echo ==========================================

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM 检查依赖
echo Checking dependencies...
python -c "import websockets" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

REM Token 验证已完全移除，不再需要检查

REM 显示配置信息
echo.
echo Configuration:
echo   Server: %WS_SERVER_HOST%
if "%WS_SERVER_HOST%"=="" echo   Server: ws://toyaiws.spacechaintech.com:8081
if "%DEBUG_MODE%"=="true" (
    echo   DEBUG MODE: 1 connection
    echo   Set DEBUG_MODE=false for full test with %CONCURRENT_CONNECTIONS% connections
) else (
    echo   Concurrent Connections: %CONCURRENT_CONNECTIONS%
    if "%CONCURRENT_CONNECTIONS%"=="" echo   Concurrent Connections: 100
)
echo   Test Message: %TEST_MESSAGE%
if "%TEST_MESSAGE%"=="" echo   Test Message: 你好啊，我今天想去故宫玩
echo   Send Audio Data: %SEND_AUDIO_DATA%
if "%SEND_AUDIO_DATA%"=="" echo   Send Audio Data: true
echo.

REM 运行测试
echo Starting test...
python test_runner.py

