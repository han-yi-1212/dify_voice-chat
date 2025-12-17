* **`main.py`**：这是 **TTS（语音合成）服务器**，基于 FastAPI 和 Coqui TTS。
* **`客户端.py`**：它负责录音、调用 Vosk 进行识别、请求 Dify API，并接收 TTS 服务器的音频进行播放。

# Dify AI Voice Assistant (语音通话助手)

本项目是一个基于 Python 的全双工语音对话系统。它将本地语音识别 (STT)、**Dify** 智能体 (LLM) 和本地语音合成 (TTS) 结合在一起，实现了与 AI 智能体的实时语音通话功能。

## ✨ 功能特性

* **🗣️ 实时语音识别 (STT)**：集成 **Vosk** 离线模型，支持中文高精度识别。
* **🧠 智能大脑 (LLM)**：对接 **Dify API**，支持流式传输 (Streaming)，实现低延迟回复。
* **🔊 神经语音合成 (TTS)**：基于 **Coqui TTS** (Tacotron2 + GST) 搭建的 WebSocket 服务端，声音自然逼真。
* **⚡ 异步流式交互**：打字机效果的语音播报，AI 边思考边说话，无需等待完整生成。
* **双模式支持**：
* 🎤 **语音模式**：纯语音交互。
* ⌨️ **键盘模式**：文字输入，语音回复。



## 📂 文件结构说明

| 文件名 | 类型 | 描述 |
| --- | --- | --- |
| `客户端.py` | **客户端** | 负责麦克风录音、Vosk 识别、调用 Dify API 以及接收音频播放。 |
| `main.py` | **TTS 服务端** | 基于 FastAPI 和 WebSocket 的语音合成服务，负责将文字转为 WAV 音频。 |


## 🛠️ 环境准备

### 1. 依赖安装

请确保您的环境已安装 Python 3.8+。建议创建虚拟环境并安装以下依赖：

```bash
# 客户端依赖 (客户端.py)
pip install sounddevice numpy vosk requests websockets soundfile

# 服务端依赖 (main.py)
pip install fastapi uvicorn "uvicorn[standard]" torch TTS

```

### 2. 模型准备

* **Vosk 模型 (STT)**:
下载 `vosk-model-small-cn-0.22` 并解压到项目根目录。
* [下载地址 (Vosk Models)](https://alphacephei.com/vosk/models)


* **Coqui TTS 模型**:
服务端代码首次运行时会自动下载 `tts_models/zh-CN/baker/tacotron2-DDC-GST` 模型。

## ⚙️ 配置指南

在运行之前，请修改 `客户端.py` 中的配置区以匹配您的环境：

```python
# 客户端.py

# Dify 配置
DIFY_URL = "http://YOUR_DIFY_IP/v1/chat-messages"
DIFY_API_KEY = "app-xxxxxxxxxxxxxxxx"

# TTS 服务器地址 (确保 IP 与运行服务端的机器一致)
TTS_SERVER_WS = "ws://127.0.0.1:8000/ws/tts" 

```

## 🚀 快速开始

### 第一步：启动 TTS 服务端

在一个终端窗口中运行 TTS 服务。

> 注意：如果您没有重命名 `服务端.py`，请将下方的 `main` 替换为 `服务端代码具体名称(不带.py)`。

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

```

*等待终端显示 `Application startup complete.` 且没有报错。首次运行需要下载模型，耗时较长。*

### 第二步：启动语音客户端

打开一个新的终端窗口，运行客户端代码：

```bash
python 客户端.py

```

### 第三步：开始对话

1. 程序启动后，会列出当前的音频设备（麦克风和扬声器）。
2. 输入对应的 **数字索引** 选择设备。
3. 选择 **模式 1 (语音对话模式)**。
4. 对着麦克风说话即可与 Dify 智能体进行通话。

## ⚠️ 常见问题 (Troubleshooting)

1. **TTS 连接失败**:
* 检查 `客户端.py` 中的 `TTS_SERVER_WS` IP 地址是否正确。如果客户端和服务端在同一台电脑，请使用 `127.0.0.1` 或 `localhost`。如果在局域网不同电脑，请使用服务端的局域网 IP (如 `192.168.x.x`)。


2. **Sounddevice 报错**:
* 确保已安装 `PortAudio` 库（Windows 通常自动安装，Linux 需 `sudo apt-get install libportaudio2`）。


3. **Vosk 模型未找到**:
* 确保解压后的文件夹名称与代码中的 `VOSK_MODEL_PATH` 一致，且位于 `客户端.py` 同级目录下。



## 📝 License

[MIT License](https://www.google.com/search?q=LICENSE)
