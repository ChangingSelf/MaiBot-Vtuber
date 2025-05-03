class Operator:
    """
    干员，表示明日方舟中的可操控角色
    """

    def __init__(
        self,
        name: str,  # 干员名称
        cost: int,  # 部署费用
        max_hp: int,  # 生命上限
        redeploy_time: int,  # 再部署时间
        block_count: int,  # 阻挡数
        profession: str = None,  # 职业类型
        position: str = None,  # 位置类型
    ):
        self.name = name
        self.cost = cost
        self.max_hp = max_hp
        self.redeploy_time = redeploy_time
        self.block_count = block_count
        self.profession = profession
        self.position = position
