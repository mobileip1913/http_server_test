"""
批量生成 TTS 音频文件
从纯文本文件读取问题（每行一个问题），批量生成 opus 音频文件，并生成映射文件
支持三种功能：商品询问、商品对比、商品下单
"""
import os
import sys
import re
import asyncio
import subprocess
from pathlib import Path
from generate_tts_audio import synthesize_speech, logger

# 音频目录
AUDIO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "audio", "inquiries")
FILE_LIST_PATH = os.path.join(AUDIO_OUTPUT_DIR, "file_list.txt")

# 默认输入文件路径
INQUIRIES_INPUT_FILE = os.path.join(AUDIO_OUTPUT_DIR, "inquiries.txt")
COMPARES_INPUT_FILE = os.path.join(AUDIO_OUTPUT_DIR, "compares.txt")
ORDERS_INPUT_FILE = os.path.join(AUDIO_OUTPUT_DIR, "orders.txt")


def parse_text_file(file_path: str, file_type: str = "inquiry") -> list:
    """
    解析纯文本文件，每行一个问题
    
    Args:
        file_path: 文本文件路径
        file_type: 文件类型 ("inquiry", "compare", "order")
    
    Returns:
        文本列表，每个元素是 (index, filename, text) 的元组
    """
    texts = []
    
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return texts
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            # 跳过分隔符行（用于单文件模式）
            if line == "---" or line.startswith("---"):
                continue
            
            # 自动生成文件名
            index = len(texts) + 1
            if file_type == "inquiry":
                prefix = "inquiry"
            elif file_type == "compare":
                prefix = "compare"
            elif file_type == "order":
                prefix = "order"
            else:
                prefix = "unknown"
            
            filename = f"{prefix}_{index:03d}.opus"
            
            texts.append((index, filename, line))
    
    return texts


def parse_combined_file(file_path: str) -> tuple:
    """
    解析包含询问、对比和下单的组合文件（用 "---" 分隔）
    格式：询问部分 --- 对比部分 --- 下单部分
    
    Returns:
        (inquiries, compares, orders) 元组
    """
    inquiries = []
    compares = []
    orders = []
    current_section = "inquiry"
    section_count = 0
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return inquiries, compares, orders
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # 检查分隔符
            if line == "---" or line.startswith("---"):
                section_count += 1
                if section_count == 1:
                    current_section = "compare"
                elif section_count == 2:
                    current_section = "order"
                continue
            
            # 添加文本
            if current_section == "inquiry":
                index = len(inquiries) + 1
                prefix = "inquiry"
                filename = f"{prefix}_{index:03d}.opus"
                inquiries.append((index, filename, line))
            elif current_section == "compare":
                index = len(compares) + 1
                prefix = "compare"
                filename = f"{prefix}_{index:03d}.opus"
                compares.append((index, filename, line))
            elif current_section == "order":
                index = len(orders) + 1
                prefix = "order"
                filename = f"{prefix}_{index:03d}.opus"
                orders.append((index, filename, line))
    
    return inquiries, compares, orders


