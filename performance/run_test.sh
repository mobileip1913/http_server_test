#!/bin/bash
# WebSocket 性能测试快速启动脚本

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}WebSocket Performance Test Runner${NC}"
echo "=========================================="

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# 检查是否安装了依赖
echo "Checking dependencies..."
if ! python3 -c "import websockets" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip3 install -r requirements.txt
fi

# Token 验证已完全移除，不再需要检查

# 显示配置信息
echo ""
echo "Configuration:"
echo "  Server: ${WS_SERVER_HOST:-ws://toyaiws.spacechaintech.com:8081}"
if [ "${DEBUG_MODE}" = "true" ]; then
    echo -e "  ${YELLOW}DEBUG MODE: 1 connection${NC}"
    echo "  Set DEBUG_MODE=false for full test with ${CONCURRENT_CONNECTIONS:-100} connections"
else
    echo "  Concurrent Connections: ${CONCURRENT_CONNECTIONS:-100}"
fi
echo "  Test Message: ${TEST_MESSAGE:-你好啊，我今天想去故宫玩}"
echo "  Send Audio Data: ${SEND_AUDIO_DATA:-true}"
echo ""

# 运行测试
echo -e "${GREEN}Starting test...${NC}"
python3 test_runner.py

