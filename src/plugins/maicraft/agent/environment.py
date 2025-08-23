"""
Minecraft环境信息存储类
用于存储和管理游戏环境数据
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


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
        self.food: int = 0
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
        
        # 更新玩家信息
        if "player" in data:
            player_data = data["player"]
            self.player = Player(
                uuid=player_data.get("uuid", ""),
                username=player_data.get("username", ""),
                display_name=player_data.get("displayName", ""),
                ping=player_data.get("ping", 0),
                gamemode=player_data.get("gamemode", 0)
            )
        
        # 更新位置信息
        if "position" in data:
            pos_data = data["position"]
            self.position = Position(
                x=pos_data.get("x", 0.0),
                y=pos_data.get("y", 0.0),
                z=pos_data.get("z", 0.0)
            )
        
        # 更新状态信息
        self.health = data.get("health", 0)
        self.food = data.get("food", 0)
        self.experience = data.get("experience", 0)
        self.level = data.get("level", 0)
        
        # 更新物品栏
        self.inventory = data.get("inventory", [])
        
        # 更新环境信息
        self.weather = data.get("weather", "")
        self.time_of_day = data.get("timeOfDay", 0)
        self.dimension = data.get("dimension", "")
        
        # 更新附近玩家
        self.nearby_players = []
        for player_data in data.get("nearbyPlayers", []):
            player = Player(
                uuid=player_data.get("uuid", ""),
                username=player_data.get("username", ""),
                display_name=player_data.get("displayName", ""),
                ping=player_data.get("ping", 0),
                gamemode=player_data.get("gamemode", 0)
            )
            self.nearby_players.append(player)
        
        # 更新附近实体
        self.nearby_entities = []
        for entity_data in data.get("nearbyEntities", []):
            entity = Entity(
                id=entity_data.get("id", 0),
                type=entity_data.get("type", ""),
                name=entity_data.get("name", ""),
                position=Position(
                    x=entity_data["position"].get("x", 0.0),
                    y=entity_data["position"].get("y", 0.0),
                    z=entity_data["position"].get("z", 0.0)
                ) if "position" in entity_data else Position(0.0, 0.0, 0.0)
            )
            self.nearby_entities.append(entity)
        
        # 更新最近事件
        self.recent_events = []
        for event_data in data.get("recentEvents", []):
            event = Event(
                type=event_data.get("type", ""),
                timestamp=event_data.get("timestamp", 0),
                server_id=event_data.get("serverId", ""),
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
            
            if event_data.get("oldPosition"):
                old_pos = event_data["oldPosition"]
                event.old_position = Position(
                    x=old_pos.get("x", 0.0),
                    y=old_pos.get("y", 0.0),
                    z=old_pos.get("z", 0.0)
                )
            
            if event_data.get("newPosition"):
                new_pos = event_data["newPosition"]
                event.new_position = Position(
                    x=new_pos.get("x", 0.0),
                    y=new_pos.get("y", 0.0),
                    z=new_pos.get("z", 0.0)
                )
            
            if event_data.get("block"):
                block_data = event_data["block"]
                event.block = Block(
                    type=block_data.get("type", 0),
                    name=block_data.get("name", ""),
                    position=Position(
                        x=block_data["position"].get("x", 0.0),
                        y=block_data["position"].get("y", 0.0),
                        z=block_data["position"].get("z", 0.0)
                    ) if "position" in block_data else Position(0.0, 0.0, 0.0)
                )
            
            # 设置其他事件特定属性
            if "experience" in event_data:
                event.experience = event_data.get("experience")
            if "level" in event_data:
                event.level = event_data.get("level")
            if "health" in event_data:
                event.health = event_data.get("health")
            if "food" in event_data:
                event.food = event_data.get("food")
            if "saturation" in event_data:
                event.saturation = event_data.get("saturation")
            
            self.recent_events.append(event)
        
        # 更新系统状态
        self.status = data.get("status", "")
        
        # 更新请求信息
        self.request_id = observation_data.get("request_id", "")
        self.elapsed_ms = observation_data.get("elapsed_ms", 0)
        
        # 更新时间戳
        self.last_update = datetime.now()
    
    def get_player_position(self) -> Optional[Position]:
        """获取玩家当前位置"""
        return self.position
    
    def get_nearby_players(self) -> List[Player]:
        """获取附近玩家列表"""
        return self.nearby_players
    
    def get_nearby_entities(self) -> List[Entity]:
        """获取附近实体列表"""
        return self.nearby_entities
    
    def get_recent_events(self, event_type: Optional[str] = None) -> List[Event]:
        """获取最近事件列表，可选择按类型过滤"""
        if event_type is None:
            return self.recent_events
        return [event for event in self.recent_events if event.type == event_type]
    
    def get_player_health(self) -> int:
        """获取玩家生命值"""
        return self.health
    
    def get_player_food(self) -> int:
        """获取玩家饥饿值"""
        return self.food
    
    def get_player_experience(self) -> int:
        """获取玩家经验值"""
        return self.experience
    
    def get_player_level(self) -> int:
        """获取玩家等级"""
        return self.level
    
    def get_weather(self) -> str:
        """获取当前天气"""
        return self.weather
    
    def get_time_of_day(self) -> int:
        """获取当前时间"""
        return self.time_of_day
    
    def get_dimension(self) -> str:
        """获取当前维度"""
        return self.dimension
    
    def is_player_alive(self) -> bool:
        """检查玩家是否存活"""
        return self.health > 0
    
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
            "health": self.health,
            "food": self.food,
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
            lines.append("【位置信息】")
            lines.append(f"  坐标: X={self.position.x:.2f}, Y={self.position.y:.2f}, Z={self.position.z:.2f}")
            lines.append("")
        else:
            lines.append("【位置信息】")
            lines.append("  未获取到位置信息")
            lines.append("")
        
        # 状态信息
        lines.append("【状态信息】")
        lines.append(f"  生命值: {self.health}/20")
        lines.append(f"  饥饿值: {self.food}/20")
        # lines.append(f"  经验值: {self.experience}")
        # lines.append(f"  等级: {self.level}")
        # lines.append(f"  存活状态: {'存活' if self.is_player_alive() else '死亡'}")
        lines.append("")
        
        # 物品栏
        lines.append("【物品栏】")
        if self.inventory:
            lines.append(f"  物品数量: {len(self.inventory)}")
            for i, item in enumerate(self.inventory):
                # 构建更可读的物品信息
                item_info = []
                if 'displayName' in item and item['displayName']:
                    item_info.append(item['displayName'])
                if 'name' in item and item['name']:
                    item_info.append(f"({item['name']})")
                if 'count' in item:
                    item_info.append(f"x{item['count']}")
                if 'slot' in item:
                    item_info.append(f"[槽位{item['slot']}]")
                
                # 组合物品信息
                item_str = " ".join(item_info)
                lines.append(f"  [{i}]: {item_str}")
        else:
            lines.append("  物品栏为空")
        lines.append("")
        
        # 环境信息
        lines.append("【环境信息】")
        lines.append(f"  天气: {self._get_weather_name(self.weather)}")
        lines.append(f"  时间: {self._get_time_name(self.time_of_day)}")
        lines.append(f"  维度: {self._get_dimension_name(self.dimension)}")
        lines.append("")
        
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
    
    def _get_weather_name(self, weather: str) -> str:
        """获取天气名称"""
        weather_names = {
            "clear": "晴朗",
            "rain": "下雨",
            "thunder": "雷暴"
        }
        return weather_names.get(weather, weather)
    
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
    
    def _get_dimension_name(self, dimension: str) -> str:
        """获取维度名称"""
        dimension_names = {
            "overworld": "主世界",
            "nether": "下界",
            "end": "末地"
        }
        return dimension_names.get(dimension, dimension)
    
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
