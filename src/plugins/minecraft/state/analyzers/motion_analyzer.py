"""
运动分析器

负责分析玩家的位置、朝向、速度等运动相关信息
"""

import math
from typing import List
from .base_analyzer import BaseAnalyzer


class MotionAnalyzer(BaseAnalyzer):
    """运动分析器"""

    def __init__(self, obs, config=None):
        super().__init__(obs, config)

        # 位置分析配置
        self.low_height_threshold = self._get_config_value("low_height_threshold", 30)

        # 朝向分析配置
        self.direction_precision = self._get_config_value("direction_precision", 1)

        # 速度分析配置
        self.velocity_still_threshold = self._get_config_value("velocity_still_threshold", 0.01)
        self.velocity_fast_threshold = self._get_config_value("velocity_fast_threshold", 0.3)
        self.velocity_precision = self._get_config_value("velocity_precision", 3)

    def analyze(self) -> List[str]:
        """
        分析运动相关状态

        Returns:
            List[str]: 运动状态提示列表
        """
        motion_prompts = []

        motion_prompts.extend(self.analyze_position())
        motion_prompts.extend(self.analyze_direction())
        motion_prompts.extend(self.analyze_velocity())

        return motion_prompts

    def analyze_position(self) -> List[str]:
        """分析位置相关状态"""
        position_prompts = []

        try:
            location_stats = self._safe_getattr(self.obs, "location_stats")
            if not location_stats:
                return position_prompts

            # 坐标信息
            pos = self._safe_getattr(location_stats, "pos")
            if pos:
                position_prompts.append(f"你的当前坐标是{pos}")

                # 高度分析
                if pos[1] < self.low_height_threshold:
                    position_prompts.append("你处于较低的高度，可能接近地下洞穴或矿层。")

            # 地面状态
            is_on_ground = self._safe_getattr(location_stats, "is_on_ground", True)
            if not is_on_ground:
                position_prompts.append("你不在地面上（在空中）")

        except Exception as e:
            self.logger.warning(f"分析位置数据时出错: {e}")

        return position_prompts

    def analyze_direction(self) -> List[str]:
        """分析玩家朝向"""
        direction_prompts = []

        try:
            location_stats = self._safe_getattr(self.obs, "location_stats")
            if not location_stats:
                return direction_prompts

            # 获取偏航角和俯仰角
            yaw = self._safe_getattr(location_stats, "yaw")
            pitch = self._safe_getattr(location_stats, "pitch")

            if yaw is not None:
                # 将yaw角度标准化到[0, 360)范围
                normalized_yaw = yaw % 360

                # 根据yaw角度确定基本方向
                if 315 <= normalized_yaw or normalized_yaw < 45:
                    cardinal_direction = "北"
                elif 45 <= normalized_yaw < 135:
                    cardinal_direction = "东"
                elif 135 <= normalized_yaw < 225:
                    cardinal_direction = "南"
                else:
                    cardinal_direction = "西"

                direction_prompts.append(
                    f"你当前面朝{cardinal_direction}方向（偏航角{round(normalized_yaw, self.direction_precision)}°）"
                )

            if pitch is not None:
                # 俯仰角分析
                if pitch > 30:
                    direction_prompts.append(f"你正在向下看（俯仰角{round(pitch, self.direction_precision)}°）")
                elif pitch < -30:
                    direction_prompts.append(f"你正在向上看（俯仰角{round(pitch, self.direction_precision)}°）")

            # 面向向量分析
            face_vector = self._safe_getattr(self.obs, "face_vector")
            if face_vector and len(face_vector) >= 3:
                direction_prompts.append(
                    f"面向向量: [{round(face_vector[0], 3)}, {round(face_vector[1], 3)}, {round(face_vector[2], 3)}]"
                )

        except Exception as e:
            self.logger.warning(f"分析朝向数据时出错: {e}")

        return direction_prompts

    def analyze_velocity(self) -> List[str]:
        """分析玩家速度"""
        velocity_prompts = []

        try:
            location_stats = self._safe_getattr(self.obs, "location_stats")
            if not location_stats:
                return velocity_prompts

            vel = self._safe_getattr(location_stats, "vel")
            is_on_ground = self._safe_getattr(location_stats, "is_on_ground", True)

            if vel and len(vel) >= 3:
                # 计算各个方向的速度分量
                vel_x = round(vel[0], self.velocity_precision)
                vel_y = round(vel[1], self.velocity_precision)
                vel_z = round(vel[2], self.velocity_precision)

                # 计算总体水平速度
                horizontal_speed = round(math.sqrt(vel[0] ** 2 + vel[2] ** 2), self.velocity_precision)
                total_speed = round(math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2), self.velocity_precision)

                # 速度状态分析
                if total_speed <= self.velocity_still_threshold:
                    velocity_prompts.append("你当前处于静止状态")
                else:
                    velocity_prompts.append(f"你的移动速度: 水平{horizontal_speed} 垂直{vel_y} 总体{total_speed}")

                    if horizontal_speed >= self.velocity_fast_threshold:
                        velocity_prompts.append("你正在快速水平移动")

                    # 垂直运动分析
                    if vel_y > 0.1:
                        velocity_prompts.append("你正在上升（跳跃或飞行）")
                    elif vel_y < -0.1:
                        if is_on_ground:
                            velocity_prompts.append("你正在下降但仍在地面上")
                        else:
                            velocity_prompts.append("你正在下降（坠落）")

                # 地面状态
                if is_on_ground:
                    velocity_prompts.append("你站在地面上")
                else:
                    velocity_prompts.append("你不在地面上（在空中）")

        except Exception as e:
            self.logger.warning(f"分析速度数据时出错: {e}")

        return velocity_prompts
