"""
启动Web测试服务的便捷脚本
"""
import sys
import os

# 确保在正确的目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 导入并启动Web服务
from web_server import app, socketio

if __name__ == '__main__':
    print("=" * 60)
    print("语音对话测试平台 - Web服务")
    print("=" * 60)
    print(f"访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n服务已停止")

