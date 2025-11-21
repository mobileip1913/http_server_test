"""
音频编码器：将文本转换为 Opus 编码的音频数据，完全模拟设备的发送流程
"""
import os
import sys
import struct
import subprocess
import tempfile
import time
import ctypes
from typing import Optional, List
from logger import Logger
from config import Config

# 在导入 opuslib 之前，尝试从项目目录加载 opus.dll
def _load_opus_dll_from_project():
    """尝试从项目目录加载 opus.dll，这样用户只需要把 DLL 放到项目目录即可"""
    try:
        # 获取项目根目录
        project_dir = os.path.dirname(os.path.abspath(__file__))
        dll_paths = [
            os.path.join(project_dir, "opus.dll"),
            os.path.join(project_dir, "libopus.dll"),
            os.path.join(project_dir, "libs", "opus.dll"),
            os.path.join(project_dir, "libs", "libopus.dll"),
        ]
        
        for dll_path in dll_paths:
            if os.path.exists(dll_path):
                try:
                    # 尝试加载 DLL（这会将其添加到系统 DLL 搜索路径）
                    ctypes.CDLL(dll_path)
                    logger = Logger()
                    logger.info(f"✅ 已从项目目录加载 Opus DLL: {dll_path}")
                    return True
                except Exception as e:
                    continue
        return False
    except Exception:
        return False

# 在导入 opuslib 之前尝试加载项目目录下的 DLL
_load_opus_dll_from_project()