async def generate_opus_file(text: str, output_file: str) -> bool:
    """
    生成单个 opus 文件（PCM -> Opus）
    """
    # 先生成 PCM 文件
    pcm_file = output_file.replace('.opus', '.pcm')
    logger.info(f"Generating PCM for: {os.path.basename(output_file)}")
    
    success = await synthesize_speech(text, pcm_file, audio_format="raw")
    
    if not success:
        logger.error(f"Failed to generate PCM for: {os.path.basename(output_file)}")
        return False
    
    # 使用 ffmpeg 将 PCM 转换为 Opus
    try:
        logger.info(f"Converting PCM to Opus: {os.path.basename(output_file)}")
        subprocess.run([
            "ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
            "-i", pcm_file, "-c:a", "libopus", "-b:a", "32k", "-frame_duration", "60",
            output_file
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 删除临时 PCM 文件
        if os.path.exists(pcm_file):
            os.remove(pcm_file)
        
        logger.info(f"✓ Generated: {os.path.basename(output_file)}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to convert PCM to Opus: {e}")
        return False


def generate_file_list(inquiries: list, compares: list, orders: list, output_path: str):
    """
    生成 file_list.txt 映射文件
    
    Args:
        inquiries: 询问列表 [(index, filename, text), ...]
        compares: 对比列表 [(index, filename, text), ...]
        orders: 下单列表 [(index, filename, text), ...]
        output_path: 输出文件路径
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        if inquiries:
            f.write("Inquiry Files:\n")
            for index, filename, text in inquiries:
                f.write(f"{index:03d}: {filename} - {text}\n")
            f.write("\n")
        
        if compares:
            f.write("Compare Files:\n")
            for index, filename, text in compares:
                f.write(f"{index:03d}: {filename} - {text}\n")
            f.write("\n")
        
        if orders:
            f.write("Order Files:\n")
            for index, filename, text in orders:
                f.write(f"{index:03d}: {filename} - {text}\n")
    
    logger.info(f"✓ Generated mapping file: {output_path}")


async def generate_all_audio_files(inquiries: list, compares: list, orders: list,
                                   skip_existing: bool = True) -> dict:
    """
    批量生成所有音频文件
    
    Args:
        inquiries: 询问列表 [(index, filename, text), ...]
        compares: 对比列表 [(index, filename, text), ...]
        orders: 下单列表 [(index, filename, text), ...]
        skip_existing: 是否跳过已存在的文件
    
    Returns:
        统计信息字典
    """
    stats = {
        "inquiry_total": len(inquiries),
        "inquiry_success": 0,
        "inquiry_failed": 0,
        "compare_total": len(compares),
        "compare_success": 0,
        "compare_failed": 0,
        "order_total": len(orders),
        "order_success": 0,
        "order_failed": 0
    }
    
    # 确保输出目录存在
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    
    # 生成询问音频
    if inquiries:
        logger.info("=" * 60)
        logger.info("Generating Inquiry Audio Files")
        logger.info("=" * 60)
        
        for index, filename, text in inquiries:
            output_file = os.path.join(AUDIO_OUTPUT_DIR, filename)
            
            # 检查文件是否已存在
            if skip_existing and os.path.exists(output_file):
                logger.info(f"⏭  Skipping (exists): {filename}")
                stats["inquiry_success"] += 1
                continue
            
            success = await generate_opus_file(text, output_file)
            if success:
                stats["inquiry_success"] += 1
            else:
                stats["inquiry_failed"] += 1
            
            # 添加延迟，避免 API 限流
            await asyncio.sleep(0.5)
    
    # 生成对比音频
    if compares:
        logger.info("=" * 60)
        logger.info("Generating Compare Audio Files")
        logger.info("=" * 60)
        
        for index, filename, text in compares:
            output_file = os.path.join(AUDIO_OUTPUT_DIR, filename)
            
            # 检查文件是否已存在
            if skip_existing and os.path.exists(output_file):
                logger.info(f"⏭  Skipping (exists): {filename}")
                stats["compare_success"] += 1
                continue
            
            success = await generate_opus_file(text, output_file)
            if success:
                stats["compare_success"] += 1
            else:
                stats["compare_failed"] += 1
            
            # 添加延迟，避免 API 限流
            await asyncio.sleep(0.5)
    
    # 生成下单音频
    if orders:
        logger.info("=" * 60)
        logger.info("Generating Order Audio Files")
        logger.info("=" * 60)
        
        for index, filename, text in orders:
            output_file = os.path.join(AUDIO_OUTPUT_DIR, filename)
            
            # 检查文件是否已存在
            if skip_existing and os.path.exists(output_file):
                logger.info(f"⏭  Skipping (exists): {filename}")
                stats["order_success"] += 1
                continue
            
            success = await generate_opus_file(text, output_file)
            if success:
                stats["order_success"] += 1
            else:
                stats["order_failed"] += 1
            
            # 添加延迟，避免 API 限流
            await asyncio.sleep(0.5)
    
    return stats


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("Batch TTS Audio Generator")
    logger.info("=" * 60)
    
    # 解析命令行参数
    skip_existing = True
    input_file = None
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--force":
            skip_existing = False
            logger.info("Force mode: will regenerate all files")
        elif sys.argv[i] == "--input" and i + 1 < len(sys.argv):
            input_file = sys.argv[i + 1]
            i += 1
        i += 1
    
    # 读取输入文件
    inquiries = []
    compares = []
    orders = []
    
    if input_file:
        # 使用指定的输入文件（可能是组合文件）
        logger.info(f"Reading input file: {input_file}")
        inquiries, compares, orders = parse_combined_file(input_file)
    else:
        # 尝试读取独立的文件
        if os.path.exists(INQUIRIES_INPUT_FILE):
            logger.info(f"Reading inquiries file: {INQUIRIES_INPUT_FILE}")
            inquiries = parse_text_file(INQUIRIES_INPUT_FILE, "inquiry")
        
        if os.path.exists(COMPARES_INPUT_FILE):
            logger.info(f"Reading compares file: {COMPARES_INPUT_FILE}")
            compares = parse_text_file(COMPARES_INPUT_FILE, "compare")
        
        if os.path.exists(ORDERS_INPUT_FILE):
            logger.info(f"Reading orders file: {ORDERS_INPUT_FILE}")
            orders = parse_text_file(ORDERS_INPUT_FILE, "order")
    
    if not inquiries and not compares and not orders:
        logger.error("No inquiries, compares, or orders found!")
        logger.info("Please create one of the following:")
        logger.info(f"  - {INQUIRIES_INPUT_FILE} (one question per line)")
        logger.info(f"  - {COMPARES_INPUT_FILE} (one question per line)")
        logger.info(f"  - {ORDERS_INPUT_FILE} (one question per line)")
        logger.info("  - Or use --input <file> with a combined file (separated by '---')")
        return 1
    
    logger.info(f"Found {len(inquiries)} inquiries, {len(compares)} compares, and {len(orders)} orders")
    logger.info("=" * 60)
    
    # 批量生成音频文件
    stats = await generate_all_audio_files(inquiries, compares, orders, skip_existing)
    
    # 生成映射文件
    if stats['inquiry_success'] > 0 or stats['compare_success'] > 0 or stats['order_success'] > 0:
        generate_file_list(inquiries, compares, orders, FILE_LIST_PATH)
    
    # 输出统计信息
    logger.info("=" * 60)
    logger.info("Generation Summary")
    logger.info("=" * 60)
    logger.info(f"Inquiries: {stats['inquiry_success']}/{stats['inquiry_total']} successful, "
                f"{stats['inquiry_failed']} failed")
    logger.info(f"Compares: {stats['compare_success']}/{stats['compare_total']} successful, "
                f"{stats['compare_failed']} failed")
    logger.info(f"Orders: {stats['order_success']}/{stats['order_total']} successful, "
                f"{stats['order_failed']} failed")
    logger.info("=" * 60)
    
    total_success = stats['inquiry_success'] + stats['compare_success'] + stats['order_success']
    total_failed = stats['inquiry_failed'] + stats['compare_failed'] + stats['order_failed']
    total = stats['inquiry_total'] + stats['compare_total'] + stats['order_total']
    
    if total_failed == 0:
        logger.info("✓ All audio files generated successfully!")
        return 0
    else:
        logger.warning(f"⚠ {total_failed} files failed to generate")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

