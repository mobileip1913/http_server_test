"""
使用Opus解码器验证并分割连续的Opus数据包
"""
import opuslib
import sys

def split_opus_packets(opus_data, sample_rate=16000, channels=1):
    """
    将连续的Opus数据包分割为独立的Opus包
    
    Args:
        opus_data: 连续的Opus数据包（bytes）
        sample_rate: 采样率（默认16000）
        channels: 声道数（默认1，单声道）
    
    Returns:
        分割后的Opus包列表
    """
    decoder = opuslib.Decoder(sample_rate, channels)
    frame_size = int(sample_rate * 60 / 1000)  # 60ms帧 = 960 samples
    
    packets = []
    offset = 0
    max_attempts = 500  # 最多尝试500次
    attempt = 0
    
    print(f"Total data: {len(opus_data)} bytes")
    print(f"Sample rate: {sample_rate}, Channels: {channels}, Frame size: {frame_size}")
    print("Attempting to split Opus packets...")
    
    while offset < len(opus_data) and attempt < max_attempts:
        attempt += 1
        found = False
        
        # 尝试从最小包大小（1字节）开始，逐步增加
        # Opus包通常最小20字节，最大400字节
        for size in range(1, min(400, len(opus_data) - offset + 1)):
            if offset + size > len(opus_data):
                break
            
            try:
                packet = opus_data[offset:offset + size]
                # 尝试解码这个包
                pcm = decoder.decode(packet, frame_size)
                
                # 如果解码成功，说明这是一个有效的Opus包
                if len(pcm) > 0:
                    packets.append(packet)
                    offset += size
                    found = True
                    print(f"  Packet #{len(packets)}: offset={offset-size}, size={size}, decoded={len(pcm)} bytes PCM")
                    break
            except Exception as e:
                # 解码失败，继续尝试更大的size
                continue
        
        if not found:
            # 如果找不到有效包，尝试跳过1字节
            offset += 1
            if offset >= len(opus_data):
                break
            # 如果跳过了太多字节，停止
            if offset - sum(len(p) for p in packets) > 50:
                print(f"Warning: Skipped too many bytes ({offset - sum(len(p) for p in packets)}), stopping")
                break
    
    total_split = sum(len(p) for p in packets)
    print(f"\nSplit complete:")
    print(f"  Total packets: {len(packets)}")
    print(f"  Total size: {total_split}/{len(opus_data)} bytes ({total_split/len(opus_data)*100:.1f}% coverage)")
    print(f"  Packet sizes: {[len(p) for p in packets[:10]]}... (first 10)")
    
    return packets

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_opus_packets.py <opus_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    with open(file_path, 'rb') as f:
        opus_data = f.read()
    
    packets = split_opus_packets(opus_data)
    
    # 保存分割后的包
    if packets:
        output_file = file_path.replace('.opus', '_split.opus')
        with open(output_file, 'wb') as f:
            for packet in packets:
                f.write(packet)
        print(f"\nSplit packets saved to: {output_file}")

