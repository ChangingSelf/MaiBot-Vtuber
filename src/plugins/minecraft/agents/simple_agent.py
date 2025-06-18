# -*- coding: utf-8 -*-
"""
简单智能体 - 基于LLM的轻量级智能体实现
"""

import logging
from typing import Dict, Any, Optional, List
from mineland import Action

from .base_agent import BaseAgent
from src.plugins.minecraft.state.analyzers import StateAnalyzer


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
        self.state_analyzer: Optional[StateAnalyzer] = None

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
            # 初始化或更新状态分析器
            if obs:
                if self.state_analyzer is None:
                    self.state_analyzer = StateAnalyzer(obs=obs, config=self.config)
                else:
                    self.state_analyzer.set_observation(obs)

            # 构建上下文
            context = self._build_context(obs, code_info, done, task_info, maicore_command)

            if self.llm:
                # 使用LLM推理
                action_code = await self._llm_decision(context)
            else:
                # 使用规则模式
                action_code = self._rule_based_decision(obs, maicore_command)

            # 验证和修复动作代码
            action_code = self._validate_and_fix_action(action_code)

            # 更新记忆
            self._update_memory(obs, action_code)

            return Action(type=Action.NEW, code=action_code)

        except Exception as e:
            self.logger.error(f"简单智能体执行错误: {e}")
            return Action(type=Action.RESUME, code="")

    def _validate_and_fix_action(self, action_code: str) -> str:
        """验证并修复动作代码"""
        # 常见错误API的修复映射
        fixes = {
            "bot.move_forward": 'bot.setControlState("forward", true)',
            "bot.move_backward": 'bot.setControlState("back", true)',
            "bot.turn_left": "bot.look(bot.entity.yaw - Math.PI/2, bot.entity.pitch)",
            "bot.turn_right": "bot.look(bot.entity.yaw + Math.PI/2, bot.entity.pitch)",
            "bot.jump": 'bot.setControlState("jump", true)',
            "bot.no_op": "// 等待",
            "bot.dig_down": "bot.dig(bot.blockAt(bot.entity.position.offset(0, -1, 0)))",
            "bot.dig_up": "bot.dig(bot.blockAt(bot.entity.position.offset(0, 1, 0)))",
            "bot.dig_forward": "bot.dig(bot.blockAt(bot.entity.position.offset(0, 0, 1)))",
        }

        # 应用修复
        for wrong_api, correct_api in fixes.items():
            if wrong_api in action_code:
                action_code = action_code.replace(wrong_api, correct_api)
                self.logger.info(f"修复API: {wrong_api} -> {correct_api}")

        return action_code

    def _build_context(
        self,
        obs: Dict,
        code_info: Optional[Dict],
        done: Optional[bool],
        task_info: Optional[Dict],
        maicore_command: Optional[str],
    ) -> str:
        """构建决策上下文 - 使用状态分析器获取环境感知"""
        context_parts = []

        # === 环境感知部分 (优先级最高) ===
        if obs and self.state_analyzer:
            # 使用状态分析器提供的详细环境分析
            analysis_result = self.state_analyzer.analyze_all()
            if isinstance(analysis_result, list):
                context_parts.extend(analysis_result)
            else:
                context_parts.append(str(analysis_result))

        # === 代码执行状态 ===
        if code_info:
            if code_info.get("code_error"):
                error_info = code_info["code_error"]
                context_parts.extend(
                    (
                        "=== 执行错误 ===",
                        f"上次代码执行失败: {error_info.get('error_message', '未知错误')}",
                        "",
                    )
                )
            elif code_info.get("is_ready"):
                context_parts.extend(("=== 执行状态 ===", "代码执行完成，准备下一个动作", ""))
        # === 历史记忆 ===
        if self.memory:
            recent_memory = self.memory[-2:]  # 最近2次记忆
            context_parts.append("=== 最近动作 ===")
            context_parts.extend(
                f"{i}. {memory.get('action', '未知动作')}" for i, memory in enumerate(recent_memory, 1)
            )
            context_parts.append("")

        # === MaiCore指令 (优先级最高) ===
        if maicore_command:
            parsed_action = self._parse_maicore_command(maicore_command)
            context_parts.append("=== 即时指令 ===")
            if parsed_action:
                context_parts.append(f"需要执行: {parsed_action}")
            else:
                context_parts.append(f"指令内容: {maicore_command}")
            context_parts.append("")
        elif self.maicore_command:
            parsed_action = self._parse_maicore_command(self.maicore_command)
            context_parts.append(f"=== 待执行指令 [{self.command_priority}] ===")
            if parsed_action:
                context_parts.append(f"需要执行: {parsed_action}")
            else:
                context_parts.append(f"指令内容: {self.maicore_command}")
            context_parts.append("")

        # === 任务信息 ===
        if task_info:
            context_parts.extend(("=== 任务信息 ===", f"任务: {task_info}", ""))
        # 当前目标
        if self.current_goal:
            context_parts.extend(("=== 当前目标 ===", f"目标: {self.current_goal}", ""))
        return "\n".join(context_parts)

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
                if actions_match := re.search(r'"actions":\s*"([^"]+)"', command_clean):
                    actions = actions_match.group(1)
                    self.logger.info(f"通过正则表达式提取到动作: {actions}")
                    return actions

                if actions_match := re.search(r'"actions":\s*([^,}]+)', command_clean):
                    if actions := actions_match.group(1).strip().strip('"'):
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
                return "// 等待"

            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [SystemMessage(content=self._get_system_prompt()), HumanMessage(content=context)]

            response = await self.llm.ainvoke(messages)
            return self._parse_action_from_response(str(response.content))
        except Exception as e:
            self.logger.error(f"LLM决策错误: {e}")
            return "// 等待"

    def _rule_based_decision(self, obs: Dict, maicore_command: Optional[str]) -> str:
        """基于规则的决策（fallback模式）"""
        # 简单的规则决策逻辑
        if maicore_command:
            # 尝试解析MaiCore指令
            command_lower = maicore_command.lower()
            if "forward" in command_lower or "前进" in command_lower:
                return 'bot.setControlState("forward", true); setTimeout(() => bot.setControlState("forward", false), 1000)'
            elif "back" in command_lower or "后退" in command_lower:
                return 'bot.setControlState("back", true); setTimeout(() => bot.setControlState("back", false), 1000)'
            elif "left" in command_lower or "左转" in command_lower:
                return "bot.look(bot.entity.yaw - Math.PI/4, bot.entity.pitch)"
            elif "right" in command_lower or "右转" in command_lower:
                return "bot.look(bot.entity.yaw + Math.PI/4, bot.entity.pitch)"
            elif "jump" in command_lower or "跳" in command_lower:
                return 'bot.setControlState("jump", true); setTimeout(() => bot.setControlState("jump", false), 500)'
            elif "chat" in command_lower or "说话" in command_lower:
                return 'bot.chat("大家好！")'

        # 检查健康状态
        if obs and obs.get("health", 20) < 10:
            return "// 生命值低，休息"

        # 随机探索
        import random

        actions = [
            'bot.setControlState("forward", true); setTimeout(() => bot.setControlState("forward", false), 2000)',
            "bot.look(bot.entity.yaw + Math.PI/4, bot.entity.pitch)",
            "bot.look(bot.entity.yaw - Math.PI/4, bot.entity.pitch)",
            'mineBlock(bot, "oak_log", 1)',
            'bot.chat("正在探索世界！")',
            "// 观察周围环境",
        ]
        return random.choice(actions)

    def _get_system_prompt(self) -> str:
        """获取系统提示 - 增强环境感知能力"""
        return """你是一个Minecraft智能体，任务是根据环境信息生成单行或多行的JavaScript动作代码。

## 决策指南
- **分析环境**: 你会收到关于生命、位置、周围方块、物品栏等的详细信息。
- **生存**: 当生命值或饥饿值低时，优先寻找食物或避开危险。夜晚时寻找安全之处。
- **移动**:
  - 前方有墙时，考虑转向或挖掘。
  - 在开阔地带可以自由探索。
  - 在水里时，使用 `swimToLand` 游到岸边。
- **挖掘**:
  - 根据周围方块信息，挖掘有价值的矿物（如 `diamond_ore`）或必要的材料（如 `oak_log`）。
  - 被困时，尝试挖掘出路。

## API参考
**重要**: 只能使用下面列出的API。确保API名称和参数正确。

### 基础
- `bot.chat("消息")`: 发送聊天消息 (请使用中文)。
- `// 注释`: 用于写注释或表示"等待"。

### 移动
- `bot.setControlState("状态", true/false)`: 设置移动状态。状态可以是 `forward`, `back`, `left`, `right`, `jump`, `sprint`。
- `bot.clearControlStates()`: 停止所有移动。
- `bot.look(yaw, pitch)`: 转向。示例:
  - `bot.look(bot.entity.yaw + Math.PI/2, bot.entity.pitch)`: 右转90度。
  - `bot.look(bot.entity.yaw - Math.PI/2, bot.entity.pitch)`: 左转90度。
- `followPlayer(bot, "玩家名")`: 跟随玩家。
- `swimToLand(bot)`: 游到最近的岸边。

### 方块
- `mineBlock(bot, "方块名", 数量)`: 挖掘并收集指定数量的方块。
  - **注意**: 方块名必须正确，例如挖铁矿石是 `iron_ore`，而不是 `raw_iron`。
- `placeItem(bot, "物品名", position)`: 在指定位置放置方块。

### 物品
- `bot.equip(item, "位置")`: 装备物品到指定位置（如 'hand', 'head'）。需要先在物品栏找到物品对象(item)。
- `bot.unequip("位置")`: 卸下指定位置的装备。
- `bot.activateItem(offhand)`: 使用手上的物品（`offhand`=false表示主手）。
- `bot.consume()`: 消耗物品（例如吃食物）。

## 输出格式
- **只返回代码**: 不要包含任何解释、markdown标记(```)或多余的文本。
- **代码示例**:
  - `bot.setControlState("forward", true);`
  - `mineBlock(bot, "oak_log", 1);`
  - `// 正在观察...`
"""

    def _parse_action_from_response(self, response: str) -> str:
        """从LLM响应中解析动作代码"""
        # 移除markdown代码块
        response = response.strip()
        if response.startswith("```javascript") or response.startswith("```js"):
            response = response.split("\n", 1)[1] if "\n" in response else response
        if response.endswith("```"):
            response = response.rsplit("\n", 1)[0] if "\n" in response else response[:-3]
        if response.startswith("```"):
            response = response[3:].strip()

        # 提取有效的代码行
        lines = response.strip().split("\n")
        code_lines = []

        for line in lines:
            line = line.strip()
            # 跳过空行和纯注释行
            if not line or line.startswith("//"):
                continue

            # 检查是否包含有效的代码
            if (
                line.startswith("bot.")
                or line.startswith("mineBlock(")
                or line.startswith("craftItem(")
                or line.startswith("placeItem(")
                or line.startswith("setTimeout(")
                or "setControlState" in line
                or "bot.chat(" in line
            ):
                code_lines.append(line)

        if code_lines:
            # 如果有多行代码，用分号连接
            result = "; ".join(code_lines)
            # 限制长度，避免过长代码
            if len(result) > 200:
                result = code_lines[0]  # 只取第一行
            return result

        # 如果没有找到有效代码，检查整个响应
        response_clean = response.strip()
        if (
            "bot." in response_clean
            or "mineBlock(" in response_clean
            or "craftItem(" in response_clean
            or "setControlState" in response_clean
        ):
            # 取第一个有效语句
            if ";" in response_clean:
                return response_clean.split(";")[0].strip()
            return response_clean

        # 默认等待
        return "// 等待下一步"

    def _update_memory(self, obs: Dict, action_code: str) -> None:
        """更新记忆"""
        memory_entry = {
            "health": obs.get("health", "unknown") if obs else "unknown",
            "action": action_code[:50] + "..." if len(action_code) > 50 else action_code,
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
        """获取API配置，支持直接配置和环境变量"""
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
            "recent_actions": [m["action"] for m in self.memory[-3:]] if self.memory else [],
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
