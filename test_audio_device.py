import sounddevice as sd

def test_find_device(device_name, kind="output"):
    """测试音频设备查找功能"""
    try:
        devices = sd.query_devices()
        print(f"正在查找 {kind} 设备: '{device_name}'")
        
        if device_name:
            for i, device in enumerate(devices):
                max_channels_key = f"max_{kind}_channels"
                print(f"设备 {i}: {device['name']}, {max_channels_key}: {device[max_channels_key]}")
                
                if device_name.lower() in device["name"].lower() and device[max_channels_key] > 0:
                    print(f"✅ 找到匹配设备: '{device['name']}' (索引: {i})")
                    return i
            
            print(f"❌ 未找到名称包含 '{device_name}' 的 {kind} 设备")
        
        # 获取默认设备
        default_device_indices = sd.default.device
        default_index = default_device_indices[1] if kind == "output" else default_device_indices[0]
        
        if default_index != -1:
            default_device = devices[default_index]
            print(f"🔧 使用默认 {kind} 设备: '{default_device['name']}' (索引: {default_index})")
            return default_index
        else:
            print(f"⚠️ 未找到默认 {kind} 设备")
            return None
            
    except Exception as e:
        print(f"❌ 查找音频设备时出错: {e}")
        return None

if __name__ == "__main__":
    # 测试您配置的设备
    device_name = "扬声器 (Steam Streaming Speakers)"
    result = test_find_device(device_name, "output")
    print(f"\n最终结果: {result}") 