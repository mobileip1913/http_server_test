import os
import sys
import time
import json
import base64
import hmac
import hashlib
import requests
import subprocess
import wave


# Xunfei RAASR credentials (from user-provided console screenshot)
APP_ID = os.getenv("XFYUN_APPID", "c7f30371")
SECRET_KEY = os.getenv("XFYUN_SECRET_KEY", "881447e1c58c944e1c169880548cf751")

UPLOAD_URL = "https://raasr.xfyun.cn/v2/api/upload2"
RESULT_URL = "https://raasr.xfyun.cn/v2/api/getResult"


def ffmpeg_convert_to_wav(input_path: str, output_path: str) -> None:
    """Convert any audio to 16kHz mono PCM WAV using ffmpeg."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def get_wav_duration_sec(path: str) -> int:
    with wave.open(path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration_sec = frames / float(rate) if rate else 0
    # API 文档要求为秒，向上取整避免低估
    import math
    return int(math.ceil(duration_sec))


def generate_signa(app_id: str, secret_key: str, ts: str) -> str:
    """Generate signa per RAASR doc: signa = base64(hmac_sha1(secret_key, md5(appId+ts)))."""
    md5_src = (app_id + ts).encode("utf-8")
    md5_digest = hashlib.md5(md5_src).hexdigest()
    hm = hmac.new(secret_key.encode("utf-8"), md5_digest.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(hm.digest()).decode("utf-8")


def upload_audio(wav_path: str) -> str:
    ts = str(int(time.time()))
    signa = generate_signa(APP_ID, SECRET_KEY, ts)
    file_size = os.path.getsize(wav_path)
    file_name = os.path.basename(wav_path)
    duration_sec = get_wav_duration_sec(wav_path)

    params = {
        "appId": APP_ID,
        "ts": ts,
        "signa": signa,
        "fileSize": str(file_size),
        "fileName": file_name,
        # 官方文档 duration 单位为 ms（有的示例用秒），这里传 ms 更稳妥
        # 文档为秒；若传毫秒会被视为超长，导致配额报错
        "duration": str(duration_sec),
    }

    with open(wav_path, "rb") as f:
        files = {"file": f}
        resp = requests.post(UPLOAD_URL, params=params, files=files, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") == "000000":
        return data.get("data")  # orderId
    raise RuntimeError(f"Upload failed: {data}")


def get_result(order_id: str, poll_interval: float = 5.0, timeout: float = 600.0) -> dict:
    start = time.time()
    while True:
        ts = str(int(time.time()))
        signa = generate_signa(APP_ID, SECRET_KEY, ts)
        params = {
            "appId": APP_ID,
            "ts": ts,
            "signa": signa,
            "orderId": order_id,
        }
        resp = requests.get(RESULT_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == "000000":
            status = data.get("data", {}).get("status")
            if status == 4:  # completed
                return data.get("data", {})
            if status in (3, 1, 2):  # processing/queued
                if time.time() - start > timeout:
                    raise TimeoutError("Polling ASR result timed out")
                time.sleep(poll_interval)
                continue
            raise RuntimeError(f"ASR failed, status={status}, response={data}")
        else:
            # e.g., transient errors
            if time.time() - start > timeout:
                raise RuntimeError(f"ASR polling failed: {data}")
            time.sleep(poll_interval)


def extract_texts(result_data: dict) -> str:
    # RAASR 返回数据结构中 result 可能是 JSON 字符串或对象
    result = result_data.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return str(result)

    # 兼容多种结构，常见为[{onebest: "..."}, ...] 或者 ws/cw 结构
    texts = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                if "onebest" in item:
                    texts.append(item.get("onebest", ""))
                elif "ws" in item:
                    # 兼容 iat 样式
                    for ws in item.get("ws", []):
                        for cw in ws.get("cw", []):
                            w = cw.get("w")
                            if w:
                                texts.append(w)
    elif isinstance(result, dict):
        if "lattice" in result:
            for lat in result.get("lattice", []):
                ob = lat.get("json_1best") or lat.get("onebest")
                if ob:
                    try:
                        obj = json.loads(ob)
                        texts.append(extract_texts({"result": obj}))
                    except Exception:
                        texts.append(str(ob))
        elif "onebest" in result:
            texts.append(result.get("onebest", ""))

    return "".join(texts).strip()


def main():
    base_dir = os.path.dirname(__file__)
    opus_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base_dir, "audio", "test_audio.opus")
    wav_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(base_dir, "audio", "test_audio_raasr.wav")

    if not os.path.isfile(opus_path):
        print(f"Input opus not found: {opus_path}")
        sys.exit(1)

    try:
        ffmpeg_convert_to_wav(opus_path, wav_path)
    except subprocess.CalledProcessError as e:
        # Fallback: use internal opuslib-based splitter/decoder
        try:
            from decode_opus_to_wav import decode_to_wav
            with open(opus_path, "rb") as f:
                data = f.read()
            decode_to_wav(data, wav_path)
        except Exception as e2:
            print("ffmpeg conversion failed and opuslib fallback failed", e, e2)
            sys.exit(2)

    try:
        order_id = upload_audio(wav_path)
        print(f"Upload OK, orderId: {order_id}")
        data = get_result(order_id)
        text = extract_texts(data)
        print("ASR raw:")
        print(json.dumps(data, ensure_ascii=False))
        print("\nRecognized text:")
        print(text)
    except Exception as e:
        print("ASR failed:", e)
        sys.exit(3)


if __name__ == "__main__":
    main()


