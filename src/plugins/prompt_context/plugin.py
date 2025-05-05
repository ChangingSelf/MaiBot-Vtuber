# src/plugins/prompt_context/plugin.py

# import logging
import tomllib  # 使用 tomllib (Python 3.11+) 或 toml
from typing import Any, Dict, List, Optional, TypedDict
import os
import asyncio  # 引入 asyncio

# Use absolute imports relative to the src directory
from core.plugin_manager import BasePlugin
from core.amaidesu_core import AmaidesuCore
from src.utils.logger import get_logger

logger = get_logger("PromptContextPlugin")


# --- Helper Function ---
def load_plugin_config() -> Dict[str, Any]:
    """Loads the plugin's configuration from config.toml."""
    config_path = os.path.join(os.path.dirname(__file__), "config.toml")
    try:
        with open(config_path, "rb") as f:
            # Python 3.11+ use tomllib
            if hasattr(tomllib, "load"):
                return tomllib.load(f)
            else:
                # Fallback for older Python versions (requires toml package)
                try:
                    import toml

                    with open(config_path, "r", encoding="utf-8") as rf:
                        return toml.load(rf)
                except ImportError:
                    logger.error("Toml package not found. Please install it (`pip install toml`) for Python < 3.11.")
                    return {}
                except FileNotFoundError:
                    logger.warning(f"Configuration file not found at {config_path}")
                    return {}
    except Exception as e:
        logger.error(f"Error loading configuration from {config_path}: {e}", exc_info=True)
        return {}


# --- Type Definition for Context Provider Data ---
class ContextProviderData(TypedDict):
    provider_name: str
    context_info: str
    priority: int
    tags: List[str]
    enabled: bool


