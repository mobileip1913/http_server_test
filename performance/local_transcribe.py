"""
本地语音识别：使用 Whisper 离线识别音频内容
"""
import os
import sys

def transcribe_with_whisper(wav_path: str) -> str:
    """使用 Whisper 识别音频"""
    try:
        import whisper
        print("Loading Whisper model (base)...")
        model = whisper.load_model("base")
        print("Transcribing audio...")
        result = model.transcribe(wav_path, language="zh")
        text = result.get("text", "").strip()
        print(f"Whisper raw result: {result}")
        print(f"Extracted text: '{text}'")
        return text if text else None
    except ImportError:
        print("Whisper not installed. Install with: pip install openai-whisper")
        return None
    except Exception as e:
        import traceback
        print(f"Whisper error: {e}")
        traceback.print_exc()
        return None

def transcribe_with_speech_recognition(wav_path: str) -> str:
    """使用 speech_recognition 库（离线引擎）"""
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
        # 尝试使用离线引擎（如 CMU Sphinx，但需要安装）
        try:
            text = r.recognize_sphinx(audio, language="zh-CN")
            return text
        except:
            # 如果没有离线引擎，返回 None
            return None
    except ImportError:
        print("speech_recognition not installed. Install with: pip install SpeechRecognition")
        return None

def main():
    base_dir = os.path.dirname(__file__)
    wav_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base_dir, "audio", "test_audio_local.wav")
    
    if not os.path.isfile(wav_path):
        print(f"WAV file not found: {wav_path}")
        sys.exit(1)
    
    print(f"Transcribing: {wav_path}")
    print("=" * 60)
    
    # 优先使用 Whisper
    text = transcribe_with_whisper(wav_path)
    if text:
        print("\n" + "=" * 60)
        print("Recognized text (Whisper):")
        print("=" * 60)
        print(text)
        print("=" * 60)
        return
    elif text is not None:
        print("\nWhisper returned empty text")
        print("Debug: result type =", type(text))
    
    # 备选：speech_recognition
    text = transcribe_with_speech_recognition(wav_path)
    if text:
        print("Recognized text (speech_recognition):")
        print(text)
        return
    
    print("No local ASR engine available.")
    print("Options:")
    print("  1. Install Whisper: pip install openai-whisper")
    print("  2. Install speech_recognition: pip install SpeechRecognition")
    print("  3. Use online service (requires quota)")

if __name__ == "__main__":
    main()

