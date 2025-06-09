#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VTube Studio 口型同步功能测试脚本

此脚本用于测试 VTube Studio 插件的口型同步功能，包括：
- 基本连接测试
- 口型同步会话管理
- 音频处理和参数更新
- numpy类型转换测试

使用方法:
1. 确保VTube Studio正在运行
2. 确保VTube Studio中已启用API访问
3. 运行此脚本: python test_lip_sync.py

依赖:
- numpy
- librosa (如果启用了音频分析)
- pyvts
"""

import asyncio
import logging
import sys
import os
import tempfile
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 尝试导入必要的库
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import toml as tomllib  # 向后兼容
    except ImportError:
        print("缺少依赖：pip install toml")
        sys.exit(1)

try:
    import pyvts
except ImportError:
    print("错误: 需要pyvts库，请运行: pip install pyvts")
    sys.exit(1)

# 模拟Amaidesu Core类，避免复杂的依赖
class MockAmaidesuCore:
    """模拟的AmaidesuCore类，用于测试"""
    
    def __init__(self):
        self.services = {}
        self.logger = logging.getLogger("MockCore")
    
    def register_service(self, name: str, service):
        """注册服务"""
        self.services[name] = service
        self.logger.info(f"已注册服务: {name}")
    
    def get_service(self, name: str):
        """获取服务"""
        return self.services.get(name)
    
    def register_websocket_handler(self, event: str, handler):
        """模拟注册WebSocket处理器"""
        pass

class LipSyncTester:
    """VTube Studio 口型同步测试器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.plugin = None
        self.core = None

    async def initialize(self):
        """初始化测试环境"""
        self.logger.info("初始化测试环境...")
        
        try:
            # 创建模拟的Core实例
            self.core = MockAmaidesuCore()
            
            # 加载VTube Studio插件配置
            config_path = Path(__file__).parent / "config.toml"
            if not config_path.exists():
                # 尝试使用模板配置
                template_path = Path(__file__).parent / "config-template.toml"
                if template_path.exists():
                    config_path = template_path
                else:
                    raise FileNotFoundError("找不到配置文件")
            
            # 根据库类型选择正确的读取方式
            if hasattr(tomllib, 'loads'):  # 标准tomllib
                with open(config_path, 'rb') as f:
                    config_data = tomllib.load(f)
            else:  # toml库
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = tomllib.load(f)
            
            # 确保配置中启用了口型同步
            vtube_config = config_data.get('vtube_studio', {})
            if not vtube_config.get('enabled', False):
                self.logger.warning("VTube Studio插件在配置中被禁用")
                vtube_config['enabled'] = True
            
            lip_sync_config = vtube_config.get('lip_sync', {})
            if not lip_sync_config.get('enabled', False):
                self.logger.warning("口型同步功能在配置中被禁用")
                lip_sync_config['enabled'] = True
            
            # 动态导入VTube Studio插件
            try:
                from plugin import VTubeStudioPlugin
            except ImportError:
                # 如果相对导入失败，尝试绝对导入
                sys.path.append(str(Path(__file__).parent))
                from plugin import VTubeStudioPlugin
            
            # 创建插件实例
            self.plugin = VTubeStudioPlugin(self.core, vtube_config)
            
            if not self.plugin.enabled:
                raise RuntimeError("VTube Studio插件初始化失败或被禁用")
            
            if not self.plugin.lip_sync_enabled:
                raise RuntimeError("口型同步功能被禁用或依赖缺失")
            
            # 执行插件设置
            await self.plugin.setup()
            
            self.logger.info("测试环境初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化失败: {e}", exc_info=True)
            return False

    def generate_test_audio(self, duration: float = 1.0, sample_rate: int = 32000) -> bytes:
        """生成测试音频数据"""
        # 生成包含不同频率的测试音频，模拟元音声音
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        
        # 创建多个频率分量，模拟语音特征
        frequency_a = 730  # A元音的主要频率
        frequency_i = 270  # I元音的主要频率
        frequency_u = 300  # U元音的主要频率
        
        # 组合不同频率的信号
        signal = (
            0.3 * np.sin(2 * np.pi * frequency_a * t) +
            0.2 * np.sin(2 * np.pi * frequency_i * t) +
            0.1 * np.sin(2 * np.pi * frequency_u * t)
        )
        
        # 添加包络以模拟自然语音
        envelope = np.exp(-t * 2) * (1 - np.exp(-t * 10))
        signal = signal * envelope
        
        # 转换为int16格式
        audio_int16 = (signal * 32767 * 0.5).astype(np.int16)
        
        return audio_int16.tobytes()

    async def test_numpy_type_conversion(self):
        """测试numpy类型转换功能"""
        self.logger.info("测试 numpy 类型转换...")
        
        try:
            # 测试各种numpy类型的转换
            test_values = {
                'float32': np.float32(0.5),
                'float64': np.float64(0.7),
                'int32': np.int32(10),
                'int64': np.int64(20),
                'array_mean': np.mean(np.array([1.0, 2.0, 3.0])),
            }
            
            converted_values = {}
            for key, value in test_values.items():
                # 模拟插件中的转换过程
                converted = float(value)
                converted_values[key] = converted
                
                # 验证转换后的类型
                if not isinstance(converted, (int, float)):
                    raise TypeError(f"转换失败: {key} -> {type(converted)}")
            
            # 尝试JSON序列化
            json_str = json.dumps(converted_values)
            self.logger.info(f"✅ numpy类型转换测试通过: {json_str}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ numpy类型转换测试失败: {e}")
            return False

    async def test_basic_connection(self):
        """测试基本连接"""
        self.logger.info("测试基本连接...")
        
        try:
            if not self.plugin:
                self.logger.error("❌ 插件未初始化")
                return False
            
            # 等待连接建立
            max_wait = 10  # 最多等待10秒
            waited = 0
            while not self.plugin._is_connected_and_authenticated and waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
            
            if self.plugin._is_connected_and_authenticated:
                self.logger.info("✅ VTube Studio连接成功")
                return True
            else:
                self.logger.error("❌ VTube Studio连接失败（超时）")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 连接测试失败: {e}")
            return False

    async def test_lip_sync_session(self):
        """测试口型同步会话管理"""
        self.logger.info("测试口型同步会话管理...")
        
        try:
            # 测试启动会话
            await self.plugin.start_lip_sync_session("测试文本")
            
            # 验证状态
            if not self.plugin.is_speaking:
                self.logger.warning("启动口型同步会话后，is_speaking 应该为 True")
            
            # 测试停止会话
            await self.plugin.stop_lip_sync_session()
            
            # 验证状态
            if self.plugin.is_speaking:
                self.logger.warning("停止口型同步会话后，is_speaking 应该为 False")
            
            self.logger.info("✅ 口型同步会话管理测试通过")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 口型同步会话管理测试失败: {e}")
            return False

    async def test_audio_processing(self):
        """测试音频处理"""
        self.logger.info("测试音频处理...")
        
        try:
            # 生成测试音频
            test_audio = self.generate_test_audio(1.0)
            
            # 测试音频分析
            result = await self.plugin.analyze_audio_chunk(test_audio)
            
            # 验证返回结果
            expected_keys = ["volume", "A", "I", "U", "E", "O"]
            for key in expected_keys:
                if key not in result:
                    raise AssertionError(f"音频分析结果缺少键: {key}")
                if not isinstance(result[key], (int, float)):
                    raise AssertionError(f"音频分析结果 {key} 不是数值类型: {type(result[key])}")
            
            self.logger.info("✅ 音频处理测试通过")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 音频处理测试失败: {e}")
            return False

    async def test_parameter_updates(self):
        """测试参数更新"""
        self.logger.info("测试参数更新...")
        
        try:
            # 测试各种参数值
            test_cases = [
                ("VoiceVolume", 0.5),
                ("VoiceSilence", 0.0),
                ("VoiceA", 0.3),
                ("VoiceI", 0.2),
                ("VoiceU", 0.1),
                ("VoiceE", 0.15),
                ("VoiceO", 0.25)
            ]
            
            for param_name, value in test_cases:
                try:
                    success = await self.plugin.set_parameter_value(param_name, value)
                    if success:
                        self.logger.info(f"✅ 参数 {param_name} 设置成功: {value}")
                    else:
                        self.logger.warning(f"⚠️ 参数 {param_name} 设置失败，但无异常")
                except Exception as e:
                    self.logger.error(f"❌ 参数 {param_name} 设置出错: {e}")
                    return False
                
                # 短暂延迟避免请求过快
                await asyncio.sleep(0.1)
            
            self.logger.info("✅ 参数更新测试通过")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 参数更新测试失败: {e}")
            return False

    async def run_all_tests(self):
        """运行所有测试"""
        self.logger.info("开始运行所有测试...")
        
        tests = [
            ("numpy类型转换", self.test_numpy_type_conversion),
            ("基本连接", self.test_basic_connection),
            ("口型同步会话", self.test_lip_sync_session),
            ("音频处理", self.test_audio_processing),
            ("参数更新", self.test_parameter_updates),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"运行测试: {test_name}")
            self.logger.info(f"{'='*50}")
            
            try:
                result = await test_func()
                results[test_name] = result
                if result:
                    self.logger.info(f"✅ {test_name} 测试通过")
                else:
                    self.logger.error(f"❌ {test_name} 测试失败")
            except Exception as e:
                self.logger.error(f"❌ {test_name} 测试出错: {e}")
                results[test_name] = False
            
            # 测试间稍作延迟
            await asyncio.sleep(1)
        
        # 输出测试总结
        self.logger.info(f"\n{'='*50}")
        self.logger.info("测试总结")
        self.logger.info(f"{'='*50}")
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ 通过" if result else "❌ 失败"
            self.logger.info(f"{test_name}: {status}")
        
        self.logger.info(f"\n总体结果: {passed}/{total} 个测试通过")
        
        if passed == total:
            self.logger.info("🎉 所有测试都通过了！")
        else:
            self.logger.warning(f"⚠️ 有 {total - passed} 个测试失败")
        
        return results

    async def cleanup(self):
        """清理测试环境"""
        if self.plugin:
            await self.plugin.cleanup()
        self.logger.info("测试环境清理完成")

async def main():
    """主函数"""
    print("VTube Studio 口型同步功能测试")
    print("================================")
    print()
    print("请确保:")
    print("1. VTube Studio已运行")
    print("2. VTube Studio中已启用API访问")
    print("3. 已正确配置config.toml文件")
    print()
    input("按回车键开始测试...")
    
    tester = LipSyncTester()
    
    try:
        await tester.initialize()
        await tester.run_all_tests()
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ 测试过程中出现错误: {e}")
        logging.getLogger().error("详细错误信息:", exc_info=True)
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 