# -*- coding: utf-8 -*-
from fastapi import FastAPI, WebSocket
import asyncio
import torch
import collections
from TTS.utils import radam
from TTS.api import TTS
import io
import soundfile as sf

# -------------------------------
torch.serialization.add_safe_globals([radam.RAdam, collections.defaultdict, dict])
# -------------------------------

MODEL_NAME = "tts_models/zh-CN/baker/tacotron2-DDC-GST"
tts = TTS(model_name=MODEL_NAME)

app = FastAPI()

@app.websocket("/ws/tts")
async def websocket_tts(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            text = await ws.receive_text()
            if not text.strip():
                continue
            print("收到文本:", text)

            # 生成完整 WAV
            wav_bytes_io = io.BytesIO()
            wav_result = tts.tts(text)  # 不传 speaker/language
            if isinstance(wav_result, tuple) and len(wav_result) == 2:
                wav_array, rate = wav_result
            else:
                wav_array = wav_result
                rate = tts.synthesizer.output_sample_rate
            sf.write(wav_bytes_io, wav_array, rate, format="WAV")
            wav_bytes_io.seek(0)

            # 分块发送
            chunk_size = 4096
            while True:
                chunk = wav_bytes_io.read(chunk_size)
                if not chunk:
                    break
                await ws.send_bytes(chunk)

            # 发送结束标志
            await ws.send_text("__END__")
            print("语音发送完成")
    except Exception as e:
        print("WebSocket 连接断开:", e)
