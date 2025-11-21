# 关键问题发现

## 问题根源

通过仔细review项目代码，发现了测试脚本的根本问题：

### 设备实际行为

1. **VB6824配置**：
   - `CONFIG_VB6824_TYPE_OPUS_16K_20MS` 配置下，`AUDIO_RECV_CHENK_LEN = 40`
   - 每次从ringbuffer读取**固定40字节**的Opus包

2. **读取流程**：
   ```cpp
   // Application::OnAudioInput()
   ReadAudio(opus, 16000, 30 * 16000 / 1000);  // samples=480
   
   // Application::ReadAudio()
   opus.resize(samples);  // resize到480字节
   
   // VbAduioCodec::InputData()
   opus.resize(40);  // 重新resize到40字节！
   int samples = Read((uint8_t *)opus.data(), opus.size());  // 读取40字节
   
   // vb6824_audio_read()
   // 从ringbuffer读取一个完整item，item_size应该等于40
   return item_size;  // 返回实际读取的字节数（40）
   ```

3. **发送流程**：
   - 每次读取40字节的Opus包
   - 立即加入`audio_send_queue_`
   - MainLoop批量连续发送队列中的所有包

### 测试脚本的问题

1. **分割逻辑错误**：
   - 使用Opus解码器验证分割点，分割出92个包
   - 包大小范围：20-237字节，平均60.7字节
   - **问题**：设备发送的是**固定40字节**的包，而我们分割出来的包大小不一致！

2. **根本原因**：
   - 讯飞TTS返回的Opus数据是连续的裸数据包
   - 每个包的大小是**可变的**（取决于音频内容）
   - 但VB6824硬件每次读取**固定40字节**
   - 我们的分割逻辑没有考虑到VB6824的固定大小限制

## 解决方案

### 方案1：按固定40字节分割（推荐）

VB6824每次读取40字节，所以我们应该：
1. 将连续的Opus数据按**固定40字节**分割
2. 如果最后一个包不足40字节，补齐到40字节（用0填充，或者丢弃）
3. 批量连续发送所有40字节的包

### 方案2：模拟VB6824的读取方式

1. 按照VB6824的实际读取方式：每次读取40字节
2. 每10ms（AudioLoop循环）读取一次
3. MainLoop批量发送队列中的包

## 关键发现

**VB6824的Opus包大小是固定的40字节，不是可变的！**

测试脚本必须按照这个固定大小分割，而不是使用Opus解码器验证可变大小的包边界。

