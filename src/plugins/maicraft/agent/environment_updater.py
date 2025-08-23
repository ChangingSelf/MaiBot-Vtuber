"""
环境信息更新器
用于定期执行query_state参数来更新Minecraft环境信息
"""

import asyncio
import threading
import time
from typing import Callable, Optional, Dict, Any
from datetime import datetime
from src.utils.logger import get_logger


class EnvironmentUpdater:
    """环境信息定期更新器"""
    
    def __init__(self, 
                 agent=None,
                 update_interval: int = 2,
                 auto_start: bool = False):
        """
        初始化环境更新器
        
        Args:
            agent: MaicraftAgent实例，用于调用query_state工具
            update_interval: 更新间隔（秒），默认5秒
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
        
        # 错误统计
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.last_error_time: Optional[datetime] = None
        
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
                self._handle_error(str(e))
                await asyncio.sleep(1)  # 出错时等待1秒再继续
        
        self.logger.info("[EnvironmentUpdater] 异步更新循环已结束")
    
    async def _perform_update(self):
        """执行单次环境更新（异步版本）"""
        try:
            self.logger.debug("[EnvironmentUpdater] 开始执行环境更新")
            
            if not self.agent:
                self.logger.error("[EnvironmentUpdater] Agent未设置，无法执行更新")
                return
            
            # 调用query_state工具获取环境数据
            result = await self._call_query_state_tool()
            
            if result:
                # 更新全局环境信息
                try:
                    from .environment import global_environment
                    global_environment.update_from_observation(result)
                    # self.logger.info(f"[EnvironmentUpdater] 全局环境信息已更新，最后更新: {global_environment.last_update}")
                except Exception as e:
                    self.logger.error(f"[EnvironmentUpdater] 更新全局环境信息失败: {e}")
                
                self.logger.debug(f"[EnvironmentUpdater] 环境更新完成，结果: {result}")
            else:
                self.logger.warning("[EnvironmentUpdater] 环境更新未返回结果")
            
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 环境更新失败: {e}")
            raise


    async def _call_query_state_tool(self) -> Optional[Any]:
        """直接使用MCP客户端调用query_state工具（异步版本）"""
        try:
            # 直接通过MCP客户端调用query_state工具
            try:
                # 调用MCP工具
                result = await self.agent.mcp_client.call_tool_directly("query_state", {})
                # 处理返回结果
                if hasattr(result, 'content') and result.content:
                    # 如果是CallToolResult对象，提取文本内容
                    content_text = result.content[0].text
                    try:
                        import json
                        parsed_result = json.loads(content_text)
                        self.logger.debug(f"[EnvironmentUpdater] MCP工具调用成功，解析结果: {parsed_result}")
                        return parsed_result
                    except json.JSONDecodeError:
                        self.logger.warning(f"[EnvironmentUpdater] 工具返回结果不是有效JSON: {content_text}")
                        return None
                else:
                    # 其他类型的返回值
                    # self.logger.debug(f"[EnvironmentUpdater] MCP工具调用成功，返回结果: {result}")
                    return result
                    
            except Exception as e:
                self.logger.error(f"[EnvironmentUpdater] MCP工具调用失败: {e}")
                return None
                
        except Exception as e:
            self.logger.error(f"[EnvironmentUpdater] 调用query_state工具时发生异常: {e}")
            return None

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
    
    def _handle_error(self, error_message: str):
        """处理错误"""
        self.error_count += 1
        self.last_error = error_message
        self.last_error_time = datetime.now()
    
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
