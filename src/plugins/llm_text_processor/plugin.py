import asyncio
import logging
import os
import sys
from typing import Dict, Any, Optional

# --- Dependency Check & TOML --- 
try:
    from openai import AsyncOpenAI, OpenAIError, APIConnectionError, RateLimitError, APIStatusError
except ImportError:
    print("依赖缺失: 请运行 'pip install openai' 来使用 LLM 文本处理器插件。", file=sys.stderr)
    AsyncOpenAI = None # type: ignore
    OpenAIError = APIConnectionError = RateLimitError = APIStatusError = Exception # type: ignore

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import toml as tomllib
    except ImportError:
        print("依赖缺失: 请运行 'pip install toml' 来加载 LLM 文本处理器插件配置。", file=sys.stderr)
        tomllib = None

# --- VUP-NEXT Core Imports ---
from core.plugin_manager import BasePlugin
from core.vup_next_core import VupNextCore

logger = logging.getLogger(__name__)

# --- Plugin Configuration Loading ---
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.toml")

def load_plugin_config() -> Dict[str, Any]:
    """Loads the plugin's specific config.toml file."""
    if tomllib is None:
        logger.error("TOML library not available, cannot load LLMTextProcessor plugin config.")
        return {}
    try:
        with open(_CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
            logger.info(f"成功加载 LLM 文本处理器配置文件: {_CONFIG_FILE}")
            return config
    except FileNotFoundError:
        logger.error(f"LLM 文本处理器配置文件未找到: {_CONFIG_FILE}。将使用默认值或禁用功能。")
    except tomllib.TOMLDecodeError as e:
        logger.error(f"LLM 文本处理器配置文件 '{_CONFIG_FILE}' 格式无效: {e}。将使用默认值或禁用功能。")
    except Exception as e:
        logger.error(f"加载 LLM 文本处理器配置文件 '{_CONFIG_FILE}' 时发生未知错误: {e}", exc_info=True)
    return {}

class LLMTextProcessorPlugin(BasePlugin):
    """提供文本清理和 STT 修正功能的统一 LLM 插件。"""
    _is_vup_next_plugin: bool = True # Plugin marker

    def __init__(self, core: VupNextCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.config = load_plugin_config()
        self.enabled = True

        # --- Dependency Check ---
        if AsyncOpenAI is None or tomllib is None:
            self.logger.error("缺少核心依赖 (openai, toml)，LLM 文本处理器插件禁用。")
            self.enabled = False
            return

        # --- Config Validation ---
        self.base_url = self.config.get('base_url')
        self.api_key = self.config.get('api_key', '-') # Default to '-' if not set
        self.model_name = self.config.get('model_name')
        self.timeout = self.config.get('timeout', 30)
        self.max_retries = self.config.get('max_retries', 2)
        self.cleanup_prompt = self.config.get('cleanup_prompt_template')
        self.correction_prompt = self.config.get('correction_prompt_template')

        if not self.base_url or not self.model_name:
            self.logger.error("LLM 配置不完整 (缺少 base_url 或 model_name)，插件禁用。")
            self.enabled = False
            return
        if not self.cleanup_prompt:
             self.logger.warning("未找到 cleanup_prompt_template，文本清理功能将不可用。")
        if not self.correction_prompt:
             self.logger.warning("未找到 correction_prompt_template，STT 修正功能将不可用。")

        # --- Initialize AsyncOpenAI Client ---
        try:
            self.client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key if self.api_key != '-' else None, # Pass None if api_key is '-'
                timeout=self.timeout,
                max_retries=0 # We handle retries manually in _call_llm
            )
            self.logger.info(f"LLM 客户端初始化成功 (URL: {self.base_url}, Model: {self.model_name})")
        except Exception as e:
            self.logger.error(f"初始化 LLM 客户端失败: {e}", exc_info=True)
            self.enabled = False
            self.client = None

    async def setup(self):
        """Register the plugin instance as both services."""
        await super().setup()
        if not self.enabled:
            self.logger.warning("LLM 文本处理器插件未启用，不注册服务。")
            return
        
        # Register this instance for both service names
        self.core.register_service("text_cleanup", self)
        self.core.register_service("stt_correction", self)
        self.logger.info("LLM 文本处理器插件已注册为 'text_cleanup' 和 'stt_correction' 服务。")

    async def cleanup(self):
        """Clean up resources, though AsyncOpenAI client might not need explicit cleanup."""
        self.logger.info("LLM 文本处理器插件清理...")
        # AsyncOpenAI client might handle closing internally, but good practice if needed
        if hasattr(self.client, 'close') and asyncio.iscoroutinefunction(self.client.close):
             try:
                 await self.client.close()
                 self.logger.debug("AsyncOpenAI client closed.")
             except Exception as e:
                  self.logger.warning(f"关闭 AsyncOpenAI client 时出错: {e}")
        await super().cleanup()

    async def clean_text(self, text: str) -> Optional[str]:
        """Cleans the input text using the cleanup prompt."""
        if not self.enabled or not self.cleanup_prompt:
            self.logger.warning("文本清理功能未启用或缺少 Prompt。")
            return None
        
        prompt = self.cleanup_prompt.format(text=text)
        self.logger.debug(f"请求清理文本: '{text[:50]}...'")
        cleaned = await self._call_llm(prompt)
        if cleaned:
             self.logger.info(f"清理结果: '{cleaned[:50]}...'")
        return cleaned

    async def correct_text(self, text: str) -> Optional[str]:
        """Corrects the input STT result using the correction prompt."""
        if not self.enabled or not self.correction_prompt:
            self.logger.warning("STT 修正功能未启用或缺少 Prompt。")
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
                    temperature=0.1, # Low temperature for deterministic cleanup/correction
                    # max_tokens= # Optional: Set max tokens if needed
                )
                result = response.choices[0].message.content
                if result:
                     return result.strip()
                else:
                     self.logger.warning("LLM 返回了空结果。")
                     return None # Return None for empty result
            except APIConnectionError as e:
                retries += 1
                self.logger.warning(f"LLM 连接错误 (尝试 {retries}/{self.max_retries}): {e}")
                if retries > self.max_retries:
                    self.logger.error("LLM 连接错误达到最大重试次数。")
                    return None
                await asyncio.sleep(1 * retries) # Exponential backoff
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
        return None # Should not be reached if retries handle correctly

# --- Plugin Entry Point ---
plugin_entrypoint = LLMTextProcessorPlugin 