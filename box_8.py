import sounddevice as sd
import numpy as np
import queue
import json
import sys
import requests
import asyncio
import websockets
import io
import soundfile as sf
import re
import os
import time
import threading  # <-- 导入 threading 模块来解决 asyncio 冲突
from vosk import Model, KaldiRecognizer

# =========================== 配置区 ===========================
# ----------------- 语音识别 (Vosk) 配置 -----------------
VOSK_MODEL_PATH = "vosk-model-small-cn-0.22"
SAMPLE_RATE_STT = 16000  # 语音识别采样率
BLOCK_SIZE_STT = 8000  # 语音识别块大小

# ----------------- Dify 配置 -----------------
# 使用你提供的 IP 和 API Key
DIFY_URL = "http://192.168.137.4/v1/chat-messages"
DIFY_API_KEY = "app-mUsuCB9zdA3vqM3HFnCIDHCm"
conversation_id = None  # 连续会话 ID

# ----------------- TTS 配置 -----------------
# 使用你提供的 TTS 服务器地址
TTS_SERVER_WS = "ws://192.168.137.4:8000/ws/tts"

# ----------------- 音频设备配置 -----------------
# 麦克风和扬声器索引将在初始化函数中设置
mic_index = None
spk_index = None

# =========================== 全局状态 ===========================
q = queue.Queue()
is_playing = False  # 播放标志，用于在播放时暂停录音


# =========================== 辅助函数：TTS & Audio ===========================

def audio_callback(indata, frames, time, status):
    """sounddevice 录音回调函数"""
    global is_playing
    if status:
        print(status, file=sys.stderr)
    # 播放时丢弃输入，避免回声
    if not is_playing:
        q.put(bytes(indata))


def clean_text_for_tts(text):
    """清理 Dify 返回的文本，使其更适合 TTS"""
    # 移除 Markdown 格式和非中文/英文/数字/常见标点符号
    cleaned = re.sub(r'[\*\-\#`]', '', text)
    cleaned = re.sub(r'[^\w\u4e00-\u9fff，。！？,.!?'']+', '', cleaned)
    return cleaned


def split_text_for_tts(text, max_len=150):
    """按标点符号分段，防止单次 TTS 请求过长"""
    # 以句号、问号、感叹号及对应的中文标点分割
    sentences = re.split(r'([。！？!?])', text)
    chunks = []
    current = ""
    for s in sentences:
        current += s
        # 长度足够且遇到分割点
        if len(current) >= max_len or re.search(r'[。！？!?]$', current):
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return [c.strip() for c in chunks if len(c.strip()) > 2]  # 过滤掉过短的片段


async def speak_stream_async(text):
    """异步连接 TTS WebSocket 并播放音频"""
    global is_playing, spk_index
    if not text.strip():
        return

    try:
        # 1. 连接 TTS 服务
        async with websockets.connect(TTS_SERVER_WS) as ws:
            # 2. 发送待合成文本
            await ws.send(text)
            audio_buffer = io.BytesIO()

            # 3. 接收音频块
            while True:
                chunk = await ws.recv()
                if isinstance(chunk, str) and chunk == "__END__":  # 收到结束标志
                    break
                audio_buffer.write(chunk)

            # 4. 读取 WAV 数据并播放
            audio_buffer.seek(0)
            # 假设 TTS 服务器返回的音频采样率为 22050 (根据 TTS 库常用配置)
            wav_data, rate = sf.read(audio_buffer, dtype='float32')

            is_playing = True  # 设置播放标志，暂停识别
            sd.play(wav_data, samplerate=rate, device=spk_index)
            sd.wait()
            is_playing = False  # 播放结束
            time.sleep(0.5)  # 播放完延迟一小段时间

    except ConnectionRefusedError:
        is_playing = False
        print("\n❌ 语音播放失败：无法连接到 TTS 服务器。请确保服务器已运行且地址正确。")
    except Exception as e:
        is_playing = False
        print(f"\n❌ 语音播放失败: {e}")


