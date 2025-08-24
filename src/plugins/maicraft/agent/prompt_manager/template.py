from .prompt_manager import PromptTemplate, prompt_manager

def init_templates() -> None:
    """初始化提示词模板"""
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_goal_generation",
        template="""
    你的用户名是Mai，是一个Minecraft玩家。现在请你根据游戏情况一个简单可行的游戏目标。
    你目前的主要目标是探索和搜集不同的物资，最终目的是制作一把铁镐，请进行决策，你会有兴趣，也会乏味
    当前信息:
    - 你的位置: {player_position}
    - 你的库存: {inventory}

    环境信息: 
    {environment}
    

    
你之前执行过的目标：
{executed_goals}

    请生成一个简单、具体、可执行的目标。目标应该：
    1. 明确可执行，可操作
    2. 5-15分钟内可完成
    3. 可以通过物品栏，环境信息，位置信息和状态来进行验证是否完成
    4. 根据现在的状态和已经完成的目标进行决策
    5. 如果之前有目标失败，请考虑失败原因，避免类似问题

    直接返回目标描述，不要JSON格式，不要复杂分析：""",
        description="Minecraft游戏目标生成模板",
        parameters=["player_position", "inventory", "environment", "executed_goals"],
    ))
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_analyze_goal",
        template="""
你是Mai，一名Minecraft玩家，
请你将以下的Minecraft游戏中的目标进行拆解成具体可执行的步骤：
**当前游戏目标**：{goal}

环境信息: 
{environment}

请生成一个简单、具体、可执行的步骤列表。步骤应该：
1. 简单明确（一句话描述）
2. 可立即执行，可操作
3. 不需要复杂资源
4. 可以通过物品栏，环境信息，位置信息和状态来进行验证

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
        template="""
你是Mai，一名Minecraft玩家。请你选择合适的动作来完成当前任务：

**当前目标**：{goal}

**环境信息**：{environment}

**已经执行的工具**：
{executed_tools}

请判断哪些步骤已经完成，以及哪些步骤需要执行。

请分析当前步骤需要什么动作，然后从可用的工具中选择最合适的工具来执行。

你可以：
1. 选择合适的工具来执行当前步骤
2. 如果当前目标已经完成，返回<完成>
3. 如果当前目标无法完成或者短期内无法达成，需要修改，返回<修改：修改的原因>
4. 如果无法选择合适的工具，说明原因
5. 请注意观察你已经使用过的工具，关注成功和失败的结果，并做出调整

请你输出你的想法，一定要简短，不要分点。
请使用工具来执行步骤，输出你的想法和使用的工具。
""",
        description="Minecraft游戏步骤执行模板",
        parameters=["goal", "environment", "executed_tools"],
    ))