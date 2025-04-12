from typing import Dict, Any, Optional, List
import logging
import re

from src.core.synaptic_network import SynapticNetwork
from src.signals.neural_signal import NeuralSignal, SignalPriority
from src.signals.sensory_signals import CommandSignal
from src.sensors.base_sensor import Sensor

logger = logging.getLogger(__name__)


class CommandSensor(Sensor):
    """命令传感器 - 处理特定命令消息，支持指令的识别与参数解析"""

    def __init__(self, synaptic_network: SynapticNetwork, name: Optional[str] = None):
        super().__init__(synaptic_network, name or "命令传感器")
        self.command_prefix = "!"  # 命令前缀
        self.command_pattern = re.compile(r"^!(\w+)(?:\s+(.*))?$")  # 命令解析正则表达式
        self.authorized_users = set()  # 授权用户列表
        self.registered_commands = {}  # 注册的命令处理器

    async def _initialize(self, config: Dict[str, Any]) -> None:
        """初始化命令传感器

        Args:
            config: 配置信息
        """
        # 设置命令前缀
        if "command_prefix" in config:
            self.command_prefix = config["command_prefix"]
            # 更新命令解析正则表达式
            self.command_pattern = re.compile(f"^{re.escape(self.command_prefix)}(\\w+)(?:\\s+(.*))?$")

        # 设置授权用户列表
        if "authorized_users" in config:
            self.authorized_users = set(config["authorized_users"])

        # 注册内置命令
        await self._register_builtin_commands()

        logger.info(f"命令传感器初始化完成: {self.name}, 命令前缀: {self.command_prefix}")

    async def _register_builtin_commands(self) -> None:
        """注册内置命令处理器"""
        # 注册帮助命令
        self.register_command("help", self._handle_help_command, "显示可用命令列表")
        self.register_command("status", self._handle_status_command, "显示系统状态")

    def register_command(
        self, command_name: str, handler: callable, description: str = "", admin_only: bool = False
    ) -> None:
        """注册命令处理器

        Args:
            command_name: 命令名称
            handler: 命令处理函数
            description: 命令描述
            admin_only: 是否仅限管理员使用
        """
        self.registered_commands[command_name] = {
            "handler": handler,
            "description": description,
            "admin_only": admin_only,
        }
        logger.debug(f"注册命令: {command_name}, 描述: {description}, 仅限管理员: {admin_only}")

    def unregister_command(self, command_name: str) -> bool:
        """取消注册命令处理器

        Args:
            command_name: 命令名称

        Returns:
            是否成功取消注册
        """
        if command_name in self.registered_commands:
            del self.registered_commands[command_name]
            logger.debug(f"取消注册命令: {command_name}")
            return True
        return False

    async def _process_raw_input(self, input_data: Dict[str, Any]) -> List[NeuralSignal]:
        """处理原始命令数据

        Args:
            input_data: 原始命令数据

        Returns:
            处理后的神经信号列表
        """
        # 提取输入信息
        user = input_data.get("user", "anonymous")
        content = input_data.get("content", "")

        # 检查是否是命令格式
        match = self.command_pattern.match(content)
        if not match:
            return []  # 不是命令格式，不处理

        command_name = match.group(1).lower()
        args_str = match.group(2) or ""

        # 解析命令参数
        args = self._parse_command_args(args_str)

        # 检查命令是否注册
        if command_name not in self.registered_commands:
            logger.debug(f"未知命令: {command_name}, 用户: {user}")
            return []

        command_info = self.registered_commands[command_name]

        # 检查用户权限
        if command_info["admin_only"] and user not in self.authorized_users:
            logger.warning(f"未授权用户尝试使用管理员命令: {user}, 命令: {command_name}")
            return []

        # 创建命令信号
        signal = CommandSignal(
            source=self.name, command=command_name, args=args, user=user, priority=SignalPriority.HIGH
        )

        # 调用命令处理器
        try:
            handler_result = command_info["handler"](user, args)
            # 如果处理器返回了额外数据，添加到信号中
            if isinstance(handler_result, dict):
                for key, value in handler_result.items():
                    signal.data[key] = value
        except Exception as e:
            logger.error(f"命令处理器执行出错: {command_name}, 错误: {e}")
            signal.data["error"] = str(e)

        logger.debug(f"生成命令信号: 用户={user}, 命令={command_name}, 参数={args}")
        return [signal]

    def _parse_command_args(self, args_str: str) -> Dict[str, Any]:
        """解析命令参数

        Args:
            args_str: 参数字符串

        Returns:
            解析后的参数字典
        """
        args = {}

        # 分割参数
        if not args_str:
            return args

        # 处理带引号的参数，例如 key="value with spaces"
        quote_pattern = re.compile(r'(\w+)=(?:"([^"]*)"|\S+)')
        quoted_args = quote_pattern.findall(args_str)

        if quoted_args:
            # 处理命名参数
            for key, value in quoted_args:
                if not value:  # 如果值是空字符串，尝试使用未引用的值
                    value_match = re.search(rf"{key}=(\S+)", args_str)
                    if value_match:
                        value = value_match.group(1)
                args[key] = value
        else:
            # 如果没有命名参数，就按顺序处理
            parts = args_str.split()
            args["args"] = parts

        return args

    async def _handle_help_command(self, user: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """处理帮助命令

        Args:
            user: 用户名
            args: 命令参数

        Returns:
            额外的信号数据
        """
        # 获取所有用户可用的命令
        available_commands = {}
        for cmd_name, cmd_info in self.registered_commands.items():
            if not cmd_info["admin_only"] or user in self.authorized_users:
                available_commands[cmd_name] = cmd_info["description"]

        return {"help_data": available_commands, "request_type": "help"}

    async def _handle_status_command(self, user: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """处理状态命令

        Args:
            user: 用户名
            args: 命令参数

        Returns:
            额外的信号数据
        """
        # 这里只返回基本状态，实际数据会由其他组件填充
        return {"request_type": "status", "status_components": args.get("args", ["all"])}
