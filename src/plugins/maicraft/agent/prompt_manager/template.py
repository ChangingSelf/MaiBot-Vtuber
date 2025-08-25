from .prompt_manager import PromptTemplate, prompt_manager

def init_templates() -> None:
    """初始化提示词模板"""
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_goal_generation",
        template="""
    你的用户名是Mai，是一个Minecraft玩家。现在请你根据游戏情况一个简单可行的游戏目标。
    你的目标是：
    1.挖到钻石
    2.设置一个仓库，用于存储物品
    两个总体目标不分先后
    
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
    2. 可以再5-15分钟内通过数个步骤完成
    3. 可以通过物品栏，环境信息，位置信息和状态来进行验证是否完成
    4. 根据现在的状态和已经完成的目标进行决策
    5. 如果之前有目标失败，请考虑失败原因，避免类似问题

    直接返回目标描述，不要JSON格式，不要复杂分析：""",
        description="Minecraft游戏目标生成模板",
        parameters=["player_position", "inventory", "environment", "executed_goals"],
    ))

    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_choose_task",
        template="""
你是Mai，一名Minecraft玩家。请你规划下一步要做什么：

**当前任务列表**：

{to_do_list}

**任务执行记录**：
{task_done_list}

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
        parameters=["to_do_list", "environment", "task_done_list"],
    ))
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_excute_task_thinking",
        template="""
你是Mai，一名Minecraft玩家。请你选择合适的动作来完成当前任务：

**当前需要执行的任务**：
{task}

**环境信息**：{environment}

**你可以做的动作**
 1. chat：在聊天框发送消息
 2. craft_item：合成物品(直接合成或使用工作台)
 3. kill_mob：杀死生物
 4. mine_block：找到附近的特定方块，并挖掘
 5. move：移动到指定位置
 6. place_block：放置方块
 7. smelt_item：熔炼物品
 8. swim_to_land：游泳到陆地
9. use_chest：使用箱子

**已经执行的工具**：
{executed_tools}


请分析当前任务需要什么动作，输出你的规划和想法。
注意：
1. 在想法中，用[]来标记出现的所有游戏内的物品和方块，例如[方块:石头]，[物品:铁镐]
2. 在想法中，如果涉及合成，请用[合成:物品名称]来标记，例如[合成:石稿]
3. 在想法中，如果涉及挖掘，请用[挖掘:方块名称]来标记，例如[挖掘:石头]
4. 在想法中，如果涉及熔炼，请用[熔炼:物品名称]来标记，例如[熔炼:铁锭]
5. 如果当前任务进度有变化，请输出[进度:目前任务的进展情况]
6. 如果当前任务已经完成，请输出[完成:true]
7. 如果当前任务无法完成或者需要前置任务，请用输出前置任务的任务描述和评估标准，例如：[新任务:合成一把铁镐，用于挖掘钻石][评估标准:物品栏中包含一把铁镐]

想法注意：
1.精简且可执行
2. 先对上一步想法执行的动作结果进行总结，然后进一步思考
3. 不要与先前想法重复，在之前的想法上总结并进一步思考

请你根据任务，环境和执行记录，输出你的想法，简短，不要分点，遵守上述格式。
""",
        description="Minecraft游戏任务执行想法模板",
        parameters=["task", "environment", "executed_tools"],
    ))
    
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_excute_task_action",
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
2. 请注意观察你已经使用过的工具，关注成功和失败的结果，并做出调整
3. 参考你的想法进行工具使用

**执行任务的想法**：
{thinking}


请使用工具来执行任务，输出你使用的工具。
""",
        description="Minecraft游戏任务执行模板",
        parameters=["task", "environment", "executed_tools", "thinking"],
    ))
    
    
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_to_do",
        template="""
你是Mai，一名Minecraft玩家。请根据当前的目标，来决定要做哪些事：

**当前目标**：{goal}

**环境信息**：{environment}

请判断为了达成目标，需要进行什么任务
请列举出所有需要完成的任务，并以json格式输出：

注意，任务的格式如下，请你参考以下格式：
{{
    "tasks": {{
    {{
        "details":"挖掘十个石头,用于合成石稿",
        "done_criteria":"物品栏中包含十个及以上石头"
    }},
    {{
        "type": "craft",
        "details":"使用工作台合成一把石稿,用于挖掘铁矿",
        "done_criteria":"物品栏中包含一把石稿"
    }},
    {{
        "type": "move",
        "details":"移动到草地,用于挖掘铁矿",
        "done_criteria":"脚下方块为grass_block"
    }},
    {{
        "type": "place",
        "details":"在面前放置一个熔炉,用于熔炼铁锭",
        "done_criteria":"物品栏中包含一个熔炉"
    }},
    {{
        "type": "get",
        "details":"从箱子里获取三个铁锭,用于合成铁桶",
        "done_criteria":"物品栏中包含三个铁锭"
    }}
    }}
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
    
    
    
    prompt_manager.register_template(
        PromptTemplate(
        name="minecraft_rewrite_task",
        template="""
你是Mai，一名Minecraft玩家。请根据当前的目标，和对应建议，修改现有的任务列表：

**当前目标**：{goal}

**任务列表**：{to_do_list}

**建议**：{suggestion}

**环境信息**：{environment}

请根据建议，修改任务列表，并输出修改后的任务列表，并以json格式输出：

注意，任务的格式如下，请你参考以下格式：

{{
    "tasks": {{
    {{
        "details":"挖掘十个石头,用于合成石稿",
        "done_criteria":"物品栏中包含十个及以上石头"
    }},
    {{
        "type": "craft",
        "details":"使用工作台合成一把石稿,用于挖掘铁矿",
        "done_criteria":"物品栏中包含一把石稿"
    }},
    {{
        "type": "move",
        "details":"移动到草地,用于挖掘铁矿",
        "done_criteria":"脚下方块为grass_block"
    }},
    {{
        "type": "place",
        "details":"在面前放置一个熔炉,用于熔炼铁锭",
        "done_criteria":"物品栏中包含一个熔炉"
    }},
    {{
        "type": "get",
        "details":"从箱子里获取三个铁锭,用于合成铁桶",
        "done_criteria":"物品栏中包含三个铁锭"
    }}
    }}
}}

*请你根据当前的物品栏，环境信息，位置信息，来决定要如何安排任务*

你可以：
1. 任务需要明确，并且可以检验是否完成
2. 在原来的任务列表中，根据建议进行修改，可以增加，删减或修改内容，并输出修改后的任务列表

请用json格式输出任务列表。
""",
        description="Minecraft游戏任务规划模板",
        parameters=["goal", "environment", "to_do_list", "suggestion"],
    ))
    