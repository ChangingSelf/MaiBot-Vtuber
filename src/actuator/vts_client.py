import pyvts
import asyncio
from typing import List
from ..utils.config import config
from ..utils.logger import get_logger


class VtubeStudioClient:
    """封装pyvts相关功能"""

    def __init__(
        self,
        plugin_name: str,
        developer: str,
        token_path: str = "./token.txt",
        host: str = "localhost",
        port: int = 8001,
    ):
        """
        初始化VTS管理器

        Args:
            plugin_name: 插件名称
            developer: 开发者名称
            token_path: 认证令牌文件路径
        """
        self.plugin_info = {
            "plugin_name": plugin_name,
            "developer": developer,
            "authentication_token_path": token_path,
        }
        self.vts_api_info = {
            "host": host,
            "port": port,
            "name": "VTubeStudioPublicAPI",
            "version": "1.0",
        }
        self.vts = pyvts.vts(plugin_info=self.plugin_info, vts_api_info=self.vts_api_info)
        self.logger = get_logger("VtubeStudioClient")

    async def connect(self) -> bool:
        """
        连接到VTS并完成认证

        Returns:
            bool: 连接是否成功
        """
        try:
            await self.vts.connect()
            await self.vts.request_authenticate_token()
            await self.vts.request_authenticate()
            self.logger.info("成功连接到VTS并完成认证")
            return True
        except Exception as e:
            self.logger.error(f"连接VTS失败: {str(e)}")
            return False

    async def get_hotkey_list(self) -> List[str]:
        """
        获取所有可用的热键列表

        Returns:
            List[str]: 热键名称列表
        """
        try:
            response_data = await self.vts.request(self.vts.vts_request.requestHotKeyList())
            hotkey_list = [hotkey["name"] for hotkey in response_data["data"]["availableHotkeys"]]
            self.logger.info(f"获取到{len(hotkey_list)}个热键")
            return hotkey_list
        except Exception as e:
            self.logger.error(f"获取热键列表失败: {str(e)}")
            return []

    async def trigger_hotkey(self, hotkey_name: str) -> bool:
        """
        触发指定的热键

        Args:
            hotkey_name: 热键名称

        Returns:
            bool: 触发是否成功
        """
        try:
            send_hotkey_request = self.vts.vts_request.requestTriggerHotKey(hotkey_name)
            await self.vts.request(send_hotkey_request)
            self.logger.info(f"成功触发热键: {hotkey_name}")
            return True
        except Exception as e:
            self.logger.error(f"触发热键失败: {str(e)}")
            return False

    async def close(self):
        """关闭VTS连接"""
        if self.vts:
            await self.vts.close()
            self.logger.info("已关闭VTS连接")


async def main():
    """示例"""
    # 创建VTS管理器实例
    vts_client = VtubeStudioClient(
        plugin_name=config.plugin_name,
        developer=config.developer,
    )

    # 连接到VTS
    connected = await vts_client.connect()
    if not connected:
        print("无法连接到VTS，程序退出")
        return

    try:
        # 获取所有热键
        hotkey_list = await vts_client.get_hotkey_list()
        print(f"可用的热键: {hotkey_list}")

        # 如果有热键，触发第一个
        if hotkey_list:
            print(f"触发热键: {hotkey_list[0]}")
            await vts_client.trigger_hotkey(hotkey_list[0])

        # 等待一段时间
        await asyncio.sleep(2)

    finally:
        # 关闭连接
        await vts_client.close()


if __name__ == "__main__":
    asyncio.run(main())
