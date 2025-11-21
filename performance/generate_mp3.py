"""
快速生成MP3格式的TTS音频文件（用于播放测试）
使用opuslib解码Opus数据，然后用ffmpeg编码为MP3
"""
import asyncio
import sys
import subprocess
import os
try:
    import opuslib
    OPUSLIB_AVAILABLE = True
except ImportError:
    OPUSLIB_AVAILABLE = False
    print("Warning: opuslib not available, will try alternative methods")

from generate_tts_audio import synthesize_speech, AUDIO_OUTPUT_FILE, AUDIO_OUTPUT_FILE_MP3

async def main():
    text = "你好啊，我想去故宫"
    if len(sys.argv) > 1:
        text = sys.argv[1]
    
    print(f"Generating audio for: {text}")
    print("Step 1: Generating Opus format...")
    
    # 先生成Opus格式
    success = await synthesize_speech(text, AUDIO_OUTPUT_FILE, audio_format="opus")
    
    if not success:
        print("\nFAILED to generate Opus file")
        sys.exit(1)
    
    print("Step 2: Requesting MP3 format directly from API...")
    
    # 直接请求MP3格式（根据文档，mp3格式应该使用 aue=lame）
    success_mp3 = await synthesize_speech(text, AUDIO_OUTPUT_FILE_MP3, audio_format="lame")
    
    if success_mp3:
        file_size = os.path.getsize(AUDIO_OUTPUT_FILE_MP3)
        print(f"\nSUCCESS! MP3 file saved to: {AUDIO_OUTPUT_FILE_MP3}")
        print(f"File size: {file_size} bytes")
        print("You can now play this file to listen.")
    else:
        print("\nAPI returned MP3 format failed, trying alternative method...")
        
        # 备用方案：使用ffmpeg转换（需要先解码Opus）
        # 由于讯飞返回的是裸Opus数据包，ffmpeg可能无法直接读取
        # 这里我们尝试使用管道方式
        temp_pcm = os.path.join(os.path.dirname(AUDIO_OUTPUT_FILE), "temp.pcm")
        
        # 尝试使用opusdec工具解码（如果系统有的话）
        # 或者直接读取Opus数据并通过管道传递给ffmpeg
        with open(AUDIO_OUTPUT_FILE, 'rb') as f:
            opus_data = f.read()
        
        # 使用ffmpeg从stdin读取Opus数据
        cmd = [
            'ffmpeg',
            '-f', 'opus',  # 输入格式
            '-ar', '16000',
            '-ac', '1',
            '-i', 'pipe:0',  # 从stdin读取
            '-acodec', 'libmp3lame',
            '-ab', '128k',
            AUDIO_OUTPUT_FILE_MP3,
            '-y'
        ]
        
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = process.communicate(input=opus_data)
        
        if process.returncode == 0:
            file_size = os.path.getsize(AUDIO_OUTPUT_FILE_MP3)
            print(f"\nSUCCESS! MP3 file saved to: {AUDIO_OUTPUT_FILE_MP3}")
            print(f"File size: {file_size} bytes")
            print("You can now play this file to listen.")
        else:
            print(f"\nFAILED to convert to MP3 via pipe: {stderr.decode()}")
            print("\nTrying with opuslib to decode Opus...")
            
            # 使用opuslib解码Opus数据包
            if OPUSLIB_AVAILABLE:
                try:
                    # 创建Opus解码器
                    sample_rate = 16000
                    channels = 1
                    decoder = opuslib.Decoder(sample_rate, channels)
                    frame_size = int(sample_rate * 60 / 1000)  # 60ms帧
                    
                    # 读取Opus数据
                    with open(AUDIO_OUTPUT_FILE, 'rb') as f:
                        opus_data = f.read()
                    
                    # 讯飞返回的是连续的Opus数据包，需要正确分割
                    # Opus数据包的TOC（Table of Contents）字节可以帮助判断包类型和大小
                    # 但更简单的方法是：尝试将数据按固定大小或使用Opus包的解析
                    pcm_frames = []
                    offset = 0
                    
                    # 方法：尝试按Opus包的特征分割
                    # Opus包的第一个字节（TOC）包含配置信息
                    # 对于简单的流式Opus，我们可以尝试逐个字节查找有效的包边界
                    
                    print(f"Decoding Opus data: {len(opus_data)} bytes")
                    
                    # 尝试不同的解码策略
                    # 策略1：尝试将整个数据作为单个Opus包（可能需要更大的frame_size）
                    # 估算音频时长：1408字节，32kbps ≈ 352ms
                    estimated_duration_ms = (len(opus_data) * 8) / 32  # 32kbps
                    estimated_frame_size = int(sample_rate * estimated_duration_ms / 1000)
                    
                    if estimated_frame_size < frame_size:
                        estimated_frame_size = frame_size
                    
                    print(f"Estimated duration: {estimated_duration_ms:.1f}ms, frame_size: {estimated_frame_size}")
                    
                    try:
                        # 尝试将整个数据作为单个包解码
                        pcm_data = decoder.decode(opus_data, estimated_frame_size)
                        pcm_frames = [pcm_data]
                        print(f"Successfully decoded as single packet: {len(pcm_data)} bytes PCM")
                    except Exception as e1:
                        print(f"Failed to decode as single packet: {e1}")
                        
                        # 策略2：尝试按固定大小分割（每60ms一帧）
                        # 对于16kHz，60ms = 960 samples = 1920 bytes PCM
                        # Opus包大小通常在20-200字节之间
                        print("Trying to split into multiple packets...")
                        
                        # 尝试常见的大小：从20字节开始，逐步增加
                        packet_sizes = []
                        test_offset = 0
                        
                        while test_offset < len(opus_data):
                            # 尝试从最小到最大可能的包大小
                            found = False
                            for try_size in range(20, min(300, len(opus_data) - test_offset + 1)):
                                try:
                                    packet = opus_data[test_offset:test_offset + try_size]
                                    pcm = decoder.decode(packet, frame_size)
                                    
                                    # 验证解码结果：对于60ms帧，应该得到约1920字节（960 samples * 2 bytes）
                                    # 但允许一些误差，因为Opus可能返回不同大小的帧
                                    if len(pcm) > 0 and len(pcm) <= frame_size * 2 * 2:  # 最多不超过预期2倍
                                        pcm_frames.append(pcm)
                                        packet_sizes.append(try_size)
                                        test_offset += try_size
                                        found = True
                                        break
                                except Exception as decode_err:
                                    # 解码失败，尝试下一个大小
                                    continue
                            
                            if not found:
                                # 如果找不到，尝试跳过1字节
                                test_offset += 1
                                if test_offset >= len(opus_data):
                                    break
                        
                        if not pcm_frames:
                            raise Exception("Failed to decode Opus data with any method")
                        
                        print(f"Decoded {len(pcm_frames)} packets: {packet_sizes}")
                    
                    # 合并所有PCM帧
                    pcm_data = b''.join(pcm_frames)
                    print(f"Total PCM data: {len(pcm_data)} bytes ({len(pcm_data)/2/16000:.2f} seconds)")
                    
                    # 保存PCM数据到临时文件
                    temp_pcm = os.path.join(os.path.dirname(AUDIO_OUTPUT_FILE), "temp.pcm")
                    with open(temp_pcm, 'wb') as f:
                        f.write(pcm_data)
                    
                    # 使用ffmpeg将PCM编码为MP3
                    cmd_mp3 = [
                        'ffmpeg',
                        '-f', 's16le',
                        '-ar', str(sample_rate),
                        '-ac', str(channels),
                        '-i', temp_pcm,
                        '-acodec', 'libmp3lame',
                        '-ab', '128k',
                        AUDIO_OUTPUT_FILE_MP3,
                        '-y'
                    ]
                    
                    result_mp3 = subprocess.run(cmd_mp3, capture_output=True, text=True)
                    
                    # 清理临时文件
                    if os.path.exists(temp_pcm):
                        os.unlink(temp_pcm)
                    
                    if result_mp3.returncode == 0:
                        file_size = os.path.getsize(AUDIO_OUTPUT_FILE_MP3)
                        print(f"\nSUCCESS! MP3 file saved to: {AUDIO_OUTPUT_FILE_MP3}")
                        print(f"File size: {file_size} bytes")
                        print("You can now play this file to listen.")
                    else:
                        print(f"\nFAILED to encode MP3: {result_mp3.stderr}")
                        sys.exit(1)
                        
                except Exception as e:
                    print(f"\nFailed to decode with opuslib: {e}")
                    print("\nPlease install opuslib: pip install opuslib")
                    sys.exit(1)
            else:
                print("\nopuslib not available. Please install: pip install opuslib")
                sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

