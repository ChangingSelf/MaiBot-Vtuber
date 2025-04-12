import pyvts
import asyncio
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class VTubeStudioController:
    """VTubeStudio控制器 - 封装pyvts相关功能"""

    def __init__(
        self,
        plugin_name: str,
        developer: str,
        token_path: str = "./token.txt",
        host: str = "localhost",
        port: int = 8001,
        api_name: str = "VTubeStudioPublicAPI",
        api_version: str = "1.0",
    ):
        """初始化VTubeStudio控制器

        Args:
            plugin_name: 插件名称
            developer: 开发者名称
            token_path: 认证令牌文件路径
            host: 主机地址
            port: 端口
            api_name: API名称
            api_version: API版本
        """
        self.plugin_info = {
            "plugin_name": plugin_name,
            "developer": developer,
            "authentication_token_path": token_path,
        }
        self.vts_api_info = {
            "host": host,
            "port": port,
            "name": api_name,
            "version": api_version,
        }
        self.vts = pyvts.vts(plugin_info=self.plugin_info, vts_api_info=self.vts_api_info)
        self.is_connected = False
        self.available_expressions = []
        self.available_hotkeys = []
        self.available_models = []
        self.current_model = None

    async def connect(self) -> bool:
        """连接到VTubeStudio并完成认证

        Returns:
            bool: 连接是否成功
        """
        try:
            await self.vts.connect()
            await self.vts.request_authenticate_token()
            await self.vts.request_authenticate()
            self.is_connected = True
            logger.info("成功连接到VTubeStudio并完成认证")

            # 获取可用资源
            await self._fetch_available_resources()

            return True
        except Exception as e:
            logger.error(f"连接VTubeStudio失败: {e}")
            self.is_connected = False
            return False

    async def close(self):
        """关闭VTubeStudio连接"""
        if self.vts:
            try:
                await self.vts.close()
                logger.info("已关闭VTubeStudio连接")
            except Exception as e:
                logger.error(f"关闭VTubeStudio连接时出错: {e}")
            finally:
                self.is_connected = False

    async def _fetch_available_resources(self):
        """获取可用资源（表情、热键、模型等）"""
        try:
            # 获取热键列表
            self.available_hotkeys = await self.get_hotkey_list()

            # 获取表情列表
            self.available_expressions = await self.get_expression_list()

            # 获取模型列表
            self.available_models = await self.get_model_list()

            # 获取当前模型
            self.current_model = await self.get_current_model()

            logger.info(
                f"获取VTubeStudio资源成功: "
                f"{len(self.available_expressions)}个表情, "
                f"{len(self.available_hotkeys)}个热键, "
                f"{len(self.available_models)}个模型"
            )
        except Exception as e:
            logger.error(f"获取VTubeStudio资源失败: {e}")

    async def get_hotkey_list(self) -> List[str]:
        """获取所有可用的热键列表

        Returns:
            List[str]: 热键名称列表
        """
        try:
            response_data = await self.vts.request(self.vts.vts_request.requestHotKeyList())
            hotkey_list = [hotkey["name"] for hotkey in response_data["data"]["availableHotkeys"]]
            logger.debug(f"获取到{len(hotkey_list)}个热键")
            return hotkey_list
        except Exception as e:
            logger.error(f"获取热键列表失败: {e}")
            return []

    async def get_expression_list(self) -> List[str]:
        """获取所有可用的表情列表

        Returns:
            List[str]: 表情名称列表
        """
        try:
            response_data = await self.vts.request(self.vts.vts_request.requestExpressionStateList())
            expression_list = [expr["name"] for expr in response_data["data"]["expressions"]]
            logger.debug(f"获取到{len(expression_list)}个表情")
            return expression_list
        except Exception as e:
            logger.error(f"获取表情列表失败: {e}")
            return []

    async def get_model_list(self) -> List[Dict[str, Any]]:
        """获取所有可用的模型列表

        Returns:
            List[Dict[str, Any]]: 模型信息列表
        """
        try:
            response_data = await self.vts.request(self.vts.vts_request.requestModelList())
            model_list = response_data["data"]["availableModels"]
            logger.debug(f"获取到{len(model_list)}个模型")
            return model_list
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return []

    async def get_current_model(self) -> Optional[Dict[str, Any]]:
        """获取当前加载的模型信息

        Returns:
            Optional[Dict[str, Any]]: 当前模型信息
        """
        try:
            response_data = await self.vts.request(self.vts.vts_request.requestCurrentModel())
            model_info = response_data["data"]["modelName"]
            logger.debug(f"当前模型: {model_info}")
            return model_info
        except Exception as e:
            logger.error(f"获取当前模型信息失败: {e}")
            return None

    async def trigger_hotkey(self, hotkey_name: str) -> bool:
        """触发指定的热键

        Args:
            hotkey_name: 热键名称

        Returns:
            bool: 触发是否成功
        """
        if not self.is_connected:
            logger.warning("未连接到VTubeStudio，无法触发热键")
            return False

        try:
            send_hotkey_request = self.vts.vts_request.requestTriggerHotKey(hotkey_name)
            await self.vts.request(send_hotkey_request)
            logger.debug(f"成功触发热键: {hotkey_name}")
            return True
        except Exception as e:
            logger.error(f"触发热键失败: {e}")
            return False

    async def set_expression(self, expression_name: Optional[str]) -> bool:
        """设置表情

        Args:
            expression_name: 表情名称，None表示重置表情

        Returns:
            bool: 设置是否成功
        """
        if not self.is_connected:
            logger.warning("未连接到VTubeStudio，无法设置表情")
            return False

        try:
            if expression_name is None:
                # 重置表情
                request_data = self.vts.vts_request.requestExpressionActivation("", active=False)
                await self.vts.request(request_data)
                logger.debug("已重置表情")
                return True
            else:
                # 设置指定表情
                request_data = self.vts.vts_request.requestExpressionActivation(expression_name, active=True)
                await self.vts.request(request_data)
                logger.debug(f"已设置表情: {expression_name}")
                return True
        except Exception as e:
            logger.error(f"设置表情时出错: {e}")
            return False

    async def set_parameter(self, parameter_name: str, value: float) -> bool:
        """设置Live2D参数

        Args:
            parameter_name: 参数名称
            value: 参数值

        Returns:
            bool: 设置是否成功
        """
        if not self.is_connected:
            logger.warning("未连接到VTubeStudio，无法设置参数")
            return False

        try:
            request_data = self.vts.vts_request.requestParameterValue(parameter_name, value)
            await self.vts.request(request_data)
            logger.debug(f"已设置参数: {parameter_name} = {value}")
            return True
        except Exception as e:
            logger.error(f"设置参数时出错: {e}")
            return False

    async def load_item(
        self,
        file_name: str,
        positionX: float = 0.5,
        positionY: float = 0.5,
        size: float = 0.33,
        rotation: float = 90,
        fadeTime: float = 0.5,
        order: int = 4,
    ) -> Optional[str]:
        """加载指定物品

        Args:
            file_name: 物品文件名
            positionX: X坐标 (0-1)
            positionY: Y坐标 (0-1)
            size: 大小 (0-1)
            rotation: 旋转角度
            fadeTime: 淡入时间
            order: 物品层级

        Returns:
            Optional[str]: 物品实例ID，失败时返回None
        """
        if not self.is_connected:
            logger.warning("未连接到VTubeStudio，无法加载物品")
            return None

        try:
            request_data = {
                "apiName": self.vts_api_info["name"],
                "apiVersion": self.vts_api_info["version"],
                "requestID": "SomeID",
                "messageType": "ItemLoadRequest",
                "data": {
                    "fileName": file_name,
                    "positionX": positionX,
                    "positionY": positionY,
                    "size": size,
                    "rotation": rotation,
                    "fadeTime": fadeTime,
                    "order": order,
                    "failIfOrderTaken": False,
                    "smoothing": 0,
                    "censored": False,
                    "flipped": False,
                    "locked": False,
                    "unloadWhenPluginDisconnects": True,
                },
            }
            response_data = await self.vts.request(request_data)
            instance_id = response_data.get("data", {}).get("instanceID")
            logger.debug(f"成功加载物品: {file_name}, 实例ID: {instance_id}")
            return instance_id
        except Exception as e:
            logger.error(f"加载物品失败: {e}")
            return None
