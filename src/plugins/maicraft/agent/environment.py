"""
Minecraft环境信息存储类
用于存储和管理游戏环境数据
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.utils.logger import get_logger

logger = get_logger("EnvironmentInfo")


@dataclass
class Player:
    """玩家信息"""
    uuid: str
    username: str
    display_name: str
    ping: int
    gamemode: int


@dataclass
class Position:
    """位置信息"""
    x: float
    y: float
    z: float


@dataclass
class Block:
    """方块信息"""
    type: int
    name: str
    position: Position


@dataclass
class Event:
    """事件信息"""
    type: str
    timestamp: int
    server_id: str
    player_name: str
    player: Optional[Player] = None
    old_position: Optional[Position] = None
    new_position: Optional[Position] = None
    block: Optional[Block] = None
    experience: Optional[int] = None
    level: Optional[int] = None
    health: Optional[int] = None
    food: Optional[int] = None
    saturation: Optional[int] = None


@dataclass
class Entity:
    """实体信息"""
    id: int
    type: str
    name: str
    position: Position


class EnvironmentInfo:
    """Minecraft环境信息存储类"""
    
    def __init__(self):
        # 玩家信息
        self.player: Optional[Player] = None
        
        # 位置信息
        self.position: Optional[Position] = None
        
        # 状态信息
        self.health: int = 0
        self.health_max: int = 20
        self.health_percentage: int = 0
        self.food: int = 0
        self.food_max: int = 20
        self.food_saturation: int = 0
        self.food_percentage: int = 0
        self.experience: int = 0
        self.level: int = 0
        
        # 物品栏
        self.inventory: List[Any] = field(default_factory=list)
        
        # 环境信息
        self.weather: str = ""
        self.time_of_day: int = 0
        self.dimension: str = ""
        
        # 附近玩家
        self.nearby_players: List[Player] = field(default_factory=list)
        
        # 附近实体
        self.nearby_entities: List[Entity] = field(default_factory=list)
        
        # 附近方块
        self.nearby_blocks: Dict[str, Any] = field(default_factory=dict)
        
        # 最近事件
        self.recent_events: List[Event] = field(default_factory=list)
        
        # 系统状态
        self.status: str = ""
        self.request_id: str = ""
        self.elapsed_ms: int = 0
        
        # 时间戳
        self.last_update: Optional[datetime] = None
    
    def get_summary(self) -> str:
        """获取环境信息摘要"""
        return self.to_readable_text()

    def update_from_observation(self, observation_data: Dict[str, Any]) -> None:
        """从观察数据更新环境信息"""
        if not observation_data.get("ok"):
            return
        
        data = observation_data.get("data", {})
        
        # 更新游戏状态信息 (来自 query_game_state)
        self.weather = data.get("weather", "")
        self.time_of_day = data.get("timeOfDay", 0)
        self.dimension = data.get("dimension", "")
        
        # 更新在线玩家信息 (来自 query_game_state)
        online_players = data.get("onlinePlayers", [])
        self.nearby_players = []
        for player_name in online_players:
            # 在线玩家只提供名称，创建基本的Player对象
            player = Player(
                uuid="",  # 在线玩家列表中没有UUID
                username=player_name,
                display_name=player_name,
                ping=0,  # 在线玩家列表中没有ping信息
                gamemode=0  # 在线玩家列表中没有游戏模式信息
            )
            self.nearby_players.append(player)
        
        # 更新玩家状态信息 (来自 query_player_status)
        if "player" in data:
            player_data = data["player"]
            self.player = Player(
                uuid=player_data.get("uuid", ""),
                username=player_data.get("username", ""),
                display_name=player_data.get("displayName", ""),
                ping=player_data.get("ping", 0),
                gamemode=player_data.get("gamemode", 0)
            )
        
        # 更新位置信息 (来自 query_player_status)
        if "position" in data:
            pos_data = data["position"]
            self.position = Position(
                x=pos_data.get("x", 0.0),
                y=pos_data.get("y", 0.0),
                z=pos_data.get("z", 0.0)
            )
        
        # 更新状态信息 (来自 query_player_status)
        # 处理新的health格式
        health_data = data.get("health", {})

        self.health = health_data.get("current", 0)
        self.health_max = health_data.get("max", 20)
        self.health_percentage = health_data.get("percentage", 0)

        
        # 处理新的food格式
        food_data = data.get("food", {})

        self.food = food_data.get("current", 0)
        self.food_max = food_data.get("max", 20)
        self.food_saturation = food_data.get("saturation", 0)
        self.food_percentage = food_data.get("percentage", 0)

        
        self.experience = data.get("experience", 0)
        self.level = data.get("level", 0)
        
        # 更新物品栏 (来自 query_player_status)
        inventory_data = data.get("inventory", {})
        # 处理新的物品栏数据格式
        self.inventory = [] 

        # 新格式：包含统计信息和槽位数据
        slots = inventory_data.get("slots", [])
        if isinstance(slots, list):
            for slot_data in slots:
                if isinstance(slot_data, dict):
                    # 构建标准化的物品信息
                    item_info = {
                        'slot': slot_data.get('slot', 0),
                        'count': slot_data.get('count', 0),
                        'name': slot_data.get('name', ''),
                        'displayName': slot_data.get('name', '')  # 使用name作为displayName
                    }
                    self.inventory.append(item_info)
        
        # 记录物品栏统计信息
        full_slots = inventory_data.get('fullSlotCount', 0)
        empty_slots = inventory_data.get('emptySlotCount', 0)
        total_slots = inventory_data.get('slotCount', 0)
        


        # 更新最近事件 (来自 query_recent_events)
        self.recent_events = []
        for event_data in data.get("recentEvents", []):
            try:
                event = Event(
                    type=event_data.get("type", ""),
                    timestamp=event_data.get("gameTick", 0),  # 使用gameTick作为时间戳
                    server_id="",  # 新格式中没有serverId
                    player_name=event_data.get("playerName", "")
                )
                
                # 根据事件类型设置特定属性
                if event_data.get("player"):
                    player_data = event_data["player"]
                    event.player = Player(
                        uuid=player_data.get("uuid", ""),
                        username=player_data.get("username", ""),
                        display_name=player_data.get("displayName", ""),
                        ping=player_data.get("ping", 0),
                        gamemode=player_data.get("gamemode", 0)
                    )
                    # 设置玩家名称
                    event.player_name = player_data.get("username", "")
                
                # 处理playerInfo字段 (playerJoin事件)
                if event_data.get("playerInfo"):
                    player_info = event_data["playerInfo"]
                    event.player = Player(
                        uuid=player_info.get("uuid", ""),
                        username=player_info.get("username", ""),
                        display_name=player_info.get("displayName", ""),
                        ping=player_info.get("ping", 0),
                        gamemode=player_info.get("gamemode", 0)
                    )
                    # 设置玩家名称
                    event.player_name = player_info.get("username", "")
                
                # 处理位置信息 (playerRespawn事件)
                if event_data.get("position"):
                    pos_data = event_data["position"]
                    if isinstance(pos_data, dict):
                        event.new_position = Position(
                            x=pos_data.get("x", 0.0),
                            y=pos_data.get("y", 0.0),
                            z=pos_data.get("z", 0.0)
                        )
                    elif isinstance(pos_data, list) and len(pos_data) >= 3:
                        # 如果位置是列表格式 [x, y, z]
                        event.new_position = Position(
                            x=float(pos_data[0]) if pos_data[0] is not None else 0.0,
                            y=float(pos_data[1]) if pos_data[1] is not None else 0.0,
                            z=float(pos_data[2]) if pos_data[2] is not None else 0.0
                        )
                
                # 处理健康更新事件
                if event.type == "healthUpdate":
                    # 处理新的health格式
                    health_data = event_data.get("health", {})
                    if isinstance(health_data, dict):
                        event.health = health_data.get("current", 0)
                    else:
                        event.health = event_data.get("health", 0)
                    
                    # 处理新的food格式
                    food_data = event_data.get("food", {})
                    if isinstance(food_data, dict):
                        event.food = food_data.get("current", 0)
                        event.saturation = food_data.get("saturation", 0)
                    else:
                        event.food = event_data.get("food", 0)
                        event.saturation = event_data.get("saturation", 0)
                
                self.recent_events.append(event)
            except Exception as e:
                # 记录事件处理错误，但继续处理其他事件
                import traceback
                print(f"处理事件数据时出错: {e}")
                print(f"事件数据: {event_data}")
                print(f"错误详情: {traceback.format_exc()}")
                continue
        
        # 更新周围环境 - 玩家 (来自 query_surroundings("players"))
        if "nearbyPlayers" in data:
            nearby_players_data = data["nearbyPlayers"]
            if isinstance(nearby_players_data, list):
                # 如果nearbyPlayers是列表，直接使用
                self.nearby_players = []
                for player_data in nearby_players_data:
                    try:
                        if isinstance(player_data, dict):
                            player = Player(
                                uuid=player_data.get("uuid", ""),
                                username=player_data.get("username", ""),
                                display_name=player_data.get("displayName", ""),
                                ping=player_data.get("ping", 0),
                                gamemode=player_data.get("gamemode", 0)
                            )
                            self.nearby_players.append(player)
                        else:
                            # 如果只是玩家名称字符串
                            player = Player(
                                uuid="",
                                username=str(player_data),
                                display_name=str(player_data),
                                ping=0,
                                gamemode=0
                            )
                            self.nearby_players.append(player)
                    except Exception as e:
                        # 记录玩家处理错误，但继续处理其他玩家
                        import traceback
                        print(f"处理玩家数据时出错: {e}")
                        print(f"玩家数据: {player_data}")
                        print(f"错误详情: {traceback.format_exc()}")
                        continue
        
        # 更新周围环境 - 实体 (来自 query_surroundings("entities"))
        if "nearbyEntities" in data:
            nearby_entities_data = data["nearbyEntities"]
            if isinstance(nearby_entities_data, list):
                self.nearby_entities = []
                for entity_data in nearby_entities_data:
                    try:
                        if isinstance(entity_data, dict):
                            # 安全地获取位置信息
                            position = Position(0.0, 0.0, 0.0)
                            if "position" in entity_data:
                                pos_data = entity_data["position"]
                                if isinstance(pos_data, dict):
                                    position = Position(
                                        x=pos_data.get("x", 0.0),
                                        y=pos_data.get("y", 0.0),
                                        z=pos_data.get("z", 0.0)
                                    )
                                elif isinstance(pos_data, list) and len(pos_data) >= 3:
                                    # 如果位置是列表格式 [x, y, z]
                                    position = Position(
                                        x=float(pos_data[0]) if pos_data[0] is not None else 0.0,
                                        y=float(pos_data[1]) if pos_data[1] is not None else 0.0,
                                        z=float(pos_data[2]) if pos_data[2] is not None else 0.0
                                    )
                            
                            entity = Entity(
                                id=entity_data.get("id", 0),
                                type=entity_data.get("type", ""),
                                name=entity_data.get("name", ""),
                                position=position
                            )
                            self.nearby_entities.append(entity)
                    except Exception as e:
                        # 记录实体处理错误，但继续处理其他实体
                        import traceback
                        print(f"处理实体数据时出错: {e}")
                        print(f"实体数据: {entity_data}")
                        print(f"错误详情: {traceback.format_exc()}")
                        continue
        
        # 更新周围环境 - 方块 (来自 query_surroundings("blocks"))
        if "nearbyBlocks" in data:
            blocks_data = data["nearbyBlocks"]
            if isinstance(blocks_data, dict) and "blockMap" in blocks_data:
                # 处理新的方块数据格式
                self.nearby_blocks = blocks_data
        elif "blocks" in data:
            # 处理直接包含blocks字段的数据
            blocks_data = data["blocks"]
            if isinstance(blocks_data, dict) and "blockMap" in blocks_data:
                self.nearby_blocks = blocks_data
        
        # 更新系统状态
        self.status = "正常"  # 默认状态
        
        # 更新请求信息
        self.request_id = observation_data.get("request_id", "")
        self.elapsed_ms = observation_data.get("elapsed_ms", 0)
        
        # 更新时间戳
        self.last_update = datetime.now()
    

    
    def get_recent_events(self, event_type: Optional[str] = None) -> List[Event]:
        """获取最近事件列表，可选择按类型过滤"""
        if event_type is None:
            return self.recent_events
        return [event for event in self.recent_events if event.type == event_type]
    

    
    def get_distance_to_player(self, target_position: Position) -> float:
        """计算到指定位置的距离"""
        if not self.position:
            return float('inf')
        
        dx = self.position.x - target_position.x
        dy = self.position.y - target_position.y
        dz = self.position.z - target_position.z
        return (dx * dx + dy * dy + dz * dz) ** 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        """将环境信息转换为字典格式"""
        return {
            "player": {
                "uuid": self.player.uuid if self.player else None,
                "username": self.player.username if self.player else None,
                "display_name": self.player.display_name if self.player else None,
                "ping": self.player.ping if self.player else None,
                "gamemode": self.player.gamemode if self.player else None
            } if self.player else None,
            "position": {
                "x": self.position.x if self.position else None,
                "y": self.position.y if self.position else None,
                "z": self.position.z if self.position else None
            } if self.position else None,
            "health": {
                "current": self.health,
                "max": self.health_max,
                "percentage": self.health_percentage
            },
            "food": {
                "current": self.food,
                "max": self.food_max,
                "saturation": self.food_saturation,
                "percentage": self.food_percentage
            },
            "experience": self.experience,
            "level": self.level,
            "inventory": self.inventory,
            "weather": self.weather,
            "time_of_day": self.time_of_day,
            "dimension": self.dimension,
            "nearby_players": [
                {
                    "uuid": p.uuid,
                    "username": p.username,
                    "display_name": p.display_name,
                    "ping": p.ping,
                    "gamemode": p.gamemode
                } for p in self.nearby_players
            ],
            "nearby_entities": [
                {
                    "id": e.id,
                    "type": e.type,
                    "name": e.name,
                    "position": {
                        "x": e.position.x,
                        "y": e.position.y,
                        "z": e.position.z
                    }
                } for e in self.nearby_entities
            ],
            "nearby_blocks": self.nearby_blocks,
            "recent_events_count": len(self.recent_events),
            "status": self.status,
            "last_update": self.last_update.isoformat() if self.last_update else None
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"EnvironmentInfo(player={self.player.username if self.player else 'None'}, " \
               f"position=({self.position.x:.2f}, {self.position.y:.2f}, {self.position.z:.2f}) " \
               f"if self.position else 'None', health={self.health}, status={self.status})"

    def to_readable_text(self) -> str:
        """以可读文本形式返回所有环境信息"""
        lines = []
        
        # 玩家信息
        if self.player:
            lines.append("【玩家信息】")
            lines.append(f"  用户名: {self.player.username}")
            # lines.append(f"  显示名: {self.player.display_name}")
            # lines.append(f"  游戏模式: {self._get_gamemode_name(self.player.gamemode)}")
            lines.append("")
        else:
            lines.append("【玩家信息】")
            lines.append("  未获取到玩家信息")
            lines.append("")
        
        # 位置信息
        if self.position:
            lines.append("【周围环境信息】")
            lines.append(f"  坐标: X={self.position.x:.2f}, Y={self.position.y:.2f}, Z={self.position.z:.2f}")
            lines.append("")
        else:
            lines.append("【周围环境信息】")
            lines.append("  未获取到位置信息")
            lines.append("")
        
        # 附近方块
        if self.nearby_blocks and "blockMap" in self.nearby_blocks:
            lines.append("【附近方块】")
            block_map = self.nearby_blocks["blockMap"]
            total_count = self.nearby_blocks.get("totalCount", 0)
            lines.append(f"  总方块数量: {total_count}")
            
            # 按方块类型分组显示
            for block_type, block_info in block_map.items():
                if isinstance(block_info, dict) and "count" in block_info:
                    count = block_info["count"]
                    positions = block_info.get("positions", [])
                    
                    # 获取方块的中文名称
                    # block_name = self._get_block_name(block_type)
                    lines.append(f"  {block_type}: {count} 个")
                    
                    # 显示位置信息（限制显示数量避免过长）
                    if positions and len(positions) <= 10:
                        for pos in positions:
                            if isinstance(pos, list) and len(pos) >= 3:
                                x, y, z = pos[0], pos[1], pos[2]
                                # 将相对位置转换为绝对位置
                                if self.position:
                                    abs_x = self.position.x + x
                                    abs_y = self.position.y + y
                                    abs_z = self.position.z + z
                                    lines.append(f"    位置: X={abs_x:.1f}, Y={abs_y:.1f}, Z={abs_z:.1f}")
                                else:
                                    lines.append(f"    相对位置: X={x}, Y={y}, Z={z}")
                    elif positions and len(positions) > 5:
                        lines.append(f"    位置数量过多，显示前5个:")
                        for i, pos in enumerate(positions[:10]):
                            if isinstance(pos, list) and len(pos) >= 3:
                                x, y, z = pos[0], pos[1], pos[2]
                                # 将相对位置转换为绝对位置
                                if self.position:
                                    abs_x = self.position.x + x
                                    abs_y = self.position.y + y
                                    abs_z = self.position.z + z
                                    lines.append(f"      {i+1}. 位置: X={abs_x:.1f}, Y={abs_y:.1f}, Z={abs_z:.1f}")
                                else:
                                    lines.append(f"      {i+1}. 相对位置: X={x}, Y={y}, Z={z}")
                        lines.append(f"    ... 还有 {len(positions) - 5} 个位置")
            lines.append("")
        else:
            lines.append("【附近方块】")
            lines.append("  未获取到方块信息")
            lines.append("")
        
        # 状态信息
        lines.append("【状态信息】")
        lines.append(f"  生命值: {self.health}/{self.health_max}")
        lines.append(f"  饥饿值: {self.food}/{self.food_max}")
        if self.food_saturation > 0:
            lines.append(f"  饥饿饱和度: {self.food_saturation}")
        # lines.append(f"  经验值: {self.experience}")
        # lines.append(f"  等级: {self.level}")
        # lines.append(f"  存活状态: {'存活' if self.is_player_alive() else '死亡'}")
        lines.append("")
        
        # 物品栏
        lines.append("【物品栏】")
        if self.inventory:
            lines.append(f"  物品数量: {len(self.inventory)}")
            # 按槽位排序显示物品
            sorted_inventory = sorted(self.inventory, key=lambda x: x.get('slot', 0) if isinstance(x, dict) else 0)
            
            for item in sorted_inventory:
                # 构建更可读的物品信息
                item_info = []
                
                # 添加类型检查，确保item是字典类型
                if isinstance(item, dict):
                    if 'slot' in item:
                        item_info.append(f"[槽位{item['slot']}]")
                    if 'displayName' in item and item['displayName']:
                        item_info.append(item['displayName'])
                    elif 'name' in item and item['name']:
                        item_info.append(item['name'])
                    if 'count' in item and item['count'] > 0:
                        item_info.append(f"x{item['count']}")
                elif isinstance(item, str):
                    # 如果item是字符串，直接显示
                    item_info.append(item)
                else:
                    # 其他类型，转换为字符串显示
                    item_info.append(str(item))
                
                # 组合物品信息
                item_str = " ".join(item_info)
                lines.append(f"  {item_str}")
        else:
            lines.append("  物品栏为空")
        lines.append("")
        
        # # 环境信息
        # lines.append("【环境信息】")
        # lines.append(f"  天气: {self._get_weather_name(self.weather)}")
        # lines.append(f"  时间: {self._get_time_name(self.time_of_day)}")
        # lines.append(f"  维度: {self._get_dimension_name(self.dimension)}")
        # lines.append("")
        
        # 附近玩家
        lines.append("【附近玩家】")
        if self.nearby_players:
            lines.append(f"  附近玩家数量: {len(self.nearby_players)}")
            for i, player in enumerate(self.nearby_players, 1):
                lines.append(f"  {i}. {player.display_name} ({player.username})")
                lines.append(f"     延迟: {player.ping}ms, 游戏模式: {self._get_gamemode_name(player.gamemode)}")
        else:
            lines.append("  附近没有其他玩家")
        lines.append("")
        
        # 附近实体
        lines.append("【附近实体】")
        if self.nearby_entities:
            lines.append(f"  附近实体数量: {len(self.nearby_entities)}")
            for i, entity in enumerate(self.nearby_entities, 1):
                pos = entity.position
                lines.append(f"  {i}. {entity.name} (ID: {entity.id}, 类型: {entity.type})")
                lines.append(f"     位置: X={pos.x:.2f}, Y={pos.y:.2f}, Z={pos.z:.2f}")
        else:
            lines.append("  附近没有实体")
        lines.append("")
        
        # # 最近事件
        # lines.append("【最近事件】")
        # if self.recent_events:
        #     lines.append(f"  事件数量: {len(self.recent_events)}")
        #     # 只显示最近5个事件
        #     recent_events = self.recent_events[-5:] if len(self.recent_events) > 5 else self.recent_events
        #     for i, event in enumerate(recent_events, 1):
        #         event_time = datetime.fromtimestamp(event.timestamp / 1000).strftime("%H:%M:%S")
        #         lines.append(f"  {i}. [{event_time}] {self._get_event_description(event)}")
        # else:
        #     lines.append("  没有最近事件")
        # lines.append("")
        
        # 系统状态
        # lines.append("【系统状态】")
        # lines.append(f"  状态: {self.status}")
        # lines.append(f"  请求ID: {self.request_id}")
        # lines.append(f"  响应时间: {self.elapsed_ms}ms")
        # if self.last_update:
        #     lines.append(f"  最后更新: {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
        # lines.append("")
        
        # 统计信息
        lines.append("【统计信息】")
        lines.append(f"  附近玩家: {len(self.nearby_players)} 人")
        lines.append(f"  附近实体: {len(self.nearby_entities)} 个")
        if self.nearby_blocks and "totalCount" in self.nearby_blocks:
            lines.append(f"  附近方块: {self.nearby_blocks['totalCount']} 个")
        else:
            lines.append(f"  附近方块: 0 个")
        lines.append(f"  最近事件: {len(self.recent_events)} 个")
        lines.append(f"  物品栏: {len(self.inventory)} 个物品")
        lines.append("")
        
        lines.append("=" * 10)
        
        return "\n".join(lines)
    
    def _get_gamemode_name(self, gamemode: int) -> str:
        """获取游戏模式名称"""
        gamemodes = {
            0: "生存模式",
            1: "创造模式", 
            2: "冒险模式",
            3: "观察者模式"
        }
        return gamemodes.get(gamemode, f"未知模式({gamemode})")
    
    
    def _get_time_name(self, time_of_day: int) -> str:
        """获取时间名称"""
        # Minecraft时间转换为现实时间
        # 0-1000: 黎明, 1000-6000: 白天, 6000-12000: 黄昏, 12000-18000: 夜晚
        if 0 <= time_of_day < 1000:
            return f"黎明 ({time_of_day})"
        elif 1000 <= time_of_day < 6000:
            return f"白天 ({time_of_day})"
        elif 6000 <= time_of_day < 12000:
            return f"黄昏 ({time_of_day})"
        elif 12000 <= time_of_day < 18000:
            return f"夜晚 ({time_of_day})"
        else:
            return f"未知时间 ({time_of_day})"
    
    def _get_event_description(self, event: Event) -> str:
        """获取事件描述"""
        base_desc = f"{event.type} - {event.player_name}"
        
        if event.type == "playerMove" and event.old_position and event.new_position:
            old_pos = event.old_position
            new_pos = event.new_position
            return f"{base_desc} 从 ({old_pos.x:.1f}, {old_pos.y:.1f}, {old_pos.z:.1f}) 移动到 ({new_pos.x:.1f}, {new_pos.y:.1f}, {new_pos.z:.1f})"
        
        elif event.type == "blockBreak" and event.block:
            block = event.block
            pos = block.position
            return f"{base_desc} 破坏了 {block.name} 在 ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})"
        
        elif event.type == "experienceUpdate":
            return f"{base_desc} 经验值更新: {event.experience}, 等级: {event.level}"
        
        elif event.type == "healthUpdate":
            return f"{base_desc} 生命值更新: {event.health}, 饥饿值: {event.food}"
        
        else:
            return base_desc


# 全局环境信息实例
global_environment = EnvironmentInfo()