def speak_stream(text):
    """同步调用异步 TTS 播放函数 (使用新线程避免 asyncio 冲突)"""

    # 解决方案：在独立的线程中执行 asyncio.run，避免冲突。
    def runner():
        asyncio.run(speak_stream_async(text))

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()  # 等待播放完成，确保语音顺序不错乱


# =========================== Dify API 调用函数 (已优化) ===========================

def dify_streaming_request(query):
    """向 Dify 平台发送流式聊天请求，并实时输出文本和进行 TTS 播放"""
    global conversation_id
    params = {
        "inputs": {},
        "query": query,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "user": "assistant-user-001"
    }

    headers = {
        'Authorization': f'Bearer {DIFY_API_KEY}',
        'Content-Type': 'application/json'
    }

    print("\n🤖 助手: ", end='', flush=True)
    full_answer = ""
    tts_buffer = ""  # 缓冲区用于分段 TTS 播放

    try:
        with requests.post(DIFY_URL, headers=headers, json=params, stream=True, timeout=60) as response:
            if response.status_code == 200:
                for line in response.iter_lines(decode_unicode=True):
                    if line:
                        try:
                            # 解析 SSE 格式数据
                            if line.startswith("data: "):
                                line = line[len("data: "):]

                            if line == "[DONE]" or not line: continue

                            data = json.loads(line)
                            event = data.get("event")

                            # 适配 Dify 的 "message" 和 "agent_message" 事件
                            if event in ["message", "agent_message"]:
                                answer = data.get("answer", "")
                                print(answer, end='', flush=True)  # 实时打印
                                full_answer += answer

                                # 实时进行 TTS 分段播放
                                tts_buffer += answer

                                # 使用正则表达式判断是否到达句子结束 (句号/问号/感叹号)
                                # 在缓冲区长度足够时才进行分段
                                if len(tts_buffer) > 15:
                                    # 检查最后一个字符是否是主要标点
                                    last_char_match = re.search(r'[。！？!?]', tts_buffer.strip()[-1:])

                                    if last_char_match:
                                        clean_chunk = clean_text_for_tts(tts_buffer)
                                        # 使用新的线程调用 speak_stream (已解决 asyncio.run 冲突)
                                        speak_stream(clean_chunk)
                                        tts_buffer = ""  # 清空缓冲区

                            elif event == "message_end":
                                # 播放剩余缓冲区内容
                                if tts_buffer:
                                    clean_chunk = clean_text_for_tts(tts_buffer)
                                    speak_stream(clean_chunk)

                                print()  # 换行
                                # 更新会话 ID
                                conversation_id = data.get("conversation_id", conversation_id)
                                return full_answer

                            elif event == "error":
                                print(f"\n助手: 错误发生: {data.get('message')}")
                                return full_answer
                        except json.JSONDecodeError:
                            continue

                # 如果流式响应在 [DONE] 之前结束
                if tts_buffer:
                    clean_chunk = clean_text_for_tts(tts_buffer)
                    speak_stream(clean_chunk)
                return full_answer

            else:
                print(f"请求失败，状态码: {response.status_code}")
                print(f"错误详情: {response.text}")
                return ""
    except requests.exceptions.Timeout:
        print("\n❌ Dify 请求超时")
        return ""
    except Exception as e:
        print(f"\n❌ Dify 请求失败: {e}")
        return ""


# =========================== 模式与初始化函数 ===========================

