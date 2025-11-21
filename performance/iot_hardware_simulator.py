import asyncio
from typing import List, Optional

from config import Config
from logger import Logger
from audio_encoder import AudioEncoder
from websocket_client import WebSocketClient


class IoTHardwareSimulator:
    """
    高拟真 IOT 硬件行为模拟器：
    - 建立 WS 连接（含请求头）
    - 定期发送 heartbeat
    - 发送 start_listen（严格对齐硬件：不包含 vad_side）
    - 逐包（二进制）发送 Opus 音频
    - 可选发送 stop_listen / enter_vad / exit_detect / play_voice / change_role
    """

    def __init__(self, connection_id: int = 1, logger: Optional[Logger] = None):
        self.connection_id = connection_id
        self.logger = logger or Logger()
        self.client = WebSocketClient(connection_id=self.connection_id)
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def _start_heartbeat(self, interval_sec: int = 10):
        try:
            while self.client.is_connected:
                await asyncio.sleep(interval_sec)
                # 发送心跳（字段与设备一致或超集，服务端容忍）
                await self.client.send_heartbeat()
        except asyncio.CancelledError:
            return

    async def connect(self) -> bool:
        return await self.client.connect()

    async def close(self):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        await self.client.close()

    async def play_welcome(self):
        await self.client.send_play_welcome_voice()

    async def enter_keep_listening(self):
        # 进入持续对话（与设备 EnterVad 一致）
        await self.client.send_enter_vad()

    async def exit_keep_listening(self):
        await self.client.send_exit_vad()

    async def change_role(self, role_type: int = 0):
        await self.client.send_change_role(role_type)

    async def start_heartbeat(self, interval_sec: int = 10):
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._start_heartbeat(interval_sec))

    async def send_speech(self, text: str, audio_frames: Optional[List[bytes]] = None,
                          send_stop: bool = True) -> bool:
        """完整语音流程：start_listen -> 逐包发送音频 -> (可选) stop_listen"""
        # 生成或使用外部提供的帧
        frames = audio_frames
        if frames is None:
            encoder = AudioEncoder(logger=self.logger)
            frames = encoder.text_to_opus_frames(text)

        # 使用已有客户端高级流程（严格对齐硬件协议）：
        # - start_listen（不含 vad_side）
        # - 批量连续二进制帧
        # - 可选 stop_listen
        original_send_stop = Config.SEND_STOP_LISTEN
        try:
            # 强制发送 stop_listen 由参数控制
            Config.SEND_STOP_LISTEN = send_stop
            return await self.client.send_user_message(text=text, audio_frames=frames)
        finally:
            Config.SEND_STOP_LISTEN = original_send_stop


