"""
验证从Ogg容器提取的Opus包是否有效
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from extract_opus_from_ogg import extract_opus_packets_from_ogg
import opuslib

def verify_opus_packets(file_path):
    """验证提取的Opus包"""
    print("=" * 60)
    print("验证从Ogg容器提取的Opus包")
    print("=" * 60)
    
    # 1. 提取包
    with open(file_path, 'rb') as f:
        ogg_data = f.read()
    
    packets = extract_opus_packets_from_ogg(ogg_data)
    
    if not packets:
        print("❌ 未能提取任何Opus包")
        return
    
    print(f"\n1. 提取结果：")
    print(f"   包数量: {len(packets)}")
    print(f"   总大小: {sum(len(p) for p in packets)} bytes")
    print(f"   平均包大小: {sum(len(p) for p in packets) / len(packets):.1f} bytes")
    print(f"   包大小范围: {min(len(p) for p in packets)} - {max(len(p) for p in packets)} bytes")
    
    # 2. 检查包的前几个字节（Opus包的特征）
    print(f"\n2. 前5个包的格式检查：")
    for i, packet in enumerate(packets[:5]):
        print(f"   包 #{i+1}:")
        print(f"     大小: {len(packet)} bytes")
        print(f"     前16字节(hex): {packet[:16].hex()}")
        print(f"     前16字节(ascii): {repr(packet[:16])}")
    
    # 3. 尝试解码验证
    print(f"\n3. 使用opuslib解码验证：")
    decoder = opuslib.Decoder(16000, 1)
    frame_size = 960  # 60ms @ 16kHz
    
    valid_count = 0
    invalid_count = 0
    
    for i, packet in enumerate(packets):
        try:
            pcm = decoder.decode(packet, frame_size)
            if len(pcm) > 0:
                valid_count += 1
                if i < 5:
                    print(f"   包 #{i+1}: ✅ 解码成功 -> {len(pcm)} bytes PCM")
            else:
                invalid_count += 1
                if i < 5:
                    print(f"   包 #{i+1}: ⚠️  解码后PCM为空")
        except Exception as e:
            invalid_count += 1
            if i < 5:
                    print(f"   包 #{i+1}: [ERROR] 解码失败: {e}")
    
    print(f"\n   验证结果: {valid_count}/{len(packets)} 包可解码")
    
    if invalid_count > 0:
        print(f"   ⚠️  有 {invalid_count} 个包无法解码")
    
    # 4. 检查是否包含Ogg页头
    print(f"\n4. 检查是否包含Ogg页头：")
    ogg_markers = sum(1 for p in packets if b'OggS' in p[:100])
    if ogg_markers > 0:
        print(f"   ⚠️  发现 {ogg_markers} 个包包含'OggS'标记（可能包含Ogg页头）")
    else:
        print(f"   ✅ 没有包包含'OggS'标记（应该是纯Opus包）")
    
    # 5. 检查Opus TOC字节（Table of Contents）
    print(f"\n5. 检查Opus TOC字节（第一个字节）：")
    toc_values = {}
    for i, packet in enumerate(packets[:10]):
        if len(packet) > 0:
            toc = packet[0]
            toc_str = f"0x{toc:02x} ({toc})"
            if toc_str not in toc_values:
                toc_values[toc_str] = 0
            toc_values[toc_str] += 1
            if i < 5:
                # 解析TOC位
                config = (toc >> 3) & 0x1f
                stereo = (toc >> 2) & 0x01
                frame_count = toc & 0x03
                print(f"   包 #{i+1}: TOC={toc_str}, config={config}, stereo={stereo}, frame_count={frame_count}")
    
    print(f"\n   TOC值分布: {dict(toc_values)}")
    
    return packets

if __name__ == "__main__":
    file_path = "audio/test_audio.opus"
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
    else:
        packets = verify_opus_packets(file_path)