def initialize_audio_devices():
    """初始化音频设备，让用户选择"""
    global mic_index, spk_index
    print("\n--- 音频设备初始化 ---")
    devices = sd.query_devices()
    print("可用音频设备：")
    for i, dev in enumerate(devices):
        print(f"{i}: {dev['name']}  输入通道: {dev['max_input_channels']} 输出通道: {dev['max_output_channels']}")

    try:
        mic_index = int(input("请选择麦克风设备索引 (输入通道 > 0): "))
        spk_index = int(input("请选择扬声器设备索引 (输出通道 > 0): "))

        # 简单测试
        print("\n🔊 测试扬声器，播放 1kHz 正弦波...")
        # 使用 STT 的采样率进行测试
        t = np.linspace(0, 1, int(1 * SAMPLE_RATE_STT), False)
        tone = (0.1 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        sd.play(tone, samplerate=SAMPLE_RATE_STT, device=spk_index)
        sd.wait()
        print("✅ 音频设备初始化完成。")

    except ValueError:
        print("输入无效，请确保输入的是数字索引。")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 音频设备初始化失败: {e}")
        sys.exit(1)


def voice_mode():
    """语音对话模式：实时语音识别 -> Dify API -> TTS 播放"""
    global mic_index, q, is_playing

    try:
        # 设置日志级别以减少干扰
        Model.log_level = -1
        if not os.path.exists(VOSK_MODEL_PATH):
            print(f"❌ 错误：找不到 Vosk 模型路径 {VOSK_MODEL_PATH}")
            return

        vosk_model = Model(VOSK_MODEL_PATH)
        rec = KaldiRecognizer(vosk_model, SAMPLE_RATE_STT)
    except Exception as e:
        print(f"❌ 初始化语音识别组件失败：{e}")
        return

    print("\n" + "-" * 50)
    print("🎤 [语音对话模式] 已启动")
    print("请说话... (说 '退出' 结束会话)")
    print("-" * 50)

    # 启动麦克风输入流
    with sd.RawInputStream(samplerate=SAMPLE_RATE_STT, blocksize=BLOCK_SIZE_STT,
                           dtype='int16', channels=1, callback=audio_callback, device=mic_index):

        try:
            while True:
                # 从队列中获取音频数据
                data = q.get()

                # Vosk 识别处理
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()

                    if text:
                        print(f"\n🗣️ 识别到: {text}")
                        if text in ["退出", "返回", "再见", "停止"]:
                            print("会话结束。")
                            break

                        dify_streaming_request(text)

                else:
                    partial = json.loads(rec.PartialResult())
                    if partial.get("partial"):
                        # 实时显示部分识别结果
                        print("👂 正在识别:", partial["partial"], end="\r", flush=True)

        except KeyboardInterrupt:
            print("\n👋 结束语音识别")
        except Exception as e:
            print(f"\n❌ 语音识别过程中发生错误: {e}")


def keyboard_mode():
    """键盘打字模式：键盘输入 -> Dify API -> TTS 播放"""
    print("\n" + "-" * 50)
    print("⌨️ [键盘打字模式] 已启动 (输入 'exit' 退出)")
    print("-" * 50)

    while True:
        try:
            user_input = input("\n🗣️ 你说: ").strip()
            if not user_input: continue

            if user_input.lower() in ["exit", "quit", "退出"]:
                print("👋 退出键盘模式。")
                break

            # 1. 发送 Dify 请求，获取完整回答
            dify_streaming_request(user_input)

        except KeyboardInterrupt:
            print("\n👋 退出键盘模式。")
            break
        except Exception as e:
            print(f"\n❌ 发生错误: {e}")


def main():
    """主程序入口：模式选择"""

    # 首次运行时初始化音频设备
    initialize_audio_devices()

    while True:
        print("\n" + "=" * 50)
        print("           💬 Dify AI 语音助手")
        print("=" * 50)
        print("1. 🎤 语音对话模式 (实时识别 & 语音回复)")
        print("2. ⌨️ 键盘打字模式 (文字输入 & 语音回复)")
        print("0. ❌ 退出程序")

        choice = input("\n请选择模式 [1/2/0]: ").strip()

        if choice == '1':
            voice_mode()
        elif choice == '2':
            keyboard_mode()
        elif choice == '0':
            print("再见！")
            sys.exit()
        else:
            print("输入无效，请重新选择。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # 当在 main 循环中按 Ctrl+C 时的退出处理
        print("\n程序已强制退出。")