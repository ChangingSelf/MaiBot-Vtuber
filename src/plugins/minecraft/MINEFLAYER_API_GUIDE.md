# Mineflayer API 使用指南

## 智能体API优化说明

基于mineflayer官方文档，我们修复了智能体中的错误API使用，确保生成的代码能够正确执行。

## 常见错误API及其修复

### ❌ 错误的API（不存在）
```javascript
// 这些API在mineflayer中不存在！
bot.move_forward(1)      // 错误
bot.move_backward(1)     // 错误
bot.turn_left()          // 错误 
bot.turn_right()         // 错误
bot.jump()               // 错误
bot.dig_down()           // 错误
bot.no_op()              // 错误
```

### ✅ 正确的API（基于官方文档）

#### 1. 移动控制
```javascript
// 开始移动
bot.setControlState("forward", true);
bot.setControlState("back", true);
bot.setControlState("left", true);
bot.setControlState("right", true);
bot.setControlState("jump", true);
bot.setControlState("sprint", true);
bot.setControlState("sneak", true);

// 停止移动
bot.setControlState("forward", false);

// 持续移动并自动停止
bot.setControlState("forward", true);
setTimeout(() => bot.setControlState("forward", false), 2000);
```

#### 2. 视角控制
```javascript
// 转向（yaw是水平角度，pitch是垂直角度）
bot.look(yaw, pitch);

// 相对转向
bot.look(bot.entity.yaw + Math.PI/4, bot.entity.pitch);  // 右转45度
bot.look(bot.entity.yaw - Math.PI/4, bot.entity.pitch);  // 左转45度

// 向上/向下看
bot.look(bot.entity.yaw, bot.entity.pitch - Math.PI/6);  // 向上看30度
bot.look(bot.entity.yaw, bot.entity.pitch + Math.PI/6);  // 向下看30度

// 看向特定位置
bot.lookAt(position);
```

#### 3. 挖掘操作
```javascript
// 挖掘指定方块
bot.dig(block);

// 挖掘相对位置的方块
bot.dig(bot.blockAt(bot.entity.position.offset(0, -1, 0)));  // 脚下
bot.dig(bot.blockAt(bot.entity.position.offset(0, 1, 0)));   // 头上
bot.dig(bot.blockAt(bot.entity.position.offset(0, 0, 1)));   // 前方

// 检查是否可以挖掘
if (bot.canDigBlock(block)) {
    bot.dig(block);
}
```

#### 4. 放置方块
```javascript
// 放置方块
const referenceBlock = bot.blockAt(bot.entity.position.offset(0, -1, 0));
bot.placeBlock(referenceBlock, new Vec3(0, 1, 0));

// 激活方块（开门、按按钮等）
bot.activateBlock(block);
```

#### 5. 聊天和交互
```javascript
// 发送聊天消息
bot.chat("你好！");

// 私聊
bot.whisper("玩家名", "私聊消息");
```

#### 6. 物品操作
```javascript
// 装备物品
bot.equip(item, 'hand');      // 装备到主手
bot.equip(item, 'off-hand');  // 装备到副手
bot.equip(item, 'head');      // 装备到头部
bot.equip(item, 'torso');     // 装备到胸部
bot.equip(item, 'legs');      // 装备到腿部
bot.equip(item, 'feet');      // 装备到脚部

// 卸下装备
bot.unequip('hand');

// 丢弃物品
bot.toss(itemType, metadata, count);
bot.tossStack(item);

// 消耗物品（食物等）
bot.consume();

// 激活物品（使用工具等）
bot.activateItem();
```

#### 7. 等待和时间
```javascript
// 等待指定tick数（20 ticks = 1秒）
bot.waitForTicks(20);

// 使用setTimeout进行延时
setTimeout(() => {
    // 延时后执行的代码
}, 1000);

// 简单等待（注释）
// 等待下一步指令
```

## 智能体改进亮点

### 1. API验证和修复机制
```python
def _validate_and_fix_action(self, action_code: str) -> str:
    """验证并修复动作代码"""
    fixes = {
        'bot.move_forward': 'bot.setControlState("forward", true)',
        'bot.turn_left': 'bot.look(bot.entity.yaw - Math.PI/2, bot.entity.pitch)',
        # ... 更多修复映射
    }
    # 自动修复错误API
```

### 2. 改进的上下文构建
- 提取关键的健康状况信息
- 包含代码执行状态和错误信息
- 简化记忆格式，减少冗余信息

### 3. 更准确的系统提示词
- 基于mineflayer官方API文档
- 提供具体的代码示例
- 强调常见错误和正确用法
- 包含决策优先级指导

### 4. 改进的代码解析
- 更好的markdown代码块处理
- 多行代码的智能连接
- 长度限制和安全检查

## 使用建议

### 优先级顺序
1. **高级函数**（如果可用）：`mineBlock()`, `craftItem()`, `placeItem()`
2. **官方API**：`bot.setControlState()`, `bot.look()`, `bot.dig()`
3. **等待和观察**：注释或`bot.waitForTicks()`

### 常用代码模式
```javascript
// 移动模式
bot.setControlState("forward", true);
setTimeout(() => bot.setControlState("forward", false), 3000);

// 挖掘模式
const block = bot.blockAt(bot.entity.position.offset(0, -1, 0));
if (block && block.name !== 'air') bot.dig(block);

// 聊天模式
bot.chat("我正在探索世界！");

// 观察模式
// 观察周围环境，等待下一个指令
```

## 测试验证

所有API都已根据mineflayer官方文档验证，确保：
- ✅ 语法正确性
- ✅ API存在性  
- ✅ 参数正确性
- ✅ 功能完整性

这样智能体就能生成正确的代码，避免"function not found"错误。 