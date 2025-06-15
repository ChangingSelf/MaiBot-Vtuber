import asyncio
import os
import sys
from typing import Dict, Any, Optional
import traceback

# --- Dependency Check & TOML ---
try:
    from openai import AsyncOpenAI, OpenAIError, APIConnectionError, RateLimitError, APIStatusError
except ImportError:
    print("依赖缺失: 请运行 'pip install openai' 来使用 LLM 文本处理器插件。", file=sys.stderr)
    AsyncOpenAI = None  # type: ignore
    OpenAIError = APIConnectionError = RateLimitError = APIStatusError = Exception  # type: ignore

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib
    except ImportError:
        print("依赖缺失: 请运行 'pip install toml' 来加载 LLM 文本处理器插件配置。", file=sys.stderr)
        tomllib = None

# --- Amaidesu Core Imports ---
from src.core.plugin_manager import BasePlugin
from src.core.amaidesu_core import AmaidesuCore


class LLMTextProcessorPlugin(BasePlugin):
    """
    Plugin for processing text using LLM (Language Model).
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = self.plugin_config

        # --- Read configuration values from self.config ---
        self.base_url = self.config.get("base_url")
        self.api_key = self.config.get("api_key")
        self.model_name = self.config.get("model_name", "default-model")  # Provide a default
        self.timeout = self.config.get("timeout", 10)  # Provide a default
        self.max_retries = self.config.get("max_retries", 2)  # Provide a default
        self.cleanup_prompt = self.config.get("cleanup_prompt_template", "")  # Load cleanup prompt
        self.correction_prompt = self.config.get("correction_prompt_template", "")  # Load correction prompt

        # --- Validate essential config ---
        if not self.base_url:
            self.logger.error("Missing 'base_url' in llm_text_processor config. Plugin disabled.")
            return
        if not self.api_key:
            self.logger.warning("Missing 'api_key' in llm_text_processor config. Set to '-' if no key is needed.")
            # Decide if this is an error or just a warning depending on API requirements
            # If API always needs a key (even dummy), uncomment below
            # self.enabled = False
            # return

        # --- Initialize OpenAI Client ---
        self.client: Optional[AsyncOpenAI] = None  # Ensure client is initialized to None
        try:
            self.client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key if self.api_key != "-" else None,  # Pass None if api_key is '-'
                timeout=self.timeout,
                max_retries=0,  # We handle retries manually in _call_llm
            )
            self.logger.info(f"LLM 客户端初始化成功 (URL: {self.base_url}, Model: {self.model_name})")
        except Exception as e:
            self.logger.error(f"初始化 LLM 客户端失败: {e}", exc_info=True)
            # No need to set self.client to None here, it's already None if init fails

    async def setup(self):
        """Register the plugin instance as both services."""
        await super().setup()

        # Register this instance for both service names
        self.core.register_service("text_cleanup", self)
        self.core.register_service("stt_correction", self)
        self.logger.info("LLM 文本处理器插件已注册为 'text_cleanup' 和 'stt_correction' 服务。")

    async def cleanup(self):
        """Clean up resources, though AsyncOpenAI client might not need explicit cleanup."""
        self.logger.info("LLM 文本处理器插件清理...")
        # AsyncOpenAI client might handle closing internally, but good practice if needed
        if hasattr(self.client, "close") and asyncio.iscoroutinefunction(self.client.close):
            try:
                await self.client.close()
                self.logger.debug("AsyncOpenAI client closed.")
            except Exception as e:
                self.logger.warning(f"关闭 AsyncOpenAI client 时出错: {e}")
        await super().cleanup()

    async def clean_text(self, text: str) -> Optional[str]:
        """Cleans the input text using the cleanup prompt."""
        if not self.cleanup_prompt:
            self.logger.debug("文本清理功能缺少 Prompt，跳过。")
            return None

        prompt = self.cleanup_prompt.format(text=text)
        self.logger.debug(f"请求清理文本: '{text[:50]}...'")
        cleaned = await self._call_llm(prompt)
        if cleaned:
            self.logger.info(f"清理结果: '{cleaned[:50]}...'")
        return cleaned

    async def correct_text(self, text: str) -> Optional[str]:
        """Corrects the input STT result using the correction prompt."""
        if not self.correction_prompt:
            self.logger.debug("STT 修正功能缺少 Prompt，跳过。")
            return None

        prompt = self.correction_prompt.format(text=text)
        self.logger.debug(f"请求修正 STT: '{text[:50]}...'")
        corrected = await self._call_llm(prompt)
        if corrected:
            self.logger.info(f"修正结果: '{corrected[:50]}...'")
        return corrected

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Internal method to call the LLM with retry logic."""
        if not self.client:
            return None

        retries = 0
        while retries <= self.max_retries:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  # Low temperature for deterministic cleanup/correction
                    # max_tokens= # Optional: Set max tokens if needed
                )
                result = response.choices[0].message.content
                if result:
                    return result.strip()
                else:
                    self.logger.warning("LLM 返回了空结果。")
                    return None  # Return None for empty result
            except APIConnectionError as e:
                retries += 1
                self.logger.warning(f"LLM 连接错误 (尝试 {retries}/{self.max_retries}): {e}")
                if retries > self.max_retries:
                    self.logger.error(f"LLM 连接错误达到最大重试次数。{traceback.format_exc()}")
                    return None
                await asyncio.sleep(1 * retries)  # Exponential backoff
            except RateLimitError as e:
                self.logger.error(f"LLM 速率限制错误: {e}。请检查您的账户配额。")
                return None
            except APIStatusError as e:
                self.logger.error(f"LLM API 状态错误 (代码: {e.status_code}): {e.message}")
                return None
            except OpenAIError as e:
                self.logger.error(f"LLM 调用时发生未知 OpenAI 错误: {e}", exc_info=True)
                return None
            except Exception as e:
                self.logger.error(f"调用 LLM 时发生意外错误: {e}", exc_info=True)
                return None
        return None  # Should not be reached if retries handle correctly


# --- Plugin Entry Point ---
plugin_entrypoint = LLMTextProcessorPlugin
