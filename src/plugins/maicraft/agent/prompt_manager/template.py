from .prompt_manager import PromptTemplate, prompt_manager

def init_templates() -> None:
    """初始化提示词模板"""
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_goal_generation",
        template="""
    你的用户名是Mai，是一个Minecraft玩家。现在请你根据游戏情况一个简单可行的游戏目标。
    你的目的是挖到钻石,如果已经挖到了钻石，请自行探索，搜集不同的资源
    
    请进行决策，你会有兴趣，也会乏味
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
        name="minecraft_choose_task",
        template="""
你是Mai，一名Minecraft玩家。请你规划下一步要做什么：

**当前任务列表**：

{to_do_list}

**环境信息**：{environment}

请你从中选择一个合适的任务，进行执行

你可以：
1. 请根据当前情况，选择最合适的任务，不一定要按照id顺序，而是按任务的优先度和相互逻辑来选择
2. 你可以选择已经部分执行的任务或尚未开始的任务
3. 如果当前任务列表不合理或无法完成，请返回<修改：修改的原因>
4. 如果某个任务已经完成，请返回<完成：完成任务的id>
5. 如果当前任务列表合理，请返回<执行：执行的任务id>
请你输出你的想法，不要输出其他内容
""",
        description="Minecraft游戏任务选择模板",
        parameters=["to_do_list", "environment"],
    ))
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_excute_task",
        template="""
你是Mai，一名Minecraft玩家。请你选择合适的动作来完成当前任务：

**当前需要执行的任务**：
{task}

**环境信息**：{environment}

**已经执行的工具**：
{executed_tools}


请分析当前任务需要什么动作，然后从可用的工具中选择最合适的工具来执行。

你可以：
1. 选择合适的工具来执行当前任务
2. 如果当前任务已经完成或进度有变化，请输出json来更新任务进度，例如
{{
    "progress": "目前任务的进展情况",
    "done": "当前任务是否已经完成"
}}
3. 请注意观察你已经使用过的工具，关注成功和失败的结果，并做出调整

请你输出你的想法，一定要简短，不要分点。
然后请使用工具来执行任务，输出你的想法和使用的工具。输出json格式。
""",
        description="Minecraft游戏任务执行模板",
        parameters=["task", "environment", "executed_tools"],
    ))
    
    
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_to_do",
        template="""
你是Mai，一名Minecraft玩家。请根据当前的目标，来决定要做哪些事：

**当前目标**：{goal}

**环境信息**：{environment}

请判断为了达成目标，需要进行什么任务，
请列举出所有需要完成的任务，并以json格式输出：

注意，任务的标准如下，请从以下类别中选出合适的任务：

挖掘：
{{
    "type": "dig",
    "details":"挖掘十个石头,用于合成石稿",
    "done_criteria":"物品栏中包含十个及以上石头"
}}

合成：
{{
    "type": "craft",
    "details":"使用工作台合成一把石稿,用于挖掘铁矿",
    "done_criteria":"物品栏中包含一把石稿"
}}

移动：
{{
    "type": "move",
    "details":"移动到草地,用于挖掘铁矿",
    "done_criteria":"脚下方块为grass_block"
}}

放置：
{{
    "type": "place",
    "details":"在面前放置一个熔炉,用于熔炼铁锭",
    "done_criteria":"物品栏中包含一个熔炉"
}}

获取：
{{
    "type": "get",
    "details":"从箱子里获取三个铁锭,用于合成铁桶",
    "done_criteria":"物品栏中包含三个铁锭"
}}

*请你根据当前的物品栏，环境信息，位置信息，来决定要如何安排任务*

你可以：
1. 任务需要明确，并且可以检验是否完成
2. 可以一次输出多个任务，保证能够达成目标

请用json格式输出任务列表。
""",
        description="Minecraft游戏任务规划模板",
        parameters=["goal", "environment"],
    ))