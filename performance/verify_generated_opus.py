"""
验证从PCM重新编码生成的Opus包是否可解码
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from audio_encoder import AudioEncoder
import opuslib

def verify_generated_packets():
    """验证生成的Opus包"""
    print("=" * 60)
    print("验证从PCM重新编码生成的Opus包")
    print("=" * 60)
    
    # 生成Opus包
    encoder = AudioEncoder()
    frames = encoder.text_to_opus_frames("测试")
    
    if not frames:
        print("❌ 未能生成Opus包")
        return
    
    print(f"\n1. 生成结果：")
    print(f"   包数量: {len(frames)}")
    print(f"   总大小: {sum(len(f) for f in frames)} bytes")
    print(f"   平均包大小: {sum(len(f) for f in frames) / len(frames):.1f} bytes")
    print(f"   包大小范围: {min(len(f) for f in frames)} - {max(len(f) for f in frames)} bytes")
    
    # 2. 尝试解码验证
    print(f"\n2. 使用opuslib解码验证：")
    decoder = opuslib.Decoder(16000, 1)
    frame_size = 960  # 60ms @ 16kHz
    
    valid_count = 0
    invalid_count = 0
    total_pcm = 0
    
    for i, packet in enumerate(frames):
        try:
            pcm = decoder.decode(packet, frame_size)
            if len(pcm) > 0:
                valid_count += 1
                total_pcm += len(pcm)
                if i < 5:
                    print(f"   包 #{i+1}: [OK] 解码成功 -> {len(pcm)} bytes PCM")
            else:
                invalid_count += 1
                if i < 5:
                    print(f"   包 #{i+1}: [WARNING] 解码后PCM为空")
        except Exception as e:
            invalid_count += 1
            if i < 5:
                print(f"   包 #{i+1}: [ERROR] 解码失败: {e}")
    
    print(f"\n   验证结果: {valid_count}/{len(frames)} 包可解码")
    print(f"   总解码PCM: {total_pcm} bytes ({total_pcm / (16000 * 2):.2f} 秒)")
    
    if invalid_count > 0:
        print(f"   [WARNING] 有 {invalid_count} 个包无法解码")
    else:
        print(f"   [OK] 所有包都可以正确解码")
    
    # 3. 检查Opus TOC字节
    print(f"\n3. 检查Opus TOC字节（第一个字节）：")
    for i, packet in enumerate(frames[:5]):
        if len(packet) > 0:
            toc = packet[0]
            config = (toc >> 3) & 0x1f
            stereo = (toc >> 2) & 0x01
            frame_count = toc & 0x03
            print(f"   包 #{i+1}: TOC=0x{toc:02x}, config={config}, stereo={stereo}, frame_count={frame_count}")
    
    return frames

if __name__ == "__main__":
    frames = verify_generated_packets()