class AudioEncoder:
    """音频编码器类（使用外部工具进行 TTS 和 Opus 编码）"""
    
    def __init__(self):
        self.logger = Logger()
    
    def text_to_opus_frames(self, text: str) -> Optional[List[bytes]]:
        """
        将文本转换为 Opus 编码的音频帧列表（每帧60ms）
        
        返回：Opus 帧列表，每个帧是一个独立的 Opus 数据包
        如果 SPLIT_OPUS_PACKETS=False，返回单个包含所有连续Opus数据的列表
        """
        try:
            # 方案1：优先使用预生成的音频文件（如果存在）
            if Config.AUDIO_FILE_PATH and os.path.exists(Config.AUDIO_FILE_PATH):
                self.logger.info(f"Using pre-generated audio file: {Config.AUDIO_FILE_PATH}")
                frames = self._load_audio_file_as_frames(Config.AUDIO_FILE_PATH)
                
                # 关键：从Ogg容器提取的原始Opus包（数量>10）必须逐个发送，不能合并！
                # 因为服务器端的 decoder.decode() 只能解码单个Opus包
                if frames:
                    if len(frames) > 10:
                        # 从Ogg提取的原始包，强制逐个发送（忽略SPLIT_OPUS_PACKETS配置）
                        self.logger.info(
                            f"Detected {len(frames)} raw Opus packets from Ogg container. "
                            f"These MUST be sent individually, ignoring SPLIT_OPUS_PACKETS={Config.SPLIT_OPUS_PACKETS}"
                        )
                        return frames  # 强制逐个发送
                    elif not Config.SPLIT_OPUS_PACKETS:
                        # 如果是重新编码的包（数量较少），且配置为不分割，则合并
                        self.logger.info(f"Not splitting Opus packets, sending {len(frames)} frames as single continuous data ({sum(len(f) for f in frames)} bytes)")
                        return [b''.join(frames)]  # 合并所有帧为一个
                
                return frames
            
            # 方案2：生成测试音频并分割为帧（静音，用于快速测试）
            self.logger.warning(
                "No audio file found, generating silent test audio. "
                f"To use real speech, run: python generate_tts_audio.py"
            )
            frames = self._generate_test_opus_frames(duration_ms=3000)  # 3秒的测试音频
            
            # 如果不分割，将所有帧合并为一个连续的数据
            if not Config.SPLIT_OPUS_PACKETS and frames:
                self.logger.info(f"Not splitting Opus packets, sending {len(frames)} frames as single continuous data ({sum(len(f) for f in frames)} bytes)")
                return [b''.join(frames)]  # 合并所有帧为一个
            
            return frames
            
        except Exception as e:
            self.logger.error(f"Failed to encode audio: {str(e)}")
            return None
    
    def _load_audio_file_as_frames(self, file_path: str) -> Optional[List[bytes]]:
        """
        加载音频文件并分割为 Opus 帧
        
        支持两种格式：
        1. 裸 Opus 数据包（Raw Opus packets）- 讯飞TTS返回的格式
        2. 标准音频文件（需要通过 ffmpeg 转换）
        """
        try:
            # 首先尝试直接读取为裸 Opus 数据包
            # 讯飞TTS返回的 Opus 数据已经是裸数据包格式，可以直接使用
            with open(file_path, 'rb') as f:
                opus_data = f.read()
            
            if not opus_data:
                self.logger.error(f"Audio file is empty: {file_path}")
                return None
            
            # 检查是否是 Ogg Opus 容器格式（以 OggS 开头）
            if opus_data[:4] == b'OggS':
                # 这是 Ogg 容器格式，需要使用 ffmpeg 转换
                self.logger.info("Detected Ogg Opus container, converting with ffmpeg...")
                frames = self._convert_ogg_opus_to_frames(file_path)
                
                # 关键：从Ogg容器提取的原始Opus包必须逐个发送，不能合并！
                # 因为服务器端的 decoder.decode() 只能解码单个Opus包
                # 即使 SPLIT_OPUS_PACKETS=False，也要逐个发送原始包
                if frames:
                    # 检查是否是从Ogg提取的原始包（通过检查帧数量，通常原始包数量较多）
                    # 如果是从Ogg提取的，强制逐个发送
                    if len(frames) > 10:  # 从Ogg提取的包通常有几十个
                        self.logger.info(
                            f"Detected {len(frames)} raw Opus packets from Ogg container. "
                            f"These MUST be sent individually (one per WebSocket message), "
                            f"ignoring SPLIT_OPUS_PACKETS={Config.SPLIT_OPUS_PACKETS}"
                        )
                        return frames  # 强制逐个发送
                    elif not Config.SPLIT_OPUS_PACKETS:
                        # 如果是重新编码的包（数量较少），且配置为不分割，则合并
                        self.logger.info(f"Not splitting Opus packets, sending {len(frames)} frames as single continuous data ({sum(len(f) for f in frames)} bytes)")
                        return [b''.join(frames)]  # 合并所有帧为一个
                
                return frames
            
            # 否则，假设是裸 Opus 数据包
            # 讯飞TTS返回的 Opus 数据是连续的裸数据包
            self.logger.info(f"Detected raw Opus packets, size: {len(opus_data)} bytes")
            
            # 关键发现（通过查看ws_server代码）：
            # 1. 服务器每个WebSocket消息的二进制数据会被当作一个Opus包解码
            # 2. 服务器使用 @discordjs/opus 的 decoder.decode(binaryData) 解码
            # 3. decoder.decode() 只能解码单个Opus包，不能解码连续的多个包
            # 4. 设备每次 SendAudio() 对应一个WebSocket消息，每个消息是一个独立的Opus包
            # 5. 所以需要将连续的Opus数据分割为多个独立的Opus包，每个包作为一个独立的WebSocket消息发送
            
            # 方案：使用Opus解码器智能分割连续的Opus数据为多个独立的包
            try:
                import opuslib
                decoder = opuslib.Decoder(Config.AUDIO_SAMPLE_RATE, Config.AUDIO_CHANNELS)
                frame_size = int(Config.AUDIO_SAMPLE_RATE * Config.OPUS_FRAME_DURATION_MS / 1000)
                
                frames = []
                offset = 0
                max_attempts = 500  # 增加尝试次数
                attempt = 0
                
                self.logger.info(f"Attempting intelligent Opus packet splitting for {len(opus_data)} bytes...")
                
                while offset < len(opus_data) and attempt < max_attempts:
                    attempt += 1
                    found = False
                    
                    # 尝试从最小包大小（通常20字节）开始，逐步增加
                    # Opus包大小范围：通常20-400字节
                    for try_size in range(20, min(400, len(opus_data) - offset + 1), 1):
                        if offset + try_size > len(opus_data):
                            break
                        
                        try:
                            packet = opus_data[offset:offset + try_size]
                            # 尝试解码，验证这是否是一个有效的Opus包
                            pcm = decoder.decode(packet, frame_size)
                            
                            # 验证解码结果：
                            # 1. 必须有PCM数据输出
                            # 2. PCM数据大小应该合理（至少大于0，通常应该是几百到几千字节）
                            # 3. 对于有效的Opus包，解码后应该有一定量的PCM数据
                            # 验证解码结果：只要解码成功且返回PCM数据，就认为是一个有效的Opus包
                            # Opus包大小可变，解码后的PCM大小也取决于帧大小
                            # 对于16kHz单声道：
                            #   - 20ms帧 = 320 samples = 640 bytes PCM
                            #   - 60ms帧 = 960 samples = 1920 bytes PCM
                            # 我们接受任何有效的解码结果（至少应该有PCM数据）
                            if len(pcm) > 0:
                                # 找到有效的Opus包边界
                                frames.append(packet)
                                offset += try_size
                                found = True
                                break
                        except Exception:
                            # 解码失败，继续尝试更大的包大小
                            continue
                    
                    if not found:
                        # 如果找不到有效包，可能数据有问题，尝试跳过少量字节
                        offset += 1
                        if offset >= len(opus_data) or offset - (sum(len(f) for f in frames)) > 50:
                            break
                
                if frames:
                    total_split = sum(len(f) for f in frames)
                    self.logger.info(
                        f"Split audio into {len(frames)} independent Opus packets "
                        f"(total {total_split}/{len(opus_data)} bytes, {total_split/len(opus_data)*100:.1f}% coverage)"
                    )
                    return frames
                else:
                    # 如果分割失败，回退到单帧方案（虽然可能不正确）
                    self.logger.warning("Failed to split Opus packets, sending as single frame (may cause decode errors)")
                    return [opus_data]
                    
            except ImportError:
                # 如果没有opuslib，回退到单帧方案
                self.logger.warning("opuslib not available, sending entire audio as single frame (may cause decode errors)")
                return [opus_data]
            except Exception as e:
                # 任何错误都回退到单帧方案
                self.logger.warning(f"Error during packet splitting: {e}, sending as single frame (may cause decode errors)")
                return [opus_data]
            
        except Exception as e:
            self.logger.error(f"Failed to load audio file: {e}")
            # 如果直接读取失败，尝试使用 ffmpeg 转换
            self.logger.info("Attempting to convert with ffmpeg...")
            return self._convert_with_ffmpeg(file_path)
    
    def _convert_ogg_opus_to_frames(self, file_path: str) -> Optional[List[bytes]]:
        """
        从 Ogg Opus 容器中提取原始 Opus 数据包（不重新编码）
        
        由于Ogg格式解析复杂且容易出错，直接使用已验证的PCM重新编码方法
        这样可以确保生成的Opus包格式正确，能被服务器端正确解码
        
        注意：从Ogg容器提取的原始Opus包必须逐个发送，不能合并！
        因为服务器端的 decoder.decode() 只能解码单个Opus包
        """
        # 直接使用已验证的PCM重新编码方法，确保生成的Opus包格式正确
        # 虽然这不是"原始"包，但至少能保证可解码性
        self.logger.info("Converting Ogg Opus to PCM and re-encoding to raw Opus packets...")
        return self._convert_with_ffmpeg(file_path)
    
    def _split_opus_packets(self, opus_data: bytes) -> Optional[List[bytes]]:
        """使用 opuslib 智能分割连续的 Opus 数据为多个独立的包"""
        try:
            import opuslib
            decoder = opuslib.Decoder(Config.AUDIO_SAMPLE_RATE, Config.AUDIO_CHANNELS)
            frame_size = int(Config.AUDIO_SAMPLE_RATE * Config.OPUS_FRAME_DURATION_MS / 1000)
            
            frames = []
            offset = 0
            max_attempts = 500
            attempt = 0
            
            self.logger.info(f"Attempting intelligent Opus packet splitting for {len(opus_data)} bytes...")
            
            while offset < len(opus_data) and attempt < max_attempts:
                attempt += 1
                found = False
                
                for try_size in range(20, min(400, len(opus_data) - offset + 1), 1):
                    if offset + try_size > len(opus_data):
                        break
                    
                    try:
                        packet = opus_data[offset:offset + try_size]
                        pcm = decoder.decode(packet, frame_size)
                        
                        if len(pcm) > 0:
                            frames.append(packet)
                            offset += try_size
                            found = True
                            break
                    except Exception:
                        continue
                
                if not found:
                    offset += 1
                    if offset >= len(opus_data) or offset - (sum(len(f) for f in frames)) > 50:
                        break
            
            if frames:
                total_split = sum(len(f) for f in frames)
                self.logger.info(
                    f"Split audio into {len(frames)} independent Opus packets "
                    f"(total {total_split}/{len(opus_data)} bytes, {total_split/len(opus_data)*100:.1f}% coverage)"
                )
                return frames
            else:
                self.logger.warning("Failed to split Opus packets, sending as single frame (may cause decode errors)")
                return [opus_data]
                
        except ImportError:
            self.logger.warning("opuslib not available, sending entire audio as single frame (may cause decode errors)")
            return [opus_data]
        except Exception as e:
            self.logger.warning(f"Error during packet splitting: {e}, sending as single frame (may cause decode errors)")
            return [opus_data]
    
    def _generate_raw_opus_from_pcm(self, pcm_data: bytes) -> Optional[List[bytes]]:
        """
        从 PCM 数据生成裸 Opus 数据包（不使用 Ogg 容器）
        
        参考服务器端 rate_control_sender.js 的 processRemainingAudio() 方法：
        - 完整帧：直接编码
        - 剩余数据：填充静音（0）到完整帧大小，然后编码
        """
        try:
            import opuslib
            # 尝试创建编码器，如果失败会抛出异常
            encoder = opuslib.Encoder(Config.AUDIO_SAMPLE_RATE, Config.AUDIO_CHANNELS, opuslib.APPLICATION_VOIP)
            # 设置编码参数（参考服务器端配置）
            # 服务器端使用默认参数，但opuslib默认bitrate=40kbps，我们设置为32kbps以匹配ffmpeg参数
            encoder.bitrate = 32000  # 32kbps，与ffmpeg编码参数一致
            encoder.complexity = Config.OPUS_COMPLEXITY  # 使用配置的复杂度（默认3）
            frame_size = int(Config.AUDIO_SAMPLE_RATE * Config.OPUS_FRAME_DURATION_MS / 1000)
            frame_bytes = frame_size * 2  # 16-bit = 2 bytes per sample
            
            frames = []
            offset = 0
            
            # 处理完整帧
            while offset + frame_bytes <= len(pcm_data):
                pcm_frame = pcm_data[offset:offset + frame_bytes]
                opus_frame = encoder.encode(pcm_frame, frame_size)
                frames.append(opus_frame)
                offset += frame_bytes
            
            # 处理剩余数据（参考服务器端 processRemainingAudio() 逻辑）
            remaining = len(pcm_data) - offset
            if remaining > 0:
                # 填充静音数据到完整帧大小
                padding = frame_bytes - remaining
                if padding > 0:
                    # 创建填充后的完整帧（剩余数据 + 静音）
                    padded_frame = bytearray(frame_bytes)
                    padded_frame[:remaining] = pcm_data[offset:]
                    # 剩余部分已经是0（静音），无需额外填充
                    opus_frame = encoder.encode(bytes(padded_frame), frame_size)
                    frames.append(opus_frame)
                    self.logger.info(f"Processed remaining {remaining} bytes PCM data with {padding} bytes padding (total {len(pcm_data)} bytes)")
            
            if frames:
                total_bytes = sum(len(f) for f in frames)
                self.logger.info(
                    f"Generated {len(frames)} raw Opus packets from PCM data "
                    f"(total {total_bytes} bytes, processed {len(pcm_data)} bytes PCM, "
                    f"coverage: {len(pcm_data) / (len(frames) * frame_bytes) * 100:.1f}%)"
                )
                return frames
            else:
                self.logger.warning("Failed to generate Opus packets from PCM")
                return None
                
        except ImportError:
            self.logger.error("opuslib not available, cannot generate raw Opus packets")
            return None
        except Exception as e:
            self.logger.error(f"Error generating Opus packets: {e}")
            return None
    
    def _convert_with_ffmpeg(self, file_path: str) -> Optional[List[bytes]]:
        """使用 ffmpeg 转换音频文件"""
        try:
            
            # 使用 ffmpeg 转换为 PCM，然后编码为 Opus 帧
            temp_pcm = tempfile.NamedTemporaryFile(suffix='.raw', delete=False)
            temp_pcm.close()
            
            temp_opus = tempfile.NamedTemporaryFile(suffix='.opus', delete=False)
            temp_opus.close()
            
            # 1. 转换为 PCM（16kHz, 单声道, 16-bit）
            cmd_pcm = [
                'ffmpeg',
                '-i', file_path,
                '-ar', str(Config.AUDIO_SAMPLE_RATE),
                '-ac', str(Config.AUDIO_CHANNELS),
                '-f', 's16le',  # 16-bit little-endian PCM
                temp_pcm.name,
                '-y'
            ]
            
            result = subprocess.run(cmd_pcm, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error(f"ffmpeg PCM conversion error: {result.stderr}")
                if os.path.exists(temp_pcm.name):
                    os.unlink(temp_pcm.name)
                if os.path.exists(temp_opus.name):
                    os.unlink(temp_opus.name)
                return None
            
            # 2. 读取并保存 PCM 数据（需要保留用于后续编码）
            with open(temp_pcm.name, 'rb') as f:
                pcm_data = f.read()
            
            # 保留 PCM 文件用于后续处理，稍后删除
            
            # 3. 尝试使用 opuslib 直接生成裸 Opus 数据包（更可靠）
            try:
                import opuslib
                frames = self._generate_raw_opus_from_pcm(pcm_data)
                if frames:
                    os.unlink(temp_pcm.name)
                    return frames
            except ImportError:
                self.logger.info("opuslib not available, using ffmpeg for Opus encoding...")
            except Exception as e:
                self.logger.warning(f"opuslib encoding failed: {e}, falling back to ffmpeg...")
            
            # 4. 回退方案：使用 ffmpeg 编码为 Opus（每帧60ms）
            cmd_opus = [
                'ffmpeg',
                '-f', 's16le',
                '-ar', str(Config.AUDIO_SAMPLE_RATE),
                '-ac', str(Config.AUDIO_CHANNELS),
                '-i', '-',  # 从 stdin 读取
                '-f', 'opus',
                '-acodec', 'libopus',
                '-b:a', '32k',
                '-frame_duration', '60',  # 60ms 帧
                '-compression_level', str(Config.OPUS_COMPLEXITY),
                temp_opus.name,
                '-y'
            ]
            
            process = subprocess.Popen(
                cmd_opus,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = process.communicate(input=pcm_data)
            
            if process.returncode == 0:
                # 读取编码后的 Opus 数据
                with open(temp_opus.name, 'rb') as f:
                    opus_data = f.read()
                
                os.unlink(temp_opus.name)
                os.unlink(temp_pcm.name)
                
                # 检查是否是 Ogg Opus 容器格式（以 OggS 开头）
                if opus_data[:4] == b'OggS':
                    # 这是 Ogg 容器格式，需要提取裸 Opus 数据包
                    # 重新读取 PCM 数据并生成裸 Opus 数据包
                    self.logger.warning("ffmpeg produced Ogg Opus container, generating raw packets from PCM...")
                    # 尝试使用 opuslib 从 PCM 生成裸 Opus 数据包
                    # 注意：需要先保存 temp_opus.name，因为 pcm_data 还在内存中
                    temp_opus_path = temp_opus.name
                    try:
                        frames = self._generate_raw_opus_from_pcm(pcm_data)
                        if frames:
                            os.unlink(temp_opus_path)
                            return frames
                    except Exception as e:
                        error_msg = str(e)
                        if "Could not find Opus library" in error_msg or "Opus library" in error_msg:
                            self.logger.error(f"Opus library not found: {e}")
                            self.logger.error("=" * 60)
                            self.logger.error("未找到 Opus 库，请确保 libs/opus.dll 文件存在")
                            self.logger.error("如果文件不存在，请从以下地址下载并放到 libs/ 目录：")
                            self.logger.error("https://github.com/xiph/opus/releases")
                            self.logger.error("=" * 60)
                        else:
                            self.logger.warning(f"Failed to generate Opus packets from PCM: {e}")
                        # 清理临时文件
                        if os.path.exists(temp_opus_path):
                            os.unlink(temp_opus_path)
                        return None
                else:
                    # 可能是裸 Opus 数据包，尝试分割
                    return self._split_opus_packets(opus_data)
            else:
                self.logger.error(f"ffmpeg Opus encoding error: {stderr.decode()}")
                if os.path.exists(temp_opus.name):
                    os.unlink(temp_opus.name)
                return None
                
        except FileNotFoundError:
            self.logger.error("ffmpeg not found. Please install ffmpeg.")
            return None
        except Exception as e:
            self.logger.error(f"Error loading audio file: {str(e)}")
            return None
    
    def _generate_test_opus_frames(self, duration_ms: int = 3000) -> Optional[List[bytes]]:
        """
        生成测试用的 Opus 音频帧列表（静音音频）
        
        注意：这是一个简化实现，实际应该使用真实的 TTS 服务
        或者提供预录制的音频文件
        """
        try:
            # 使用 ffmpeg 生成静音音频并编码为 Opus
            temp_output = tempfile.NamedTemporaryFile(suffix='.opus', delete=False)
            temp_output.close()
            
            duration_sec = duration_ms / 1000.0
            
            # 计算需要的帧数（每帧60ms）
            num_frames = int(duration_ms / Config.OPUS_FRAME_DURATION_MS)
            
            # 生成更长的音频（至少3秒，确保有足够的音频数据供识别）
            # 实际设备通常会说1-3秒的话
            if duration_ms < 2000:
                duration_ms = 2000  # 至少2秒
                duration_sec = duration_ms / 1000.0
            
            # 生成裸 Opus 数据包（不是 Ogg Opus 容器格式）
            # 项目代码期望的是裸 Opus 数据包，每个包最大 1000 字节
            # 使用 -f opus 会生成 Ogg 容器，我们需要使用 -f data 或直接输出 PCM 然后手动编码
            # 但为了简化，我们先生成 PCM，然后使用 opusenc 工具（如果可用）
            # 或者使用 ffmpeg 的 raw opus 输出（实验性）
            
            # 方案1：先生成 PCM，然后编码为 Opus（更可靠）
            temp_pcm = tempfile.NamedTemporaryFile(suffix='.raw', delete=False)
            temp_pcm.close()
            
            # 先生成 PCM 数据
            cmd_pcm = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', f'anullsrc=r={Config.AUDIO_SAMPLE_RATE}:cl=mono',  # 生成静音
                '-t', str(duration_sec),  # 持续时间
                '-f', 's16le',  # 16-bit little-endian PCM
                '-ar', str(Config.AUDIO_SAMPLE_RATE),
                '-ac', str(Config.AUDIO_CHANNELS),
                temp_pcm.name,
                '-y'
            ]
            
            result_pcm = subprocess.run(cmd_pcm, capture_output=True, text=True)
            if result_pcm.returncode != 0:
                self.logger.warning(f"ffmpeg PCM generation failed: {result_pcm.stderr}")
                if os.path.exists(temp_pcm.name):
                    os.unlink(temp_pcm.name)
                return None
            
            # 读取 PCM 数据
            with open(temp_pcm.name, 'rb') as f:
                pcm_data = f.read()
            os.unlink(temp_pcm.name)
            
            # 方案2：使用 ffmpeg 直接生成 Opus（但格式可能不对）
            # 尝试使用 -packet_size 参数生成裸 Opus 数据包
            cmd = [
                'ffmpeg',
                '-f', 's16le',
                '-ar', str(Config.AUDIO_SAMPLE_RATE),
                '-ac', str(Config.AUDIO_CHANNELS),
                '-i', '-',  # 从 stdin 读取 PCM
                '-f', 'opus',  # Opus 格式
                '-acodec', 'libopus',
                '-b:a', '32k',  # 比特率
                '-frame_duration', '60',  # 帧长度 60ms
                '-compression_level', str(Config.OPUS_COMPLEXITY),  # 复杂度
                '-packet_size', '0',  # 尝试禁用打包（实验性）
                temp_output.name,
                '-y'
            ]
            
            # 从 stdin 输入 PCM 数据
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = process.communicate(input=pcm_data)
            
            if process.returncode == 0:
                with open(temp_output.name, 'rb') as f:
                    opus_data = f.read()
                os.unlink(temp_output.name)
                
                # 检查是否是 Ogg Opus 格式（以 OggS 开头）
                if opus_data[:4] == b'OggS':
                    # 这是 Ogg 容器格式，需要提取裸 Opus 数据包
                    # 简化方案：警告用户，但继续使用（服务器可能能够处理）
                    self.logger.warning(
                        f"Generated Ogg Opus container ({len(opus_data)} bytes for {duration_ms}ms), "
                        f"server expects raw Opus packets - this may cause recognition issues. "
                        f"Consider using a real TTS service or pre-recorded audio file."
                    )
                else:
                    # 可能是裸 Opus 数据包
                    self.logger.info(
                        f"Generated raw Opus data: {len(opus_data)} bytes for {duration_ms}ms"
                    )
                
                # 简化方案：将整个 Opus 数据作为一个帧返回
                # 实际应该按照 Opus 数据包格式分割为多个 60ms 帧
                # 这里返回一个帧，测试时会逐帧发送
                frames = [opus_data]
                self.logger.warning(
                    f"Audio splitting not implemented - returning as single frame. "
                    f"Server may not recognize this as valid audio (only {len(opus_data)} bytes)"
                )
                return frames
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                self.logger.warning(f"Cannot generate test audio (ffmpeg may not be installed): {error_msg}")
                if os.path.exists(temp_output.name):
                    os.unlink(temp_output.name)
                return None
                
        except FileNotFoundError:
            self.logger.warning("ffmpeg not found. Test will use text-only mode.")
            return None
        except Exception as e:
            self.logger.warning(f"Cannot generate test audio: {str(e)}. Test will use text-only mode.")
            return None
