import sys
import os
import wave
from typing import List

try:
    from opuslib import Decoder
except Exception as e:
    print("opuslib not installed or failed to import:", e)
    sys.exit(1)


def split_opus_frames(opus_data: bytes, sample_rate: int = 16000) -> List[bytes]:
    """
    Heuristically split a raw concatenation of Opus packets into individual packets
    by attempting to decode progressively increasing chunk sizes.

    This mirrors the tolerant logic used in the performance audio encoder.
    """
    channels = 1
    decoder = Decoder(sample_rate, channels)
    frame_size = int(sample_rate * 0.06)  # 60ms frames as common target (e.g., 960 at 16kHz)

    frames: List[bytes] = []
    offset = 0
    max_attempts = 500
    attempts = 0

    while offset < len(opus_data) and attempts < max_attempts:
        attempts += 1
        found = False

        # Try from ~20 bytes upward to a reasonable upper bound for Opus packets
        upper_bound = min(400, len(opus_data) - offset)
        if upper_bound <= 0:
            break

        for try_size in range(20, upper_bound + 1):
            packet = opus_data[offset : offset + try_size]
            try:
                pcm = decoder.decode(packet, frame_size)
                if len(pcm) >= 100:  # minimal sanity threshold
                    frames.append(packet)
                    offset += try_size
                    found = True
                    break
            except Exception:
                # Keep increasing try_size
                continue

        if not found:
            # Skip a byte and try again to recover alignment
            offset += 1
            # bail out if we're clearly not making progress
            if offset >= len(opus_data):
                break

    return frames


def decode_to_wav(opus_bytes: bytes, wav_path: str, sample_rate: int = 16000):
    channels = 1
    decoder = Decoder(sample_rate, channels)
    frame_size = int(sample_rate * 0.06)

    frames = split_opus_frames(opus_bytes, sample_rate)
    if not frames:
        raise RuntimeError("Failed to split Opus data into frames; cannot decode.")

    pcm_all = bytearray()
    for pkt in frames:
        pcm = decoder.decode(pkt, frame_size)
        if pcm:
            pcm_all.extend(pcm)

    if not pcm_all:
        raise RuntimeError("Decoded PCM is empty.")

    # Write WAV (16-bit PCM little-endian)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm_all))


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("audio", "test_audio.opus")
    out_wav = sys.argv[2] if len(sys.argv) > 2 else os.path.join("audio", "test_audio_check.wav")

    if not os.path.isfile(in_path):
        print(f"Input file not found: {in_path}")
        sys.exit(1)

    with open(in_path, "rb") as f:
        data = f.read()

    try:
        decode_to_wav(data, out_wav)
    except Exception as e:
        print("Decoding failed:", e)
        sys.exit(2)

    print(f"WAV written: {out_wav}")


if __name__ == "__main__":
    main()


