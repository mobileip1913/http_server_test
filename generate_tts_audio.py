"""
讯飞在线语音合成 - 生成测试音频文件

使用讯飞TTS API将文本转换为语音，并保存为本地Opus文件供测试使用。
参考文档：https://www.xfyun.cn/doc/tts/online_tts/API.html
"""
import os
import sys
import json
import base64
import hmac
import hashlib
import asyncio
import websockets
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
from urllib.parse import urlencode, quote
from typing import Optional
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 讯飞API配置
XFYUN_APPID = "c7f30371"
XFYUN_API_KEY = "50e273869438ea2fc41e44a32167ef6d"
XFYUN_API_SECRET = "OGIxYmY1OGM2OWZkNTcyMGE4YzM2NTM0"
XFYUN_HOST = "tts-api.xfyun.cn"
XFYUN_PATH = "/v2/tts"

# 音频保存路径
AUDIO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "audio")
AUDIO_OUTPUT_FILE = os.path.join(AUDIO_OUTPUT_DIR, "test_audio.opus")
AUDIO_OUTPUT_FILE_MP3 = os.path.join(AUDIO_OUTPUT_DIR, "test_audio.mp3")  # MP3版本用于播放测试


def generate_authorization() -> tuple:
    """
    生成讯飞API鉴权参数（按照官方demo）
    
    Returns:
        (authorization, date) 元组
    """
    # 按照官方demo，签名中的host是 "ws-api.xfyun.cn"，不是 "tts-api.xfyun.cn"
    SIGN_HOST = "ws-api.xfyun.cn"
    
    # 生成RFC 1123格式的日期（按照官方demo使用本地时间）
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    
    # 生成签名原始字符串（按照官方demo格式）
    signature_origin = f"host: {SIGN_HOST}\ndate: {date}\nGET {XFYUN_PATH} HTTP/1.1"
    
    # 使用HMAC-SHA256生成签名
    signature_sha = hmac.new(
        XFYUN_API_SECRET.encode('utf-8'),
        signature_origin.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    
    signature_enc = base64.b64encode(signature_sha).decode(encoding='utf-8')
    
    # 生成authorization字符串
    authorization_origin = f'api_key="{XFYUN_API_KEY}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_enc}"'
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
    
    return authorization, date, SIGN_HOST


def build_websocket_url() -> str:
    """
    构建WebSocket连接URL（带鉴权参数，按照官方demo）
    
    Returns:
        WebSocket URL字符串
    """
    authorization, date, sign_host = generate_authorization()
    
    # 构建查询参数（按照官方demo）
    params = {
        "authorization": authorization,
        "date": date,
        "host": sign_host  # 注意：这里使用 sign_host，不是 XFYUN_HOST
    }
    
    query_string = urlencode(params)
    url = f"wss://{XFYUN_HOST}{XFYUN_PATH}?{query_string}"
    
    return url


async def synthesize_speech(text: str, output_file: str, audio_format: str = "opus") -> bool:
    """
    调用讯飞TTS API合成语音并保存
    
    Args:
        text: 要合成的文本
        output_file: 输出文件路径
    
    Returns:
        True if success, False otherwise
    """
    try:
        # 构建WebSocket URL
        url = build_websocket_url()
        logger.info(f"Connecting to Xunfei TTS API: {XFYUN_HOST}")
        
        # 建立WebSocket连接
        async with websockets.connect(url) as websocket:
            logger.info("WebSocket connection established")
            
            # 构建请求数据（按照官方demo，一次性发送，status=2）
            # 官方demo只使用最基本的参数：aue, auf, vcn, tte
            business_params = {
                "aue": "raw",  # 固定使用 raw（PCM格式），然后用 ffmpeg 转换为 Opus
                "auf": "audio/L16;rate=16000",  # PCM 采样率参数（按照官方demo）
                "vcn": "xiaoyan",  # 发音人：小燕（中文女声）
                "tte": "utf8"  # 文本编码：utf8（小写，按照官方demo）
            }
            
            # 按照官方demo，直接发送 status=2，一次性发送完整文本
            business_data = {
                "common": {
                    "app_id": XFYUN_APPID
                },
                "business": business_params,
                "data": {
                    "status": 2,  # 按照官方demo，直接使用 status=2
                    "text": base64.b64encode(text.encode('utf-8')).decode('utf-8')  # Base64编码的文本
                }
            }
            
            # 发送请求（按照官方demo，只发送一次）
            logger.info(f"Sending TTS request for text: {text}")
            await websocket.send(json.dumps(business_data))
            
            # 接收音频数据
            audio_data = []
            received_size = 0
            
            async for message in websocket:
                try:
                    response = json.loads(message)
                    
                    # 检查响应状态
                    code = response.get("code", -1)
                    if code != 0:
                        error_msg = response.get("message", "Unknown error")
                        logger.error(f"TTS API error: code={code}, message={error_msg}")
                        return False
                    
                    # 获取音频数据
                    data_obj = response.get("data", {})
                    audio_base64 = data_obj.get("audio", "")
                    
                    if audio_base64:
                        # 解码Base64音频数据
                        audio_chunk = base64.b64decode(audio_base64)
                        audio_data.append(audio_chunk)
                        received_size += len(audio_chunk)
                        logger.debug(f"Received audio chunk: {len(audio_chunk)} bytes (total: {received_size} bytes)")
                    
                    # 检查是否完成
                    status = data_obj.get("status", 0)
                    if status == 2:
                        logger.info(f"Audio synthesis completed, total size: {received_size} bytes")
                        break
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON response: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing response: {e}")
                    continue
            
            # 保存音频文件
            if audio_data:
                # 确保输出目录存在
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # 合并所有音频数据块并保存
                with open(output_file, 'wb') as f:
                    for chunk in audio_data:
                        f.write(chunk)
                
                total_size = sum(len(chunk) for chunk in audio_data)
                logger.info(f"Audio saved to: {output_file} ({total_size} bytes)")
                return True
            else:
                logger.error("No audio data received")
                return False
                
    except Exception as e:
        logger.error(f"Failed to synthesize speech: {e}", exc_info=True)
        return False


async def main():
    """主函数"""
    # 默认文本：与测试脚本的TEST_MESSAGE保持一致
    # 这样生成的音频文件可以直接用于测试脚本
    DEFAULT_TEXT = "你好啊，我想去故宫"
    
    # 测试文本（默认）
    test_text = DEFAULT_TEXT
    # 根据服务器代码分析：讯飞 TTS API 只支持 raw (PCM) 和 lame (MP3)
    # 所以先生成 PCM，然后用 ffmpeg 转换为 Opus（更可靠）
    output_format = "pcm_to_opus"
    
    # 解析命令行参数
    args = sys.argv[1:]
    if args:
        # 检查最后一个参数是否是格式参数
        if args[-1].lower() in ["--mp3", "mp3"]:
            output_format = "mp3"
            # 文本是除了最后一个参数之外的所有参数
            if len(args) > 1:
                test_text = " ".join(args[:-1])
            else:
                # 如果没有提供文本，MP3使用简短文本（用于播放测试）
                test_text = "你好啊"
        else:
            # 所有参数都是文本
            test_text = " ".join(args)
    
    logger.info("=" * 60)
    logger.info("Xunfei TTS Audio Generator")
    logger.info("=" * 60)
    logger.info(f"Text to synthesize: {test_text}")
    logger.info(f"Output format: {output_format.upper()}")
    logger.info("=" * 60)
    
    if output_format == "mp3":
        # 生成MP3格式（用于播放测试）
        logger.info("Generating MP3 format for playback testing...")
        success = await synthesize_speech(test_text, AUDIO_OUTPUT_FILE_MP3, audio_format="mp3")
        output_file = AUDIO_OUTPUT_FILE_MP3
    elif output_format == "pcm" or output_format == "pcm_to_opus":
        # 生成PCM格式（使用 raw），然后转换为Opus（更可靠）
        # 根据服务器代码，aue 应该使用 "raw" 而不是 "pcm"
        pcm_file = os.path.join(AUDIO_OUTPUT_DIR, "test_audio.pcm")
        logger.info("Generating PCM format (raw)...")
        success = await synthesize_speech(test_text, pcm_file, audio_format="raw")  # 使用 raw 格式（固定）
        if success:
            # 使用 ffmpeg 将 PCM 转换为 Opus 和 WAV（用于验证）
            import subprocess
            wav_file = os.path.join(AUDIO_OUTPUT_DIR, "test_audio_verify.wav")
            logger.info("Converting PCM to Opus and WAV...")
            try:
                # PCM -> WAV (用于验证)
                subprocess.run([
                    "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                    "-i", pcm_file, wav_file
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.info(f"WAV file created: {wav_file} (for verification)")
                
                # PCM -> Opus (用于测试，使用与设备相同的参数)
                subprocess.run([
                    "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                    "-i", pcm_file, "-c:a", "libopus", "-b:a", "32k", "-frame_duration", "60",
                    AUDIO_OUTPUT_FILE
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.info(f"Opus file created: {AUDIO_OUTPUT_FILE}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to convert PCM: {e}")
                success = False
        output_file = AUDIO_OUTPUT_FILE
    else:
        # 生成Opus格式（用于测试）
        logger.info("Generating Opus format for testing...")
        success = await synthesize_speech(test_text, AUDIO_OUTPUT_FILE, audio_format="opus")
        output_file = AUDIO_OUTPUT_FILE
    
    if success:
        logger.info("=" * 60)
        logger.info("SUCCESS: Audio file generated successfully!")
        logger.info(f"File location: {output_file}")
        logger.info("=" * 60)
        if output_format == "opus":
            logger.info("You can now use this file for testing by setting:")
            logger.info(f"  export AUDIO_FILE_PATH={AUDIO_OUTPUT_FILE}")
        else:
            logger.info("You can play this MP3 file to listen to the audio.")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("=" * 60)
        logger.error("FAILED: Failed to generate audio file")
        logger.error("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

