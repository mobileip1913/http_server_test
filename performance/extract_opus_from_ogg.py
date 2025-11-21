"""
从Ogg Opus容器中直接提取原始Opus数据包（不重新编码）

注意：由于Ogg格式解析复杂，如果提取失败，应该回退到PCM重新编码的方法
"""
import struct
import subprocess
import tempfile
import os
from typing import List, Optional

def extract_opus_packets_from_ogg(ogg_data: bytes) -> Optional[List[bytes]]:
    """
    从Ogg Opus容器中提取原始Opus数据包
    
    Ogg格式说明：
    - Ogg页面（Page）以'OggS'开头（4字节）
    - 每个页面包含多个段（Segments）
    - Opus包可能跨越多个页面
    - 需要解析段表（Segment Table）来重建Opus包
    
    这是一个简化实现，只提取基本的Opus包
    """
    if len(ogg_data) < 4 or ogg_data[:4] != b'OggS':
        return None
    
    packets = []
    offset = 0
    
    while offset < len(ogg_data):
        # 检查是否是Ogg页面开始
        if offset + 4 > len(ogg_data) or ogg_data[offset:offset+4] != b'OggS':
            break
        
        # Ogg页面结构（简化版，只提取关键字段）
        # 偏移量：
        # 0-3: 'OggS' (4 bytes)
        # 4: version (1 byte)
        # 5: header_type (1 byte)
        # 6-9: granule_pos (8 bytes, little-endian)
        # 10-13: serial_number (4 bytes)
        # 14-17: page_sequence (4 bytes)
        # 18-21: checksum (4 bytes)
        # 22: page_segments (1 byte) - 段表中段的数量
        
        if offset + 27 > len(ogg_data):
            break
        
        page_segments = ogg_data[offset + 22]
        
        # 读取段表（每个段1字节，表示该段的大小）
        segment_table_start = offset + 27
        if segment_table_start + page_segments > len(ogg_data):
            break
        
        segment_table = ogg_data[segment_table_start:segment_table_start + page_segments]
        data_start = segment_table_start + page_segments
        
        # 解析段，提取Opus包
        current_packet = b''
        for seg_size in segment_table:
            if seg_size == 0:
                # 段大小为0，表示这是段表结束
                continue
            
            if data_start + seg_size > len(ogg_data):
                break
            
            segment_data = ogg_data[data_start:data_start + seg_size]
            current_packet += segment_data
            
            # 如果段大小 < 255，表示这是包的最后一个段
            if seg_size < 255:
                if current_packet:
                    # 跳过OpusHead和OpusTags元数据包，只提取音频包
                    # OpusHead: 前8字节是 "OpusHead"
                    # OpusTags: 前8字节是 "OpusTags"
                    if len(current_packet) >= 8:
                        packet_type = current_packet[:8]
                        if packet_type == b'OpusHead' or packet_type == b'OpusTags':
                            # 这是元数据包，跳过
                            current_packet = b''
                            data_start += seg_size
                            continue
                    
                    # 这是音频包，添加到列表
                    packets.append(current_packet)
                    current_packet = b''
            
            data_start += seg_size
        
        # 移动到下一个页面（如果还有数据）
        if data_start >= len(ogg_data):
            break
        
        # 尝试找到下一个'OggS'标记
        next_page = ogg_data.find(b'OggS', data_start)
        if next_page == -1:
            break
        offset = next_page
    
    return packets if packets else None

