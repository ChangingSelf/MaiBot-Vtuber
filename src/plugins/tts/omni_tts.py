"""
大模型音频生成模块 - 使用阿里云Qwen-Omni模型实现文本到语音的转换
"""
import os
import json
import aiohttp
import base64
import asyncio
from typing import List, Dict, Any, Optional, Generator, AsyncGenerator
import io
import numpy as np
import soundfile as sf
import random
# 导入音频处理库
try:
    from pydub import AudioSegment
    from pydub.generators import WhiteNoise
    PYDUB_AVAILABLE = True
except ImportError:
    print("警告: pydub库未安装，音频后处理功能将不可用")
    PYDUB_AVAILABLE = False


class OmniTTS:
    """使用阿里云Qwen-Omni模型实现的文本到语音转换类"""
    
    def __init__(
        self, 
        api_key: str,
        model_name: str = "qwen-omni-turbo",
        voice: str = "Chelsie",
        format: str = "wav",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        # 音频后处理参数
        enable_post_processing: bool = False,
        volume_reduction_db: float = 0,
        noise_level: float = 0,
        blow_up_probability: float = 0.0,
        blow_up_texts: Optional[List[str]] = None,
    ):
        """
        初始化OmniTTS类
        
        Args:
            api_key: 阿里云百炼API Key
            model_name: 模型名称，默认为qwen-omni-turbo
            voice: 语音音色，默认为Chelsie
            format: 音频格式，默认为wav
            base_url: API基础URL
            enable_post_processing: 是否启用音频后处理
            volume_reduction_db: 音量降低程度(dB)，值越大音量越低
            noise_level: 杂音强度，0-1之间的浮点数，0表示无杂音
            blow_up_probability: 触发"麦炸了"彩蛋的概率，0-1之间的浮点数
            blow_up_texts: 彩蛋触发时使用的文本列表
        """
        self.api_key = api_key
        self.model_name = model_name
        self.voice = voice
        self.format = format
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 音频后处理参数
        self.enable_post_processing = True  # 强制启用后处理
        self.volume_reduction_db = volume_reduction_db
        self.noise_level = max(0, min(1, noise_level))  # 确保在0-1之间
        self.blow_up_probability = max(0, min(1, blow_up_probability)) # 确保在0-1之间
        self.blow_up_texts = blow_up_texts if blow_up_texts else ["我的麦真的很炸吗（大声急促）"]
        
        self.blow_up = False
        
        # 检查pydub是否可用
        global PYDUB_AVAILABLE
        if not PYDUB_AVAILABLE:
            try:
                from pydub import AudioSegment
                from pydub.generators import WhiteNoise
                PYDUB_AVAILABLE = True
                print("成功导入pydub库")
            except ImportError:
                print("警告: pydub库未安装，音频后处理功能将不可用")
                PYDUB_AVAILABLE = False
                self.enable_post_processing = False
        
        # 尝试导入OpenAI库
        try:
            import openai
            self.openai_available = True
        except ImportError:
            self.openai_available = False
            print("OpenAI库未安装，将使用aiohttp直接调用API")
    
    async def generate_audio(self, text: str) -> bytes:
        """
        使用大模型生成音频数据
        
        Args:
            text: 需要转换为语音的文本
        
        Returns:
            音频数据的字节流
        """
        print(f"开始调用大模型API生成音频，文本: {text[:30]}{'...' if len(text) > 30 else ''}")
        
        self.blow_up = False
        if self.blow_up_texts and random.random() < self.blow_up_probability:
            self.blow_up = True
            text = random.choice(self.blow_up_texts)
        
        # 由于修改后的流式API现在只返回一个合并后的音频块，我们可以直接获取这个块
        audio_chunks = []
        async for chunk in self.generate_audio_stream(text):
            audio_chunks.append(chunk)
        
        if not audio_chunks:
            raise Exception("未能获取任何音频数据")
            
        # 合并所有音频块（通常只有一个）
        complete_audio = b"".join(audio_chunks)
        return complete_audio
    
    async def generate_audio_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        使用大模型流式生成音频数据
        
        Args:
            text: 需要转换为语音的文本
        
        Yields:
            音频数据块的字节流
        """
        print(f"开始流式调用大模型API生成音频，文本: {text[:30]}{'...' if len(text) > 30 else ''}")
        print(f"生成prompt: {text}")
        prompt = f"复述这句话，不要输出其他内容，只输出'{text}'就好，不要输出其他内容，不要输出前后缀，不要输出'{text}'以外的内容，不要说：如果还有类似的需求或者想聊聊别的"
        
        
        # 优先使用OpenAI客户端(如果可用)
        if self.openai_available and self._should_use_openai_client():
            async for chunk in self._generate_with_openai_client(prompt):
                yield chunk
            return
            
        # 否则使用aiohttp直接调用API
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/chat/completions"
            
            # 按照官方示例构建消息格式 - 使用简单格式而不是嵌套格式
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "stream": True,
                "stream_options": {"include_usage": True},
                "modalities": ["text", "audio"],
                "audio": {"voice": self.voice, "format": self.format}
            }
            
            print(f"API请求: {url}")
            print(f"使用模型: {self.model_name}, 音色: {self.voice}, 格式: {self.format}")
            
            try:
                async with session.post(url, headers=self.headers, json=payload) as response:
                    print(f"API返回状态码: {response.status}")
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"API错误响应: {error_text}")
                        raise Exception(f"API请求失败: {response.status} - {error_text}")
                    
                    # 处理流式响应
                    chunk_count = 0
                    audio_string = ""
                    
                    async for line in response.content:
                        line = line.strip()
                        if not line:
                            continue
                        
                        if line == b"data: [DONE]":
                            print("收到流结束标记 [DONE]")
                            continue
                        
                        if line.startswith(b"data: "):
                            chunk_count += 1
                            json_str = line[6:].decode("utf-8")
                            try:
                                chunk = json.loads(json_str)
                                
                                # 检查是否包含音频数据
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})
                                    
                                    # 处理音频数据 - 直接从audio字段获取
                                    if delta and "audio" in delta:
                                        if "data" in delta["audio"]:
                                            # 累积base64字符串
                                            audio_string += delta["audio"]["data"]
                                        elif "transcript" in delta["audio"]:
                                            # 处理音频转录文本
                                            print(f"收到音频转录文本: {delta['audio']['transcript']}")
                            except json.JSONDecodeError as e:
                                print(f"无法解析JSON: {str(e)}")
                                print(f"原始数据: {json_str[:100]}...")
                                continue
                    
                    print(f"流式处理完成，共处理 {chunk_count} 个数据块")
                    
                    # 一次性解码所有音频数据
                    if audio_string:
                        # 解码base64数据
                        wav_bytes = base64.b64decode(audio_string)
                        # 转换为numpy数组
                        audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
                        # 创建临时内存文件对象
                        audio_buffer = io.BytesIO()
                        # 使用soundfile写入正确格式的wav数据
                        sf.write(audio_buffer, audio_np, samplerate=24000, format='WAV')
                        # 获取处理后的音频数据
                        audio_buffer.seek(0)
                        audio_data = audio_buffer.read()
                        
                        # 应用音频后处理
                        if self.enable_post_processing:
                            print("正在应用音频后处理...")
                            audio_data = self._process_audio(audio_data)
                        
                        print(f"成功获取音频数据，总大小: {len(audio_data)} 字节")
                        yield audio_data
                    else:
                        print("警告: 没有收到任何音频数据")
            except Exception as e:
                import traceback
                print(f"流式处理过程中发生错误: {str(e)}")
                print(f"详细错误信息: {traceback.format_exc()}")
                raise
    
    def _should_use_openai_client(self) -> bool:
        """判断是否应该使用OpenAI客户端"""
        return self.openai_available

    async def _generate_with_openai_client(self, text: str) -> AsyncGenerator[bytes, None]:
        """使用OpenAI客户端生成音频"""
        try:
            from openai import OpenAI
            
            print("使用OpenAI客户端调用API")
            print(f"PYDUB可用性状态: {PYDUB_AVAILABLE}")
            print(f"后处理功能状态: {self.enable_post_processing}")
            print(f"爆音模式状态: {self.blow_up}")
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            print(f"OpenAI请求参数: model={self.model_name}, voice={self.voice}")
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": text}
                ],
                modalities=["text", "audio"],
                audio={"voice": self.voice, "format": self.format},
                stream=True,
                stream_options={"include_usage": True}
            )
            
            # 用于累积所有base64字符串
            audio_string = ""
            
            for chunk in completion:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    # 检查是否有音频数据
                    if hasattr(delta, 'audio'):
                        try:
                            # 累积base64字符串
                            if 'data' in delta.audio:
                                audio_string += delta.audio['data']
                            elif 'transcript' in delta.audio:
                                print(f"[OpenAI客户端] 收到音频转录文本: {delta.audio['transcript']}")
                        except Exception as e:
                            print(f"[OpenAI客户端] 处理音频数据出错: {str(e)}")
            
            # 一次性解码所有音频数据
            if audio_string:
                print("准备解码音频数据...")
                # 解码base64数据
                wav_bytes = base64.b64decode(audio_string)
                # 转换为numpy数组
                audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
                # 创建临时内存文件对象
                audio_buffer = io.BytesIO()
                # 使用soundfile写入正确格式的wav数据
                sf.write(audio_buffer, audio_np, samplerate=24000, format='WAV')
                # 获取处理后的音频数据
                audio_buffer.seek(0)
                audio_data = audio_buffer.read()
                
                print(f"解码成功，原始音频大小: {len(audio_data)} 字节, 爆音状态: {self.blow_up}")
                
                # 应用音频后处理 - 无论后处理设置如何，在blow_up模式下都强制应用
                if self.enable_post_processing or self.blow_up:
                    print("[OpenAI客户端] 正在应用音频后处理...")
                    audio_data = self._process_audio(audio_data)
                
                print(f"[OpenAI客户端] 成功获取音频数据，总大小: {len(audio_data)} 字节")
                yield audio_data
            else:
                print("[OpenAI客户端] 警告: 没有收到任何音频数据")
                
        except ImportError:
            print("OpenAI库未正确安装，无法使用OpenAI客户端")
            raise
        except Exception as e:
            import traceback
            print(f"[OpenAI客户端] 处理过程中发生错误: {str(e)}")
            print(f"[OpenAI客户端] 详细错误信息: {traceback.format_exc()}")
            raise

    def _process_audio(self, audio_data: bytes) -> bytes:
        """
        对音频数据进行后处理（降低音量、添加杂音、柔化声音）
        
        Args:
            audio_data: 原始音频数据
            
        Returns:
            处理后的音频数据
        """
        print(f"进入_process_audio方法，PYDUB_AVAILABLE={PYDUB_AVAILABLE}, enable_post_processing={self.enable_post_processing}, blow_up={self.blow_up}")
        
        if not PYDUB_AVAILABLE:
            print("警告: pydub库不可用，无法处理音频")
            return audio_data
            
        if not self.enable_post_processing and not self.blow_up:
            print("后处理功能未启用且非爆音模式，跳过处理")
            return audio_data
            
        try:
            # 保证pydub导入成功
            from pydub import AudioSegment
            from pydub.generators import WhiteNoise
            
            print("开始处理音频数据...")
            # 将音频数据加载到AudioSegment对象
            audio_segment = AudioSegment.from_wav(io.BytesIO(audio_data))
            original_duration = len(audio_segment)
            print(f"原始音频长度: {original_duration}ms")
            
            # 降低音量
            if self.volume_reduction_db > 0:
                audio_segment = audio_segment - self.volume_reduction_db
                print(f"已降低音量 {self.volume_reduction_db}dB")
                
            # 柔化声音 - 使用低通滤波实现声音钝化和柔化
            # 使用低通滤波器保留低频，降低高频尖锐感
            try:
                # 尝试应用低通滤波
                low_freq = audio_segment.low_pass_filter(2000)  # 2000Hz以下频率通过
                audio_segment = low_freq
                print("已应用低通滤波进行声音柔化")
            except Exception as e:
                print(f"应用低通滤波失败: {str(e)}")
                
            # 添加杂音 - 使用更加温和、自然的噪声
            if self.noise_level > 0 or self.blow_up:
                try:
                    # 使用WhiteNoise并应用低通滤波使其接近粉红噪声效果
                    from pydub.generators import WhiteNoise
                    
                    # 生成噪声
                    noise_duration = original_duration
                    noise = WhiteNoise().to_audio_segment(duration=noise_duration)
                    print("已生成基础噪声")
                    
                    # 应用强烈的低通滤波使白噪声听起来更接近自然环境噪声
                    if not self.blow_up:  # 只在非爆炸模式下应用滤波
                        try:
                            noise = noise.low_pass_filter(300)  # 更强的滤波，只保留非常低的频率
                            print("已对噪声应用低通滤波")
                        except Exception as e:
                            print(f"滤波白噪声失败: {str(e)}")
                    else:
                        noise = noise.low_pass_filter(1200)  # 更强的滤波，只保留非常低的频率
                        print("爆炸模式：不对噪声应用滤波，保留原始白噪声的刺耳特性")
                    
                    # 调整噪声音量
                    if self.blow_up:
                        # 噪音拉满 - 使用最大噪声强度
                        actual_noise_level = random.uniform(0.3, 1)
                        # 提高噪声基准，使其接近原音频音量
                        noise = noise - 10 *(actual_noise_level)
                        audio_segment = audio_segment.overlay(noise)
                        print(f"爆音模式！噪声强度设置为{actual_noise_level*100:.1f}%")
                    else:
                        # 正常噪声处理，噪声强度为self.noise_level的三次方根
                        noise_level = 0.9 + self.noise_level * 0.1
                        noise = noise * noise_level  # 噪声基准比原音频低较多
                        audio_segment = audio_segment.overlay(noise)
                        print(f"已添加{noise_level*100:.1f}%（三次方根）强度的背景噪声")
                except Exception as e:
                    print(f"添加噪声失败: {str(e)}")
            
            # 轻微混响效果 - 通过制作一个非常轻微的延迟副本并叠加实现
            try:
                if original_duration > 100 and not self.blow_up:  # 爆音模式下不添加混响
                    reverb_segment = audio_segment[10:] - 12  # 使用略延迟的副本，降低12dB
                    audio_segment = audio_segment.overlay(reverb_segment, position=10)
                    print("已添加轻微混响效果")
                elif self.blow_up and original_duration > 50:
                    # 爆音模式下添加更强烈的混响
                    reverb_segment = audio_segment[5:] - 6  # 更短的延迟，更高的音量
                    audio_segment = audio_segment.overlay(reverb_segment, position=5)
                    print("已添加强烈混响效果")
            except Exception as e:
                print(f"添加混响效果失败: {str(e)}")
            
            # 转换回字节数据
            output = io.BytesIO()
            audio_segment.export(output, format="wav")
            processed_data = output.getvalue()
            print(f"音频处理完成，处理后大小: {len(processed_data)} 字节")
            return processed_data
            
        except Exception as e:
            import traceback
            print(f"音频后处理过程中发生错误: {str(e)}")
            print(f"详细错误信息: {traceback.format_exc()}")
            # 出错时返回原始音频
            return audio_data


async def test_omni_tts():
    """测试函数"""
    # 设置API Key
    api_key = ""
    if not api_key:
        print("请设置有效的API密钥")
        return
    
    # 测试带后处理的TTS
    if PYDUB_AVAILABLE:
        print("\n===== 测试音频后处理功能 =====")
        tts = OmniTTS(
            api_key=api_key,
            model_name="qwen2.5-omni-7b",
            voice="Chelsie",
            enable_post_processing=True,
            volume_reduction_db=3.0,  # 降低3dB的音量
            noise_level=0.05          # 添加15%强度的背景杂音
        )
        
        test_text = "复述这句话，不要输出其他内容，只输出'挺厉害的'就好，不要输出其他内容，不要输出前后缀，不要输出'挺厉害的'以外的内容，不要说：如果还有类似的需求或者想聊聊别的"
        audio_data = await tts.generate_audio(test_text)
        
        if audio_data:
            # 保存音频文件
            filename = "test_post_processed.wav"
            with open(filename, "wb") as f:
                f.write(audio_data)
            print(f"已保存后处理音频至 {filename}")
    
    # 只测试qwen2.5-omni-7b开源模型，并输出完整返回数据
    print("\n===== 测试qwen2.5-omni-7b模型 =====")
    # 使用OpenAI客户端直接测试
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        print("发起API请求...")
        test_text = "这是一条使用qwen2.5-omni-7b模型的测试消息。"
        print(f"请求文本: {test_text}")
        
        completion = client.chat.completions.create(
            model="qwen2.5-omni-7b",
            messages=[
                {"role": "user", "content": test_text}
            ],
            modalities=["text", "audio"],
            audio={"voice": "Chelsie", "format": "wav"},
            stream=True,
            stream_options={"include_usage": True}
        )
        
        print("开始接收响应...")
        chunk_count = 0
        text_parts = []
        audio_string = ""
        
        for chunk in completion:
            chunk_count += 1
            # 完整打印每个响应块
            # print(f"\n===== 响应块 #{chunk_count} =====")
            # print(f"完整内容: {chunk}")
            
            # 提取文本内容
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                # 提取音频数据
                if hasattr(delta, 'audio'):
                    try:
                        if 'data' in delta.audio:
                            audio_string += delta.audio['data']
                        elif 'transcript' in delta.audio:
                            print(f"音频转录文本: {delta.audio['transcript']}")
                    except Exception as e:
                        print(f"处理音频数据出错: {str(e)}")
                
                # 提取文本内容
                if hasattr(delta, 'content'):
                    if delta.content:  # 有内容
                        print(f"内容类型: {type(delta.content)}")
                        
                        # 处理文本
                        if isinstance(delta.content, str):
                            text_parts.append(delta.content)
                            print(f"文本内容: {delta.content}")
                        # 处理列表内容
                        elif isinstance(delta.content, list):
                            for item in delta.content:
                                print(f"列表项: {item}")
                                if isinstance(item, dict):
                                    if item.get("type") == "text" and "text" in item:
                                        text_parts.append(item["text"])
                                        print(f"文本内容: {item['text']}")
            # 处理使用信息
            elif hasattr(chunk, 'usage'):
                print(f"使用信息: {chunk.usage}")
                
        # 汇总结果
        print(f"\n===== 处理结果汇总 =====")
        print(f"处理的响应块数量: {chunk_count}")
        
        if text_parts:
            full_text = "".join(text_parts)
            print(f"收集到的完整文本: {full_text}")
        else:
            print("未收集到文本内容")
            
        # 解码并保存音频
        if audio_string:
            # 解码base64数据
            wav_bytes = base64.b64decode(audio_string)
            # 转换为numpy数组
            audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
            # 使用soundfile保存为正确格式的wav文件
            filename = "test_qwen25_omni_7b.wav"
            sf.write(filename, audio_np, samplerate=24000)
            print(f"音频已保存至 {filename}，总大小: {len(audio_np)*2} 字节")
        else:
            print("未收到任何音频数据")
    
    except Exception as e:
        import traceback
        print(f"测试出错: {str(e)}")
        print(traceback.format_exc())
    
    print("\n测试完成")


if __name__ == "__main__":
    asyncio.run(test_omni_tts()) 