# Minecraft状态分析器（新增面朝方向墙体检测）

## ✅ 重构完成 + 新功能

已成功将原有的1324行`state_analyzers.py`重构为9个专门的分析器，**完全移除了兼容性代码**，并新增了**面朝方向墙体检测功能**：

```
analyzers/
├── base_analyzer.py         # 基础分析器抽象类 (92行)
├── state_analyzer.py        # 主状态分析器 (86行)
├── life_stats_analyzer.py   # 生命统计分析器 (63行)
├── motion_analyzer.py       # 运动分析器 (172行)
├── equipment_analyzer.py    # 装备分析器 (141行)
├── inventory_analyzer.py    # 库存分析器 (101行)
├── voxel_analyzer.py        # 体素分析器 (391行)
├── environment_analyzer.py  # 环境分析器 (155行)
├── collision_analyzer.py    # 碰撞检测分析器 (235行) ⭐ 新增功能
└── __init__.py              # 模块导出
```

## 🎯 设计原则

- **无兼容层**: 完全移除了旧的兼容性方法
- **直接调用**: 所有引用处直接使用具体的分析器
- **职责明确**: 每个分析器专注于特定功能领域
- **智能检测**: 新增基于玩家实际朝向的墙体检测

## 📦 分析器功能

| 分析器 | 功能 |
|--------|------|
| **StateAnalyzer** | 组合所有分析器，提供完整分析 |
| **LifeStatsAnalyzer** | 生命值、饥饿值、氧气值 |
| **MotionAnalyzer** | 位置、朝向、速度 |
| **EquipmentAnalyzer** | 装备状态、耐久度 |
| **InventoryAnalyzer** | 物品栏管理 |
| **VoxelAnalyzer** | 3x3x3方块环境分析 |
| **EnvironmentAnalyzer** | 时间、天气、游戏信息 |
| **CollisionAnalyzer** | 碰撞检测、移动空间、⭐**面朝方向墙体检测** |

## 🆕 新功能：面朝方向墙体检测

### 功能特点
- **智能方向识别**: 根据玩家实际yaw角度确定面朝方向
- **精确墙体检测**: 检测玩家正前方是否有可碰撞方块
- **墙体高度分析**: 分析墙体高度，提供跳跃或绕行建议
- **方块类型识别**: 区分可碰撞和非可碰撞方块

### 使用方式

```python
from src.plugins.minecraft.state.analyzers import CollisionAnalyzer

# 创建分析器
analyzer = CollisionAnalyzer(obs, config)

# 检测面朝方向是否有墙
facing_result = analyzer.analyze_facing_direction_wall()

# 示例输出：
# ['警告：你面朝北方向有墙体阻挡（stone方块）', '前方墙体较高，可能需要跳跃或绕行']
# ['你面朝方向畅通无阻']
# ['你面朝方向有方块但可以通过（water）']
```

### 方向映射系统

| 偏航角(yaw) | 方向 | voxel坐标 |
|-------------|------|-----------|
| 315°-45° | 北 | (0, 1) |
| 45°-135° | 东 | (1, 2) |
| 135°-225° | 南 | (2, 1) |
| 225°-315° | 西 | (1, 0) |

## 🚀 集成使用

### 完整分析（自动包含面朝方向检测）
```python
from src.plugins.minecraft.state.analyzers import StateAnalyzer
analyzer = StateAnalyzer(obs, config)
status = analyzer.analyze()  # 自动包含面朝方向墙体检测
```

### 详细分类分析
```python
from src.plugins.minecraft.state import MinecraftGameState
game_state = MinecraftGameState(config)
detailed_analysis = game_state.get_detailed_status_analysis()
# 结果包含 "facing_wall" 键，专门显示面朝方向检测结果
```

### 单独使用面朝方向检测
```python
collision_analyzer = analyzer.collision_analyzer
facing_info = collision_analyzer.analyze_facing_direction_wall()
```

## 🔧 配置说明

碰撞检测配置：

```python
config = {
    "state_analyzer": {
        "collision": {
            "check_radius": 1,           # 检测半径
            "wall_block_threshold": 2    # 墙体方块阈值
        }
    }
}
```

## 🎉 功能优势

- ✅ **精确定向**: 基于真实yaw角度，而非固定方向
- ✅ **智能分析**: 区分可通过和不可通过的方块
- ✅ **高度检测**: 分析墙体高度，提供行动建议
- ✅ **实时反馈**: 即时反映玩家面朝方向的障碍情况
- ✅ **无缝集成**: 自动集成到完整状态分析中

**面朝方向墙体检测功能让AI能够更智能地理解环境，做出更合理的移动决策！** 🎯 