# /dev_src - 开发辅助工具目录

这个目录用于存放项目开发过程中使用的辅助脚本和工具，它们不属于核心应用逻辑的一部分。

## 文件说明

### `make_config_sync.py`

这是一个用于保持主配置文件 (`config-template.toml`) 与插件目录 (`src/plugins/`) 同步的 Python 脚本。

#### 功能

当你添加或删除一个插件目录时，往往需要手动更新主配置文件中的 `[plugins]` 部分来启用或禁用它。这个脚本将此过程自动化。

每次运行时，它会执行以下两个操作：

1.  **移除失效条目**: 脚本会检查 `config-template.toml` 中 `[plugins]` 下的所有 `enable_...` 条目。如果发现某个条目对应的插件目录在 `src/plugins/` 中已不存在，它会自动将该行配置删除。
2.  **添加新条目**: 脚本会扫描 `src/plugins/` 目录，找出所有新添加的、但在配置文件中没有对应 `enable_...` 条目的插件。然后，它会自动将 `enable_<new_plugin_name> = true` 添加到 `[plugins]` 配置区域的末尾。

这确保了配置文件能够精确地反映当前项目中实际存在的插件。

#### 使用方法

直接从项目根目录运行此脚本即可：

```bash
python dev_src/make_config_sync.py
```

#### 依赖

- **Python 3.8+**
- **toml** (对于 Python < 3.11): `pip install toml` 