# --- Plugin Class ---
class PromptContextPlugin(BasePlugin):
    """
    Manages and aggregates contextual information to be appended to prompts.
    Other plugins can register context providers, and message-sending plugins
    can retrieve the aggregated context.
    """

    _is_amaidesu_plugin: bool = True

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.logger = logger
        self.config = plugin_config.get("prompt_context", {})
        self.formatting_config = plugin_config.get("formatting", {})
        self.limits_config = plugin_config.get("limits", {})

        # --- Store for Context Providers ---
        # Key: provider_name, Value: ContextProviderData
        self._context_providers: Dict[str, ContextProviderData] = {}

        # --- Configuration Values ---
        self.enabled = self.config.get("enabled", True)
        self.separator = self.formatting_config.get("separator", "\\n").replace("\\n", "\n")
        self.add_provider_title = self.formatting_config.get("add_provider_title", False)
        self.title_separator = self.formatting_config.get("title_separator", ": ")
        self.default_max_length = self.limits_config.get("default_max_length", 1000)
        self.default_priority = self.limits_config.get("default_priority", 100)

        if not self.enabled:
            self.logger.warning("PromptContextPlugin is disabled in the configuration.")

    async def setup(self):
        await super().setup()
        if not self.enabled:
            return
        # Register self as a service
        self.core.register_service("prompt_context", self)
        self.logger.info("PromptContextPlugin service registered.")

    async def cleanup(self):
        # No specific resources to clean up other than unregistering service?
        # Consider if unregistering is needed or handled by Core/PluginManager
        self.logger.info("PromptContextPlugin cleaned up.")
        await super().cleanup()

    # --- Public API for other plugins ---

    def register_context_provider(
        self,
        provider_name: str,
        context_info: Any,
        priority: Optional[int] = None,
        tags: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> bool:
        """
        Registers or updates a context provider.
        context_info can be a string or an async function returning a string.

        Args:
            provider_name: A unique identifier for the provider (e.g., "vts_actions").
            context_info: The actual contextual string to potentially add to prompts.
            priority: Lower numbers mean higher priority (appear earlier). Uses default if None.
            tags: A list of tags for filtering (e.g., ["action", "vts"]).
            enabled: Whether this provider's context is currently active.

        Returns:
            True if registration/update was successful, False otherwise.
        """
        if not self.enabled:
            self.logger.warning(f"Cannot register '{provider_name}', PromptContextPlugin is disabled.")
            return False
        if not provider_name:
            self.logger.error("Provider name cannot be empty.")
            return False

        resolved_priority = priority if priority is not None else self.default_priority
        resolved_tags = tags if tags is not None else []

        provider_data: ContextProviderData = {
            "provider_name": provider_name,
            "context_info": context_info,
            "priority": resolved_priority,
            "tags": resolved_tags,
            "enabled": enabled,
        }
        self._context_providers[provider_name] = provider_data
        self.logger.info(
            f"Context provider '{provider_name}' registered/updated (Priority: {resolved_priority}, Enabled: {enabled})."
        )

        # Modified debug log to handle callables
        if callable(context_info):
            context_repr = f"<callable: {getattr(context_info, '__name__', repr(context_info))}>"
        elif isinstance(context_info, str):
            context_repr = f"'{context_info[:100]}...'"
        else:
            context_repr = repr(context_info)
        self.logger.debug(f"'{provider_name}' context: {context_repr}")

        return True

    def update_context_info(
        self, provider_name: str, context_info: Optional[str] = None, enabled: Optional[bool] = None
    ) -> bool:
        """
        Updates specific fields of an existing context provider.

        Args:
            provider_name: The identifier of the provider to update.
            context_info: The new context string (if updating).
            enabled: The new enabled status (if updating).

        Returns:
            True if update was successful, False if provider not found or no changes specified.
        """
        if not self.enabled:
            self.logger.warning(f"Cannot update '{provider_name}', PromptContextPlugin is disabled.")
            return False
        if provider_name not in self._context_providers:
            self.logger.warning(f"Cannot update context for non-existent provider: '{provider_name}'")
            return False
        if context_info is None and enabled is None:
            self.logger.warning(f"No update specified for provider: '{provider_name}'")
            return False

        provider = self._context_providers[provider_name]
        updated = False
        if context_info is not None:
            provider["context_info"] = context_info
            self.logger.info(f"Context info updated for '{provider_name}'.")
            self.logger.debug(f"New context: '{context_info[:100]}...'")
            updated = True
        if enabled is not None:
            provider["enabled"] = enabled
            self.logger.info(f"Enabled status for '{provider_name}' set to {enabled}.")
            updated = True

        return updated

    def unregister_context_provider(self, provider_name: str) -> bool:
        """Removes a context provider."""
        if provider_name in self._context_providers:
            del self._context_providers[provider_name]
            self.logger.info(f"Context provider '{provider_name}' unregistered.")
            return True
        else:
            self.logger.warning(f"Attempted to unregister non-existent provider: '{provider_name}'")
            return False

    async def get_formatted_context(self, tags: Optional[List[str]] = None, max_length: Optional[int] = None) -> str:
        """
        Retrieves and formats the aggregated context from enabled providers,
        sorted by priority and optionally filtered by tags.
        Handles both string and async callable context_info.

        Args:
            tags: If provided, only include providers matching ALL these tags.
            max_length: Overrides the default maximum length for the returned string.

        Returns:
            A single string containing the formatted context, potentially truncated.
        """
        if not self.enabled:
            return ""

        target_max_length = max_length if max_length is not None else self.default_max_length

        # 1. Filter providers by enabled status and tags
        eligible_providers = []
        for provider in self._context_providers.values():
            if not provider["enabled"]:
                continue
            if tags:  # Check if all requested tags are present in the provider's tags
                if not all(tag in provider["tags"] for tag in tags):
                    continue
            eligible_providers.append(provider)

        # 2. Sort by priority (ascending) then by name (alphabetical for stability)
        eligible_providers.sort(key=lambda p: (p["priority"], p["provider_name"]))
        self.logger.debug(f"Eligible providers for context: {[p['provider_name'] for p in eligible_providers]}")

        # 3. Format and combine context strings
        context_parts: List[str] = []
        current_length = 0
        separator_len = len(self.separator)

        for provider in eligible_providers:
            context_value: Optional[str] = None
            provider_name = provider["provider_name"]
            raw_context_info = provider["context_info"]

            # --- 获取上下文值 (处理 callable) ---
            if callable(raw_context_info):
                self.logger.debug(f"Calling async provider: {provider_name}")
                try:
                    # 检查是否是协程函数 (更健壮的方式)
                    if asyncio.iscoroutinefunction(raw_context_info):
                        context_value = await raw_context_info()
                    else:  # 如果不是 async def 但可调用 (虽然我们期望是 async)
                        # 可以在这里决定是否支持同步 callable，或者直接报错/跳过
                        self.logger.warning(
                            f"Context provider '{provider_name}' is callable but not an async function. Skipping."
                        )
                        continue
                except Exception as e:
                    self.logger.error(f"Error calling context provider '{provider_name}': {e}", exc_info=True)
                    # 出错时可以跳过这个 provider
                    continue
            elif isinstance(raw_context_info, str):
                context_value = raw_context_info
            else:
                self.logger.warning(
                    f"Provider '{provider_name}' has unexpected context_info type: {type(raw_context_info)}. Skipping."
                )
                continue

            # --- 使用获取到的 context_value 进行后续处理 ---
            if not context_value:  # Skip empty context (after potentially calling callable)
                self.logger.debug(f"Provider '{provider_name}' returned empty context. Skipping.")
                continue

            prefix = ""
            if self.add_provider_title:
                prefix = f"{provider_name}{self.title_separator}"

            full_part = prefix + context_value
            part_len = len(full_part)

            # Check length before adding (including separator if not the first part)
            projected_length = current_length + part_len
            if context_parts:  # If not the first part, account for separator
                projected_length += separator_len

            if projected_length <= target_max_length:
                context_parts.append(full_part)
                current_length = projected_length
            else:
                # Try to add a truncated part if possible
                remaining_space = target_max_length - current_length
                if context_parts:  # Account for separator space
                    remaining_space -= separator_len

                if remaining_space > 3:  # Need space for "..."
                    truncated_part = full_part[: remaining_space - 3] + "..."
                    context_parts.append(truncated_part)
                    self.logger.warning(f"Context from '{provider_name}' was truncated due to max_length.")
                else:
                    # Not enough space even for truncated part, stop adding
                    self.logger.warning(f"Context from '{provider_name}' skipped entirely due to max_length.")
                    break  # Stop processing further providers

        self.logger.debug(f"Final context parts before join: {context_parts}")
        return self.separator.join(context_parts)


# --- Plugin Entry Point ---
plugin_entrypoint = PromptContextPlugin

# --- Load config globally for the plugin instance ---
# (PluginManager usually handles passing config, but this ensures it's loaded once)
# global_plugin_config = load_plugin_config() # Alternative if PM doesn't pass it
