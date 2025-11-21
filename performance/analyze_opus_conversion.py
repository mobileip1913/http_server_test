"""
分析Opus文件转换过程，找出问题所在
"""
import os
import subprocess
import tempfile
import opuslib

def analyze_opus_file(file_path):
    """分析Opus文件转换过程"""
    print("=" * 60)
    print("分析Opus文件转换过程")
    print("=" * 60)
    
    # 1. 检查原始文件
    print(f"\n1. 原始文件分析：{file_path}")
    with open(file_path, 'rb') as f:
        opus_data = f.read()
    
    print(f"   文件大小: {len(opus_data)} 字节")
    print(f"   前4字节: {opus_data[:4]}")
    print(f"   是否为Ogg容器: {opus_data[:4] == b'OggS'}")
    
    if opus_data[:4] != b'OggS':
        print("   ⚠️  这不是Ogg容器格式，可能是裸Opus包")
        return
    
    # 2. 转换为PCM
    print(f"\n2. 转换为PCM（16kHz, 单声道, 16-bit）")
    temp_pcm = tempfile.NamedTemporaryFile(suffix='.raw', delete=False)
    temp_pcm.close()
    
    cmd_pcm = [
        'ffmpeg', '-i', file_path,
        '-ar', '16000',
        '-ac', '1',
        '-f', 's16le',
        temp_pcm.name,
        '-y'
    ]
    
    result = subprocess.run(cmd_pcm, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ❌ ffmpeg转换失败: {result.stderr[:200]}")
        return
    
    with open(temp_pcm.name, 'rb') as f:
        pcm_data = f.read()
    
    print(f"   PCM大小: {len(pcm_data)} 字节")
    print(f"   预期帧数（60ms）: {len(pcm_data) // (960 * 2)}")
    print(f"   预期时长: {len(pcm_data) / (16000 * 2):.2f} 秒")
    
    # 3. 从PCM生成Opus包
    print(f"\n3. 从PCM生成Opus包（使用opuslib）")
    encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)
    frame_size = 960  # 60ms @ 16kHz
    frame_bytes = frame_size * 2  # 16-bit = 2 bytes per sample
    
    frames = []
    offset = 0
    processed_pcm = 0
    
    while offset + frame_bytes <= len(pcm_data):
        pcm_frame = pcm_data[offset:offset + frame_bytes]
        opus_frame = encoder.encode(pcm_frame, frame_size)
        frames.append(opus_frame)
        processed_pcm += frame_bytes
        offset += frame_bytes
    
    # 检查是否有剩余的PCM数据
    remaining_pcm = len(pcm_data) - processed_pcm
    if remaining_pcm > 0:
        print(f"   [WARNING] 有 {remaining_pcm} 字节PCM数据未处理 ({remaining_pcm / (16000 * 2) * 1000:.1f}ms)")
    
    print(f"   生成Opus包数量: {len(frames)}")
    print(f"   总字节数: {sum(len(f) for f in frames)} 字节")
    print(f"   平均包大小: {sum(len(f) for f in frames) / len(frames):.1f} 字节")
    print(f"   包大小范围: {min(len(f) for f in frames)} - {max(len(f) for f in frames)} 字节")
    
    # 4. 验证生成的Opus包
    print(f"\n4. 验证生成的Opus包（使用opuslib解码器）")
    decoder = opuslib.Decoder(16000, 1)
    validation_errors = 0
    total_decoded_pcm = 0
    
    for i, frame in enumerate(frames):
        try:
            decoded_pcm = decoder.decode(frame, frame_size)
            if len(decoded_pcm) == 0:
                print(f"   ⚠️  包 #{i+1} 解码后为空PCM")
                validation_errors += 1
            elif len(decoded_pcm) != frame_bytes:
                print(f"   ⚠️  包 #{i+1} 解码后大小异常: {len(decoded_pcm)} bytes (预期 {frame_bytes} bytes)")
            else:
                total_decoded_pcm += len(decoded_pcm)
        except Exception as e:
            print(f"   ❌ 包 #{i+1} 解码失败: {e}")
            validation_errors += 1
    
    print(f"   验证结果: {len(frames) - validation_errors}/{len(frames)} 包通过验证")
    print(f"   总解码PCM: {total_decoded_pcm} 字节")
    
    # 5. 对比原始文件解码
    print(f"\n5. 对比：直接解码原始Ogg文件（使用ffmpeg）")
    temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_wav.close()
    
    cmd_wav = [
        'ffmpeg', '-i', file_path,
        '-ar', '16000',
        '-ac', '1',
        temp_wav.name,
        '-y'
    ]
    
    result_wav = subprocess.run(cmd_wav, capture_output=True, text=True)
    if result_wav.returncode == 0:
        wav_size = os.path.getsize(temp_wav.name)
        print(f"   原始文件解码为WAV: {wav_size} 字节")
        os.unlink(temp_wav.name)
    
    # 6. 总结
    print(f"\n6. 总结")
    if validation_errors == 0:
        print(f"   [OK] 所有生成的Opus包都能正确解码")
        print(f"   [OK] 生成的包格式应该与服务器端兼容")
    else:
        print(f"   [WARNING] 有 {validation_errors} 个包验证失败")
        print(f"   [WARNING] 这些包可能无法被服务器端正确解码")
    
    # 清理
    os.unlink(temp_pcm.name)
    
    return frames

if __name__ == "__main__":
    file_path = "audio/test_audio.opus"
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
    else:
        frames = analyze_opus_file(file_path)

