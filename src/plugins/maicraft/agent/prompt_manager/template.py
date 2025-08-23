from .prompt_manager import PromptTemplate, prompt_manager

def init_templates() -> None:
    """初始化提示词模板"""
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_goal_generation",
        template="""你是一个Minecraft游戏助手。请为玩家生成一个简单可行的游戏目标。
    当前信息:
    - 玩家位置: {player_position}
    - 库存: {inventory}

    环境信息: 
    {environment}
    
    你之前执行过的目标：
    {executed_goals}

    请生成一个简单、具体、可执行的目标。目标应该：
    1. 简单明确（一句话描述）
    2. 可立即执行
    3. 不需要复杂资源
    4. 5-15分钟内可完成
    5. 可以通过物品栏，环境信息，位置信息和状态来进行验证

    直接返回目标描述，不要JSON格式，不要复杂分析：""",
        description="Minecraft游戏目标生成模板",
        parameters=["player_position", "inventory", "environment", "executed_goals"],
    ))
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_analyze_goal",
        template="""你是一个Minecraft游戏助手。请你将目标进行拆解成具体可执行的步骤：
**当前目标**：{goal}

环境信息: 
{environment}

请生成一个简单、具体、可执行的步骤列表。步骤应该：
1. 简单明确（一句话描述）
2. 可立即执行
3. 不需要复杂资源
4. 可以通过物品栏，环境信息，位置信息和状态来进行验证

你可以进行的操作有：
chat - 发送聊天消息
craft_item - 合成物品
smelt_item - 熔炼物品
use_chest - 使用箱子
swim_to_land - 游向陆地
kill_mob - 击杀生物
mine_block - 挖掘方块
place_block - 放置方块
follow_player - 跟随玩家

请使用json格式输出步骤列表，例如
{{
    "steps": [
        "步骤1": "找到最近的oak_log方块",
        "步骤2": "破坏oak_log方块",
        "步骤3": "收集掉落物"
    ],
    "notes": "注意：如果找不到oak_log,也可以寻找其他log方块"
}}
""",
        description="Minecraft游戏目标拆解模板",
        parameters=["goal", "environment"],
    ))
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_excute_step",
        template="""你是一个Minecraft游戏助手。请你选择合适的动作来完成当前任务：

**当前目标**：{goal}
**目标步骤**：{all_steps}
**环境信息**：{environment}

**已经执行的工具**：{executed_tools}

请判断哪些步骤已经完成，以及哪些步骤需要执行。

请分析当前步骤需要什么动作，然后从可用的MCP工具中选择最合适的工具来执行。

你可以：
1. 选择合适的工具来执行当前步骤
2. 如果当前目标已经完成，返回"完成"
3. 如果无法选择合适的工具，说明原因

请使用工具来执行步骤，或者直接返回文本响应。
""",
        description="Minecraft游戏步骤执行模板",
        parameters=["goal", "all_steps", "environment", "executed_tools"],
    ))

    prompt_manager.register_template(
        PromptTemplate(
        name="action_planning",
        template="""基于以下信息制定行动计划：

    目标: {goal}
    当前状态: {current_state}
    可用资源: {available_resources}
    时间限制: {time_limit}

    请提供：
    1. 主要步骤（3-5步）
    2. 所需资源
    3. 预期时间
    4. 潜在风险

    行动计划：""",
        description="行动计划制定模板",
        parameters=["goal", "current_state", "available_resources", "time_limit"],
    ))