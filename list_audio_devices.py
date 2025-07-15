import sounddevice as sd

def list_audio_devices():
    """列出所有可用的音频设备"""
    devices = sd.query_devices()
    
    print("=== 可用的音频输出设备 ===")
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:  # 只显示支持输出的设备
            print(f"设备 {i}: {device['name']}")
            print(f"  - 最大输出通道: {device['max_output_channels']}")
            print(f"  - 默认采样率: {device['default_samplerate']}")
            print()
    
    # 显示默认设备
    default_output = sd.default.device[1]  # 输出设备索引
    if default_output != -1:
        default_device = devices[default_output]
        print(f"当前默认输出设备: {default_device['name']} (索引: {default_output})")
    else:
        print("未找到默认输出设备")

if __name__ == "__main__":
    try:
        list_audio_devices()
    except Exception as e:
        print(f"错误: {e}")
        print("请确保已安装sounddevice: pip install sounddevice") 