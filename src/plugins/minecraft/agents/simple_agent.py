# -*- coding: utf-8 -*-
"""
简单智能体 - 基于LLM的轻量级智能体实现
"""

import logging
from typing import Dict, Any, Optional, List
from mineland import Action

from .base_agent import BaseAgent


class SimpleAgent(BaseAgent):
    """简单智能体 - 基于LLM的轻量级实现"""

    def __init__(self):
        self.llm = None
        self.config: Dict[str, Any] = {}
        self.memory: List[Dict] = []
        self.current_goal: Optional[str] = None
        self.maicore_command: Optional[str] = None
        self.command_priority: str = "normal"
        self.max_memory_size: int = 10
        self.logger = logging.getLogger(__name__)
        self._is_initialized = False

    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化简单智能体"""
        try:
            self.config = config
            self.max_memory_size = config.get("max_memory", 10)

            # 尝试初始化LLM
            model_name = config.get("model", "Pro/deepseek-ai/DeepSeek-V3")
            try:
                from langchain_openai import ChatOpenAI
                import os

                # 获取API配置
                api_key = self._get_api_config(config, "api_key", "api_key_env", "OPENAI_API_KEY")
                base_url = self._get_api_config(config, "base_url", "base_url_env", "OPENAI_BASE_URL")

                llm_kwargs = {
                    "model": model_name,
                    "temperature": config.get("temperature", 0.7),
                    "max_tokens": config.get("max_tokens", 512),
                }

                # 如果配置了API key，添加到参数中
                if api_key:
                    llm_kwargs["api_key"] = api_key

                # 如果配置了base_url，添加到参数中
                if base_url:
                    llm_kwargs["base_url"] = base_url

                self.llm = ChatOpenAI(**llm_kwargs)
                self._is_initialized = True
                self.logger.info(f"简单智能体初始化完成，使用模型: {model_name}")
            except ImportError:
                self.logger.warning("langchain_openai未安装，简单智能体将使用规则模式")
                self._is_initialized = True

        except Exception as e:
            self.logger.error(f"初始化简单智能体失败: {e}")
            raise

    async def run(
        self,
        obs: Dict[str, Any],
        code_info: Optional[Dict] = None,
        done: Optional[bool] = None,
        task_info: Optional[Dict] = None,
        maicore_command: Optional[str] = None,
    ) -> Optional[Action]:
        """执行一步决策"""
        if not self._is_initialized:
            raise RuntimeError("简单智能体未初始化")

        try:
            # 构建上下文
            context = self._build_context(obs, code_info, done, task_info, maicore_command)

            if self.llm:
                # 使用LLM推理
                action_code = await self._llm_decision(context)
            else:
                # 使用规则模式
                action_code = self._rule_based_decision(obs, maicore_command)

            # 更新记忆
            self._update_memory(obs, action_code)

            return Action(type=Action.NEW, code=action_code)

        except Exception as e:
            self.logger.error(f"简单智能体执行错误: {e}")
            return Action(type=Action.NEW, code="await bot.no_op()")

    def _build_context(
        self,
        obs: Dict,
        code_info: Optional[Dict],
        done: Optional[bool],
        task_info: Optional[Dict],
        maicore_command: Optional[str],
    ) -> str:
        """构建决策上下文"""
        context_parts = []

        # 当前观察
        if obs:
            context_parts.append(f"当前观察: {str(obs)[:500]}")  # 限制长度

        # 历史记忆
        if self.memory:
            recent_memory = self.memory[-3:]  # 最近3次记忆
            context_parts.append(f"最近记忆: {recent_memory}")

        # MaiCore指令（优先级高）- 尝试解析JSON格式
        if maicore_command:
            parsed_action = self._parse_maicore_command(maicore_command)
            if parsed_action:
                context_parts.append(f"即时指令动作: {parsed_action}")
            else:
                context_parts.append(f"即时指令: {maicore_command}")
        elif self.maicore_command:
            parsed_action = self._parse_maicore_command(self.maicore_command)
            if parsed_action:
                context_parts.append(f"上层指令动作[{self.command_priority}]: {parsed_action}")
            else:
                context_parts.append(f"上层指令[{self.command_priority}]: {self.maicore_command}")

        # 任务信息
        if task_info:
            context_parts.append(f"任务信息: {task_info}")

        # 当前目标
        if self.current_goal:
            context_parts.append(f"当前目标: {self.current_goal}")

        # 完成状态
        if done is not None:
            context_parts.append(f"任务完成状态: {done}")

        return "\n\n".join(context_parts)

    def _parse_maicore_command(self, command: str) -> Optional[str]:
        """解析MaiCore指令，提取actions字段"""
        try:
            import json
            import re

            # 清理可能的markdown代码块
            command_clean = command.strip()
            if command_clean.startswith("```json") and command_clean.endswith("```"):
                command_clean = command_clean[7:-3].strip()
            elif command_clean.startswith("```") and command_clean.endswith("```"):
                command_clean = command_clean[3:-3].strip()

            # 尝试解析JSON
            try:
                data = json.loads(command_clean)
                if isinstance(data, dict) and "actions" in data:
                    actions = data["actions"]
                    if isinstance(actions, str) and actions.strip():
                        self.logger.info(f"从MaiCore指令中提取到动作: {actions}")
                        return actions.strip()
            except json.JSONDecodeError:
                # 如果不是JSON格式，尝试用正则表达式提取actions字段
                actions_match = re.search(r'"actions":\s*"([^"]+)"', command_clean)
                if actions_match:
                    actions = actions_match.group(1)
                    self.logger.info(f"通过正则表达式提取到动作: {actions}")
                    return actions

                # 尝试提取不带引号的actions
                actions_match = re.search(r'"actions":\s*([^,}]+)', command_clean)
                if actions_match:
                    actions = actions_match.group(1).strip().strip('"')
                    if actions:
                        self.logger.info(f"通过正则表达式提取到动作(无引号): {actions}")
                        return actions

            return None

        except Exception as e:
            self.logger.error(f"解析MaiCore指令时出错: {e}")
            return None

    async def _llm_decision(self, context: str) -> str:
        """使用LLM进行决策"""
        try:
            if not self.llm:
                self.logger.warning("LLM未初始化，使用规则模式")
                return "await bot.no_op()"

            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [SystemMessage(content=self._get_system_prompt()), HumanMessage(content=context)]

            response = await self.llm.ainvoke(messages)
            action_code = self._parse_action_from_response(str(response.content))

            return action_code

        except Exception as e:
            self.logger.error(f"LLM决策错误: {e}")
            return "await bot.no_op()"

    def _rule_based_decision(self, obs: Dict, maicore_command: Optional[str]) -> str:
        """基于规则的决策（fallback模式）"""
        # 简单的规则决策逻辑
        if maicore_command:
            # 尝试解析MaiCore指令
            command_lower = maicore_command.lower()
            if "forward" in command_lower or "前进" in command_lower:
                return "await bot.move_forward(1)"
            elif "back" in command_lower or "后退" in command_lower:
                return "await bot.move_backward(1)"
            elif "left" in command_lower or "左转" in command_lower:
                return "await bot.turn_left()"
            elif "right" in command_lower or "右转" in command_lower:
                return "await bot.turn_right()"
            elif "dig" in command_lower or "挖" in command_lower:
                return "await bot.dig_down()"
            elif "jump" in command_lower or "跳" in command_lower:
                return "await bot.jump()"
            elif "wood" in command_lower or "木头" in command_lower or "原木" in command_lower:
                return "mineBlock(bot, 'oak_log', 3)"
            elif "stone" in command_lower or "石头" in command_lower:
                return "mineBlock(bot, 'stone', 5)"
            elif "chat" in command_lower or "说话" in command_lower:
                return "bot.chat('大家好！')"

        # 检查健康状态
        if obs and obs.get("health", 20) < 10:
            return "await bot.no_op()  # 生命值低，休息"

        # 基于观察的简单决策
        if obs:
            # 如果看到木头，收集木头
            if "oak_log" in str(obs).lower():
                return "mineBlock(bot, 'oak_log', 2)"
            # 如果看到石头，收集石头
            elif "stone" in str(obs).lower():
                return "mineBlock(bot, 'stone', 3)"
            # 如果在水中，游到岸边
            elif "water" in str(obs).lower():
                return "swimToLand(bot)"

        # 随机探索（使用基础移动API）
        import random

        actions = [
            "await bot.move_forward(1)",
            "await bot.turn_left()",
            "await bot.turn_right()",
            "mineBlock(bot, 'oak_log', 1)",
            "bot.chat('正在探索世界！')",
            "await bot.no_op()",
        ]
        return random.choice(actions)

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个Minecraft智能体，正在直播游戏。你需要根据当前观察和上下文，生成合适的动作代码。

## 决策优先级
1. **如果有即时指令动作或上层指令动作，直接执行该动作代码**
2. 如果有其他玩家发言，友好回应
3. 基于观察和记忆做出合理决策
4. 确保安全，避免危险动作

## 指令处理说明
- 当看到"即时指令动作"或"上层指令动作"时，请直接返回该动作代码
- 如果动作包含多个语句（用分号分隔），请选择第一个动作执行
- 例如：如果指令动作是"mineBlock(bot,'oak_log',2); bot.chat('hello');"，请返回"mineBlock(bot,'oak_log',2)"

## 可用的API函数
以下是一些有用的Mineflayer API和函数:
- `bot.chat(message)`: 发送聊天消息，聊天消息请使用中文
- `mineBlock(bot, name, count)`: 收集指定方块，例如`mineBlock(bot,'oak_log',5)`。无法挖掘非方块，例如想要挖掘铁矿石需要`iron_ore`而不是`raw_iron`
- `craftItem(bot, name, count)`: 合成物品，合成之前请先制作并放置工作台，否则无法合成
- `placeItem(bot, name, position)`: 放置方块
- `smeltItem(bot, name, count)`: 冶炼物品
- `killMob(bot, name, timeout)`: 击杀生物
- `followPlayer(bot,playerName,followDistance=3,timeout=60)`: 跟随玩家
- `swimToLand(bot, maxDistance = 100, timeout = 60)`: 游泳到岸边
- `bot.toss(itemType, metadata, count)`: 丢弃物品，丢弃时记得离开原地，否则物品会被吸收回来

## 基础移动API
- `bot.move_forward(distance)`: 向前移动
- `bot.move_backward(distance)`: 向后移动
- `bot.turn_left()`: 左转
- `bot.turn_right()`: 右转
- `bot.jump()`: 跳跃
- `bot.dig_down()`: 向下挖掘
- `bot.dig_up()`: 向上挖掘
- `bot.dig_forward()`: 向前挖掘
- `bot.no_op()`: 不执行任何动作

## 编写代码时的注意事项
- 代码需要符合JavaScript语法，使用bot相关异步函数时记得在async函数内await，但是mineBlock之类的高级函数不需要await
- 检查机器人库存再使用物品
- 每次不要收集太多物品，够用即可
- 只编写能够在10秒内完成的代码
- 请保持角色移动，不要一直站在原地
- 一次不要写太多代码，否则容易出现错误。不要写复杂判断，一次只写几句代码
- 如果状态一直没有变化，请检查代码是否正确（例如方块或物品名称是否正确）并使用新的代码，而不是重复执行同样的代码
- 如果目标一直无法完成，请切换目标
- **重要：避免重复说话！** 在使用`bot.chat()`时，请检查你最近是否说过类似的话。如果已经说过，就不要再重复了，或者换一个完全不同的表达方式
- 如果你发现自己在重复相同的行为或话语，立即改变策略：尝试新的活动、换个话题、或者保持沉默专注于游戏
- 不要使用`bot.on`或`bot.once`注册事件监听器
- 尽可能使用mineBlock、craftItem、placeItem、smeltItem、killMob等高级函数，如果没有，才使用Mineflayer API
- 如果你看到有玩家和你聊天，请友好回应，不要不理他们，但也不要反复说同样的话

## 示例动作代码
- `mineBlock(bot, 'oak_log', 3)` - 收集3个橡木原木
- `craftItem(bot, 'oak_planks', 12)` - 合成12个橡木木板
- `placeItem(bot, 'crafting_table')` - 放置工作台
- `bot.chat("大家好！我正在收集木材")` - 发送聊天消息
- `await bot.move_forward(2)` - 向前移动2步

请直接返回一行动作代码，不要解释。优先执行MaiCore的指令动作，其次使用高级函数（mineBlock、craftItem等），只有在必要时才使用基础移动API。"""

    def _parse_action_from_response(self, response: str) -> str:
        """从LLM响应中解析动作代码"""
        # 提取包含动作的行
        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            # 移除可能的markdown代码块标记
            if line.startswith("```") or line.endswith("```"):
                continue

            # 检查是否包含有效的动作代码
            if (
                line.startswith("await bot.")
                or line.startswith("bot.")
                or "mineBlock(" in line
                or "craftItem(" in line
                or "placeItem(" in line
                or "smeltItem(" in line
                or "killMob(" in line
                or "followPlayer(" in line
                or "swimToLand(" in line
            ):
                # 如果包含分号，取第一个动作
                if ";" in line:
                    first_action = line.split(";")[0].strip()
                    self.logger.info(f"从复合动作中提取第一个动作: {first_action}")
                    return first_action
                return line

        # 如果没有找到，尝试从整个响应中提取
        response_clean = response.strip()
        if (
            response_clean.startswith("await bot.")
            or response_clean.startswith("bot.")
            or "mineBlock(" in response_clean
            or "craftItem(" in response_clean
            or "placeItem(" in response_clean
            or "smeltItem(" in response_clean
            or "killMob(" in response_clean
            or "followPlayer(" in response_clean
            or "swimToLand(" in response_clean
        ):
            # 如果包含分号，取第一个动作
            if ";" in response_clean:
                first_action = response_clean.split(";")[0].strip()
                self.logger.info(f"从复合动作中提取第一个动作: {first_action}")
                return first_action
            return response_clean

        # 如果没有找到，返回默认动作
        return "await bot.no_op()"

    def _update_memory(self, obs: Dict, action_code: str) -> None:
        """更新记忆"""
        memory_entry = {
            "obs_summary": str(obs)[:100] if obs else "无观察",
            "action": action_code,
            "timestamp": self._get_timestamp(),
        }

        self.memory.append(memory_entry)

        # 限制记忆大小
        if len(self.memory) > self.max_memory_size:
            self.memory = self.memory[-self.max_memory_size :]

    def _get_timestamp(self) -> str:
        """获取时间戳"""
        import time

        return str(int(time.time()))

    def _get_api_config(self, config: Dict[str, Any], direct_key: str, env_key: str, default_env: str) -> Optional[str]:
        """
        获取API配置，支持直接配置和环境变量

        Args:
            config: 配置字典
            direct_key: 直接配置的键名
            env_key: 环境变量名配置的键名
            default_env: 默认环境变量名

        Returns:
            配置值
        """
        import os

        # 优先使用直接配置
        if direct_key in config and config[direct_key] and config[direct_key] != "your_api_key_here":
            return config[direct_key]

        # 其次使用配置中指定的环境变量名
        if env_key in config and config[env_key]:
            env_name = config[env_key]
            value = os.getenv(env_name)
            if value:
                return value

        # 最后使用默认环境变量名
        value = os.getenv(default_env)
        if value:
            return value

        return None

    async def reset(self) -> None:
        """重置智能体状态"""
        self.memory.clear()
        self.current_goal = None
        self.maicore_command = None
        self.command_priority = "normal"
        self.logger.info("简单智能体状态已重置")

    async def receive_command(self, command: str, priority: str = "normal") -> None:
        """接收上层指令"""
        self.maicore_command = command
        self.command_priority = priority
        self.logger.info(f"收到MaiCore指令[{priority}]: {command}")

    async def get_status(self) -> Dict[str, Any]:
        """获取智能体状态"""
        return {
            "agent_type": "simple",
            "initialized": self._is_initialized,
            "has_llm": self.llm is not None,
            "memory_size": len(self.memory),
            "current_goal": self.current_goal,
            "current_command": self.maicore_command,
            "command_priority": self.command_priority,
            "config": self.config,
        }

    def get_agent_type(self) -> str:
        """获取智能体类型"""
        return "simple"

    async def cleanup(self) -> None:
        """清理资源"""
        self.memory.clear()
        self.llm = None
        self._is_initialized = False
        self.logger.info("简单智能体清理完成")
