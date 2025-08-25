import asyncio
from typing import Any, Dict, Optional
from contextlib import suppress

from src.core.amaidesu_core import AmaidesuCore
from src.core.plugin_manager import BasePlugin
from .mcp.client import MCPClient
from .agent.runner import AgentRunner
from .agent.agent import MaicraftAgent
from .config import load_config_from_dict
from .agent.mai_agent import MaiAgent


class MaicraftPlugin(BasePlugin):
    """
    Maicraft 插件, 用于连接到 MCP 服务器, 并启动自主代理循环
    """

    def __init__(self, core: AmaidesuCore, plugin_config: Dict[str, Any]):
        super().__init__(core, plugin_config)
        self.mcp_client: Optional[MCPClient] = None
        self.connected = False
        self.agent: Optional[MaicraftAgent | MaiAgent] = None
        self._agent_cfg: Dict[str, Any] = self.plugin_config.get("agent", {})
        self._agent_runner: Optional[AgentRunner] = None

    async def setup(self):
        """初始化插件"""
        # 初始化 MCP client
        mcp_config = self.plugin_config.get("mcp", {})
        self.logger.debug(f"[插件初始化] MCP配置: {mcp_config}")
        self.mcp_client = MCPClient(mcp_config)
        self.logger.debug("[插件初始化] MCP客户端已创建")

        # 尝试连接到 MCP 服务器
        self.logger.info("[插件初始化] 尝试连接到 MCP 服务器")
        try:
            self.connected = await self.mcp_client.connect()
        except Exception as e:
            self.logger.error(f"[插件初始化] 连接MCP服务器异常: {e}")
            self.connected = False

        if self.connected:
            self.logger.info("[插件初始化] 成功连接到 MCP 服务器")

            # 加载配置
            try:
                self.config = load_config_from_dict(self.plugin_config)
                self.logger.info("[插件初始化] 配置加载成功")
            except Exception as e:
                self.logger.error(f"[插件初始化] 配置加载失败: {e}")
                raise
            
            
            # 初始化 Agent
            try:
                self.logger.info(f"[插件初始化] Agent模式: {self.config.agent_mode.mode}")
                if self.config.agent_mode.mode == "mai_agent":
                    self.agent = MaiAgent(self.config, self.mcp_client)
                    await self.agent.initialize()
                    
                    await asyncio.sleep(2)
                    #等待2秒

                    self.logger.info("[插件初始化] 启动 Agent 主循环")
                    asyncio.create_task(self.agent.run_plan_loop())
                    asyncio.create_task(self.agent.run_execute_loop())
                    
                else:
                    self.agent = MaicraftAgent(self.config, self.mcp_client)
                    self._agent_runner = AgentRunner(
                        core=self.core,
                        mcp_client=self.mcp_client,
                        agent=self.agent,
                        agent_cfg=self._agent_cfg,
                    )
                    
                # await self.agent.initialize()
                self.logger.info("[插件初始化] Agent初始化成功")
            except Exception as e:
                self.logger.error(f"[插件初始化] Agent初始化失败: {e}")
                raise

            # 初始化 AgentRunner


            # 注册消息处理器 → 转发给 AgentRunner
            self.logger.debug("[插件初始化] 注册websocket消息处理器 (转发Agent)")
            self.core.register_websocket_handler(
                "*",
                lambda message: asyncio.create_task(self._agent_runner.handle_message(message)),  # type: ignore[attr-defined]
            )
            self.logger.debug("[插件初始化] 消息处理器注册完成")

            # 启动自主代理循环
            agent_enabled = bool(self._agent_cfg.get("enabled", True))
            self.logger.info(f"[插件初始化] 自主代理配置: 启用={agent_enabled}")

            if self.config.agent_mode.mode == "mai_agent":
                pass
            else:
                if agent_enabled and self._agent_runner:
                    self.logger.info("[插件初始化] 启动 Agent 自主代理循环")
                    await self._agent_runner.start()
                    self.logger.debug("[插件初始化] 自主代理任务已创建")
                else:
                    self.logger.info("[插件初始化] 自主代理被禁用，不启动代理循环")

            self.logger.info("[插件初始化] Agent 插件初始化完成")
        else:
            self.logger.warning("[插件初始化] 连接到 MCP 服务器失败，插件功能受限")

    async def cleanup(self):
        """清理插件资源"""
        self.logger.info("[插件清理] 开始清理 Agent 插件资源")

        # 停止自主代理
        if self._agent_runner:
            self.logger.info("[插件清理] 停止自主代理循环")
            with suppress(Exception):
                await self._agent_runner.stop()
            self.logger.info("[插件清理] 自主代理循环已停止")
        else:
            self.logger.debug("[插件清理] 无需停止自主代理循环（未运行）")

        # 断开MCP连接
        if self.mcp_client and self.connected:
            self.logger.info("[插件清理] 断开与 MCP 服务器的连接")
            try:
                await self.mcp_client.disconnect()
                self.logger.info("[插件清理] MCP 连接已断开")
            except Exception as e:
                self.logger.error(f"[插件清理] 断开MCP连接时异常: {e}")
        else:
            self.logger.debug("[插件清理] 无需断开MCP连接（未连接）")

        self.logger.info("[插件清理] Agent 插件清理完成")

    # 插件入口点仍在本文件底部


plugin_entrypoint = MaicraftPlugin
