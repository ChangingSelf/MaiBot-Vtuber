"""
环境信息更新器
使用新的拆分后的查询工具来更新Minecraft环境信息
"""

import asyncio
import threading
import time
import traceback
from typing import Callable, Optional, Dict, Any
from datetime import datetime
from src.utils.logger import get_logger
from .environment import global_environment
import json

class EnvironmentUpdater:
    """环境信息定期更新器"""
    
    def __init__(self, 
                 agent=None,
                 update_interval: int = 2,
                 auto_start: bool = False):
        """
        初始化环境更新器
        
        Args:
            agent: MaicraftAgent实例，用于调用查询工具
            update_interval: 更新间隔（秒），默认2秒
            auto_start: 是否自动开始更新，默认False
        """
        self.agent = agent
        self.update_interval = update_interval
        self.logger = get_logger("EnvironmentUpdater")
        
        # 更新状态
        self.is_running = False
        self.is_paused = False
        
        # 线程和任务控制
        self._update_thread: Optional[threading.Thread] = None
        self._update_task: Optional[asyncio.Task] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        
        # 统计信息
        self.update_count = 0
        self.last_update_time: Optional[datetime] = None
        self.last_update_duration = 0.0
        self.average_update_duration = 0.0
        self.total_update_duration = 0.0
        
        # 如果自动开始，则启动更新
        if auto_start:
            self.start()
    
    def start(self) -> bool:
        """启动环境更新器"""
        if self.is_running:
            self.logger.warning("[EnvironmentUpdater] 更新器已在运行中")
            return False
        
        try:
            self._stop_event.clear()
            self._pause_event.clear()
            self.is_running = True
            self.is_paused = False
            
            # 使用asyncio.create_task启动异步更新循环
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # 如果已有事件循环，直接创建任务
                self._update_task = loop.create_task(self._update_loop())
                self.logger.info(f"[EnvironmentUpdater] 在现有事件循环中启动成功，更新间隔: {self.update_interval}秒")
            except RuntimeError:
                # 如果没有运行中的事件循环，创建新的事件循环
                self._update_thread = threading.Thread(
                    target=self._run_async_loop,
                    name="EnvironmentUpdater",
                    daemon=True
                )
                self._update_thread.start()
                self.logger.info(f"[EnvironmentUpdater] 在新线程中启动成功，更新间隔: {self.update_interval}秒")
            
            return True
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 启动失败: {e}")
            self.is_running = False
            return False
    
    def stop(self) -> bool:
        """停止环境更新器"""
        if not self.is_running:
            self.logger.warning("[EnvironmentUpdater] 更新器未在运行")
            return False
        
        try:
            self.logger.info("[EnvironmentUpdater] 正在停止更新器...")
            self._stop_event.set()
            
            # 停止异步任务
            if self._update_task and not self._update_task.done():
                self._update_task.cancel()
                self.logger.info("[EnvironmentUpdater] 异步任务已取消")
            
            # 等待线程结束
            if self._update_thread and self._update_thread.is_alive():
                self._update_thread.join(timeout=10.0)
                if self._update_thread.is_alive():
                    self.logger.warning("[EnvironmentUpdater] 线程未能在10秒内结束")
            
            self.is_running = False
            self.is_paused = False
            self.logger.info("[EnvironmentUpdater] 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 停止失败: {e}")
            return False
    
    def pause(self) -> bool:
        """暂停环境更新"""
        if not self.is_running:
            self.logger.warning("[EnvironmentUpdater] 更新器未在运行")
            return False
        
        if self.is_paused:
            self.logger.warning("[EnvironmentUpdater] 更新器已暂停")
            return False
        
        try:
            self._pause_event.set()
            self.is_paused = True
            self.logger.info("[EnvironmentUpdater] 已暂停")
            return True
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 暂停失败: {e}")
            return False
    
    def resume(self) -> bool:
        """恢复环境更新"""
        if not self.is_running:
            self.logger.warning("[EnvironmentUpdater] 更新器未在运行")
            return False
        
        if not self.is_paused:
            self.logger.warning("[EnvironmentUpdater] 更新器未暂停")
            return False
        
        try:
            self._pause_event.clear()
            self.is_paused = False
            self.logger.info("[EnvironmentUpdater] 已恢复")
            return True
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 恢复失败: {e}")
            return False
    
    
    async def _update_loop(self):
        """更新循环的主逻辑（异步版本）"""
        self.logger.info(f"[EnvironmentUpdater] 异步更新循环已启动，间隔: {self.update_interval}秒")
        
        while not self._stop_event.is_set():
            try:
                # 检查是否暂停
                if self._pause_event.is_set():
                    await asyncio.sleep(0.1)  # 暂停时短暂休眠
                    continue
                
                # 执行更新
                start_time = time.time()
                await self._perform_update()
                update_duration = time.time() - start_time
                
                # 更新统计信息
                self._update_statistics(update_duration)
                
                # 等待下次更新
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"[EnvironmentUpdater] 更新循环异常: {e}")
                await asyncio.sleep(1)  # 出错时等待1秒再继续
        
        self.logger.info("[EnvironmentUpdater] 异步更新循环已结束")
    
    async def _perform_update(self):
        """执行单次环境更新（异步版本）"""
        try:
            if not self.agent:
                self.logger.error("[EnvironmentUpdater] Agent未设置，无法执行更新")
                return
            
            # 使用新的拆分后的查询工具获取环境数据
            environment_data = await self._gather_environment_data()
            
            if environment_data:
                # 更新全局环境信息
                try:
                    
                    global_environment.update_from_observation(environment_data)
                    self.logger.debug(f"[EnvironmentUpdater] 全局环境信息已更新，最后更新: {global_environment.last_update}")
                except Exception as e:
                    self.logger.error(f"[EnvironmentUpdater] 更新全局环境信息失败: {e}")
                    self.logger.error(traceback.format_exc())
                
                self.logger.debug(f"[EnvironmentUpdater] 环境更新完成")
            else:
                self.logger.warning("[EnvironmentUpdater] 环境更新未返回结果")
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 环境更新失败: {e}")
            raise

    async def _gather_environment_data(self) -> Optional[Dict[str, Any]]:
        """使用新的查询工具收集环境数据"""
        try:
            # 并行调用所有查询工具
            tasks = [
                self._call_query_game_state(),
                self._call_query_player_status(include_inventory=True),  # 默认包含物品栏信息
                self._call_query_recent_events(),
                self._call_query_surroundings("players"),
                self._call_query_surroundings("entities"),
                self._call_query_surroundings("blocks")
            ]
            
            # 等待所有查询完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 记录每个查询工具的结果类型，用于调试
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.warning(f"[EnvironmentUpdater] 查询工具 {i} 返回异常: {result}")
                elif isinstance(result, dict):
                    self.logger.debug(f"[EnvironmentUpdater] 查询工具 {i} 返回字典，ok={result.get('ok')}")
                else:
                    self.logger.warning(f"[EnvironmentUpdater] 查询工具 {i} 返回未知类型: {type(result)}")
            
            # 合并结果
            combined_data = {
                "ok": True,
                "data": {},
                "request_id": "",
                "elapsed_ms": 0
            }
            
            # 处理游戏状态
            if isinstance(results[0], dict) and results[0].get("ok"):
                try:
                    game_state = results[0].get("data", {})
                    combined_data["data"].update(game_state)
                    combined_data["request_id"] = results[0].get("request_id", "")
                    combined_data["elapsed_ms"] = max(combined_data["elapsed_ms"], results[0].get("elapsed_ms", 0))
                    self.logger.debug("[EnvironmentUpdater] 游戏状态数据更新成功")
                except Exception as e:
                    self.logger.warning(f"[EnvironmentUpdater] 处理游戏状态数据时出错: {e}")
            
            # 处理玩家状态
            if isinstance(results[1], dict) and results[1].get("ok"):
                try:
                    player_status = results[1].get("data", {})
                    combined_data["data"].update(player_status)
                    combined_data["elapsed_ms"] = max(combined_data["elapsed_ms"], results[1].get("elapsed_ms", 0))
                    self.logger.debug("[EnvironmentUpdater] 玩家状态数据更新成功")
                except Exception as e:
                    self.logger.warning(f"[EnvironmentUpdater] 处理玩家状态数据时出错: {e}")
            
            # 处理最近事件
            if isinstance(results[2], dict) and results[2].get("ok"):
                try:
                    recent_events = results[2].get("data", {})
                    combined_data["data"]["recentEvents"] = recent_events.get("events", [])
                    combined_data["elapsed_ms"] = max(combined_data["elapsed_ms"], results[2].get("elapsed_ms", 0))
                    self.logger.debug("[EnvironmentUpdater] 最近事件数据更新成功")
                except Exception as e:
                    self.logger.warning(f"[EnvironmentUpdater] 处理最近事件数据时出错: {e}")
                    combined_data["data"]["recentEvents"] = []
            
            # 处理周围环境 - 玩家
            if isinstance(results[3], dict) and results[3].get("ok"):
                try:
                    nearby_players = results[3].get("data", {}).get("players", {})
                    if isinstance(nearby_players, dict) and "list" in nearby_players:
                        combined_data["data"]["nearbyPlayers"] = nearby_players.get("list", [])
                    else:
                        # 如果players不是预期的结构，设置为空列表
                        combined_data["data"]["nearbyPlayers"] = []
                    combined_data["elapsed_ms"] = max(combined_data["elapsed_ms"], results[3].get("elapsed_ms", 0))
                    self.logger.debug("[EnvironmentUpdater] 周围玩家数据更新成功")
                except Exception as e:
                    self.logger.warning(f"[EnvironmentUpdater] 处理周围玩家数据时出错: {e}")
                    combined_data["data"]["nearbyPlayers"] = []
            
            # 处理周围环境 - 实体
            if isinstance(results[4], dict) and results[4].get("ok"):
                try:
                    nearby_entities = results[4].get("data", {}).get("entities", {})
                    if isinstance(nearby_entities, dict) and "list" in nearby_entities:
                        combined_data["data"]["nearbyEntities"] = nearby_entities.get("list", [])
                    else:
                        # 如果entities不是预期的结构，设置为空列表
                        combined_data["data"]["nearbyEntities"] = []
                    combined_data["elapsed_ms"] = max(combined_data["elapsed_ms"], results[4].get("elapsed_ms", 0))
                    self.logger.debug("[EnvironmentUpdater] 周围实体数据更新成功")
                except Exception as e:
                    self.logger.warning(f"[EnvironmentUpdater] 处理周围实体数据时出错: {e}")
                    combined_data["data"]["nearbyEntities"] = []
            
            # 处理周围环境 - 方块
            if isinstance(results[5], dict) and results[5].get("ok"):
                try:
                    blocks = results[5].get("data", {}).get("blocks", {})
                    if isinstance(blocks, dict):
                        combined_data["data"]["nearbyBlocks"] = blocks
                    else:
                        # 如果blocks不是预期的结构，设置为空字典
                        combined_data["data"]["nearbyBlocks"] = {}
                    combined_data["elapsed_ms"] = max(combined_data["elapsed_ms"], results[5].get("elapsed_ms", 0))
                    self.logger.debug("[EnvironmentUpdater] 周围方块数据更新成功")
                except Exception as e:
                    self.logger.warning(f"[EnvironmentUpdater] 处理周围方块数据时出错: {e}")
                    combined_data["data"]["nearbyBlocks"] = {}
            
            return combined_data
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 收集环境数据时发生异常: {e}")
            return None
        
    async def _call_tool(self, tool_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用工具"""
        try:
            result = await self.agent.mcp_client.call_tool_directly(tool_name, params)
            if not result.is_error and result.content:
                content_text = result.content[0].text
                return json.loads(content_text)
            else:
                self.logger.error(f"[EnvironmentUpdater] {tool_name}调用失败: {result.content[0].text if result.content else 'Unknown error'}")
                return None
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 调用{tool_name}时发生异常: {e}")
            return None

    async def _call_query_game_state(self) -> Optional[Dict[str, Any]]:
        """调用query_game_state工具"""
        return await self._call_tool("query_game_state", {})

    async def _call_query_player_status(self, include_inventory: bool = False) -> Optional[Dict[str, Any]]:
        """调用query_player_status工具"""
        return await self._call_tool("query_player_status", {"includeInventory": include_inventory})

    async def _call_query_recent_events(self) -> Optional[Dict[str, Any]]:
        """调用query_recent_events工具"""
        return await self._call_tool("query_recent_events", {})

    async def _call_query_surroundings(self, env_type: str) -> Optional[Dict[str, Any]]:
        """调用query_surroundings工具"""
        return await self._call_tool("query_surroundings", {"type": env_type})

    def _run_async_loop(self):
        """在新线程中运行异步事件循环"""
        import asyncio
        
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 运行异步更新循环
            loop.run_until_complete(self._update_loop())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    
    def _update_statistics(self, update_duration: float):
        """更新统计信息"""
        self.update_count += 1
        self.last_update_time = datetime.now()
        self.last_update_duration = update_duration
        self.total_update_duration += update_duration
        self.average_update_duration = self.total_update_duration / self.update_count

    
    def reset_statistics(self):
        """重置统计信息"""
        self.update_count = 0
        self.last_update_time = None
        self.last_update_duration = 0.0
        self.average_update_duration = 0.0
        self.total_update_duration = 0.0
        self.error_count = 0
        self.last_error = None
        self.last_error_time = None
        self.logger.info("[EnvironmentUpdater] 统计信息已重置")
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()
    
    def __del__(self):
        """析构函数，确保线程被正确清理"""
        if self.is_running:
            try:
                self.stop()
            except:
                pass
