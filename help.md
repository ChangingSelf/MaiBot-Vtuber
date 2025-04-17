# VUP-NEXT 帮助文档

欢迎使用 VUP-NEXT！这是一个旨在通过插件化架构，提供与 MaiCore (MMC) 等核心进行交互的虚拟主播辅助工具。它集成了语音识别 (STT)、语音合成 (TTS)、视觉模型交互、外部设备控制等多种功能。

## 目录

*   [安装与设置](#安装与设置)
*   [项目配置](#项目配置)
*   [运行程序](#运行程序)
*   [插件概览](#插件概览)
*   [常见问题](#常见问题)

## 安装与设置

1.  **环境要求:**
    *   Python 3.9 或更高版本 (推荐 3.11+ 以获得内建 `tomllib` 支持)。
    *   部分插件可能需要特定的外部软件或服务（例如：VTube Studio, DG-LAB HTTP API 服务）。

2.  **安装依赖:**
    项目根目录下提供了 `requirements.txt` 文件，包含了所有必要的 Python 库。使用以下命令安装：
    ```bash
    pip install -r requirements.txt
    ```
    *注意：* `torch` 库可能需要根据你的操作系统和 CUDA 版本进行特定安装，请参考 [PyTorch 官网](https://pytorch.org/) 的说明。如果不需要 STT 的 VAD 功能，可以暂时跳过或移除 `torch`。

3.  **API 密钥与认证:**
    *   许多插件需要配置 API 密钥才能工作（例如 OpenAI 兼容接口、讯飞、Bilibili 等）。
    *   请根据各插件目录 (`src/plugins/<plugin_name>/config.toml`) 中的说明填写必要的密钥和认证信息。
    *   对于 VTube Studio 插件，首次运行时需要在 VTube Studio 应用内授权插件连接。

## 项目配置

VUP-NEXT 采用分层配置：

1.  **根配置文件 (`config.toml`):** 位于项目根目录。
    *   主要用于启用或禁用各个插件。
2.  **插件配置文件 (`src/plugins/<plugin_name>/config.toml`):** 每个插件目录下都有自己的配置文件，用于控制该插件的具体行为。
    *   例如 `src/plugins/tts/config.toml` 控制 TTS 的语音、设备等。
    *   `src/plugins/stt/config.toml` 控制 STT 的讯飞 API 密钥、VAD 参数等。
    *   `src/plugins/read_pingmu/config.toml` 控制屏幕监控的 API Key、截图频率等。
    *   请务必检查并修改你需要使用的插件的配置文件，特别是 API 密钥和 URL 等。

## 运行程序

在项目根目录下，运行主程序：

```bash
python src/main.py
```

程序启动后会加载启用的插件，并开始执行它们的功能（例如：监听控制台输入、连接 VTS、开始屏幕监控等）。

## 插件概览

以下是当前项目包含的主要插件及其功能：

*   **`console_input`**: 提供一个控制台界面，允许你手动输入文本并发送给 MaiCore。使用了 `prompt_toolkit` (如果可用) 以获得更好的输入体验。
*   **`tts`**: 负责文本转语音。
    *   使用 `edge-tts` 进行语音合成。
    *   可以配置输出语音和音频设备。
    *   依赖 `text_cleanup` 服务（由 `llm_text_processor` 提供）进行文本预处理。
    *   调用 `subtitle_service`（由 `subtitle` 提供）来记录语音信息。
*   **`subtitle`**: 在屏幕上显示实时字幕。
    *   使用 `tkinter` 创建一个置顶、可拖动的窗口。
    *   接收来自 `tts` 插件的文本和时长信息，并更新字幕显示。
*   **`stt`**: 负责语音转文本。
    *   使用 `torch` 和 `silero-vad` 进行语音活动检测 (VAD)。
    *   使用 `aiohttp` 与讯飞实时语音听写 WebSocket API 进行通信。
    *   可选依赖 `stt_correction` 服务（由 `llm_text_processor` 提供）对识别结果进行修正。
*   **`vtube_studio`**: 连接并控制 VTube Studio。
    *   使用 `pyvts` 库进行通信。
    *   提供 `vts_control` 服务，允许其他插件触发热键 (`trigger_hotkey`)。
    *   向 `prompt_context` 服务注册可用的热键列表和使用说明。
*   **`prompt_context`**: 管理和聚合提供给 LLM 的上下文信息。
    *   提供 `prompt_context` 服务。
    *   允许其他插件注册动态或静态的上下文信息，并按优先级组合。
*   **`llm_text_processor`**: 提供基于 LLM 的文本处理服务。
    *   使用 `openai` 库与 OpenAI 兼容的 API (如 Dashscope, SiliconFlow 等) 交互。
    *   提供 `text_cleanup` 服务（用于清理文本）。
    *   提供 `stt_correction` 服务（用于修正 STT 结果）。
*   **`command_processor`**: 处理嵌入在文本中的命令。
    *   监听来自 MaiCore 的消息。
    *   查找特定格式的命令标签（例如 `%{vts_trigger_hotkey:id}%`）。
    *   调用相应的服务（如 `vts_control`）执行命令。
    *   从原始文本中移除命令标签。
*   **`dg-lab-do` (原 `ElectricityMonitorPlugin`)**: 监控文本并控制 DG-LAB 设备。
    *   监听来自 MaiCore 的消息。
    *   检测特定关键词（如 "电"）。
    *   如果检测到，通过配置的 HTTP API 地址发送命令设置设备强度和波形。
    *   在延迟后自动将强度归零。
    *   向 `prompt_context` 服务注册关于关键词后果的警告信息。
*   **`read_pingmu` (原 `ScreenMonitorPlugin`)**: 监控屏幕内容。
    *   使用 `mss` 定期截取屏幕。
    *   使用 `openai` 兼容接口调用视觉语言模型 (VL Model) 获取屏幕描述。
    *   将最新的屏幕描述作为动态上下文注册到 `prompt_context` 服务。
    *   **注意：此插件存在隐私风险和 API 成本，请谨慎使用并确保配置正确。**
*   **`bili_danmaku`**: 从指定的 Bilibili 直播间获取弹幕。
    *   通过轮询 Bilibili API 实现。
    *   将获取到的新弹幕作为消息发送给 MaiCore。

## 常见问题

*   **插件未加载/禁用:**
    *   检查根目录 `config.toml` 中对应插件是否设置为 `true`。
    *   检查该插件所需的依赖库是否已正确安装 (参考 `requirements.txt`)。
    *   检查该插件目录下的 `config.toml` 配置是否完整且正确（特别是 API Key、URL 等）。
    *   查看启动日志，通常会有插件加载失败或禁用的原因说明。
*   **VTube Studio 连接失败:**
    *   确保 VTube Studio 正在运行。
    *   确保 VTube Studio 的 API 功能已开启。
    *   首次连接时，需要在 VTube Studio 弹出的窗口中允许插件连接。
    *   检查 `vtube_studio/config.toml` 中的 `vts_host` 和 `vts_port` 配置是否正确。
*   **控制台输入被日志打断:**
    *   这是使用原生 `sys.stdin` 时的限制。确保已安装 `prompt_toolkit` (`pip install prompt_toolkit`)，插件会自动尝试使用它来改善输入体验。

---

希望这份文档对你有所帮助！