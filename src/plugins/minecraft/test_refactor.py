# -*- coding: utf-8 -*-
"""
重构测试脚本 - 验证智能体模式重构的基本功能
"""

import asyncio
import logging
from typing import Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_config_manager():
    """测试配置管理器"""
    logger.info("=== 测试配置管理器 ===")

    try:
        from .core.config_manager import ConfigManager

        # 模拟配置
        test_config = {
            "control_mode": "agent",
            "allow_mode_switching": True,
            "agent_manager": {"default_agent_type": "simple"},
            "agents": {"simple": {"model": "gpt-3.5-turbo", "temperature": 0.7}},
        }

        config_manager = ConfigManager(test_config)

        # 测试方法
        assert config_manager.get_control_mode() == "agent"
        assert config_manager.is_mode_switching_allowed() == True
        assert config_manager.get_agent_specific_config("simple")["model"] == "gpt-3.5-turbo"

        logger.info("✓ 配置管理器测试通过")

    except Exception as e:
        logger.error(f"✗ 配置管理器测试失败: {e}")


async def test_agent_manager():
    """测试智能体管理器"""
    logger.info("=== 测试智能体管理器 ===")

    try:
        from .core.agent_manager import AgentManager

        agent_manager = AgentManager()

        # 测试初始化
        test_config = {
            "default_agent_type": "simple",
            "agents": {"simple": {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_memory": 10}},
        }

        await agent_manager.initialize(test_config)

        # 测试可用智能体
        available_agents = await agent_manager.get_available_agents()
        logger.info(f"可用智能体类型: {available_agents}")

        # 测试当前智能体
        current_agent = await agent_manager.get_current_agent()
        if current_agent:
            agent_type = current_agent.get_agent_type()
            logger.info(f"当前智能体类型: {agent_type}")

            # 测试智能体状态
            status = await current_agent.get_status()
            logger.info(f"智能体状态: {status}")

        await agent_manager.cleanup()
        logger.info("✓ 智能体管理器测试通过")

    except Exception as e:
        logger.error(f"✗ 智能体管理器测试失败: {e}")


async def test_simple_agent():
    """测试简单智能体"""
    logger.info("=== 测试简单智能体 ===")

    try:
        from .agents.simple_agent import SimpleAgent

        agent = SimpleAgent()

        # 测试初始化
        test_config = {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 512, "max_memory": 10}

        await agent.initialize(test_config)

        # 测试智能体信息
        assert agent.get_agent_type() == "simple"

        # 测试状态
        status = await agent.get_status()
        logger.info(f"简单智能体状态: {status}")

        # 测试接收指令
        await agent.receive_command("向前移动", "high")

        # 测试执行（使用模拟观察数据）
        mock_obs = {"health": 20, "food": 20, "position": [0, 64, 0]}

        action = await agent.run(mock_obs)
        if action:
            logger.info(f"智能体生成的动作: {action.code}")

        await agent.cleanup()
        logger.info("✓ 简单智能体测试通过")

    except Exception as e:
        logger.error(f"✗ 简单智能体测试失败: {e}")


async def test_controllers():
    """测试控制器基础功能"""
    logger.info("=== 测试控制器 ===")

    try:
        from .controllers.maicore_controller import MaiCoreController
        from .controllers.agent_controller import AgentController

        # 测试控制器创建
        maicore_controller = MaiCoreController()
        agent_controller = AgentController()

        # 测试模式名称
        assert maicore_controller.get_mode_name() == "maicore"
        assert agent_controller.get_mode_name() == "agent"

        logger.info("✓ 控制器基础测试通过")

    except Exception as e:
        logger.error(f"✗ 控制器测试失败: {e}")


async def main():
    """主测试函数"""
    logger.info("开始重构功能测试...")

    # 运行各项测试
    await test_config_manager()
    await test_agent_manager()
    await test_simple_agent()
    await test_controllers()

    logger.info("测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
