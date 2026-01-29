"""
安全监控模块
实现碰撞检测、安全限位监控等功能
"""

import time
import threading
import logging
import os
from robot_config import robot_config

class SafetyMonitor:
    """安全监控类"""
    
    def __init__(self):
        self.collision_detected = False
        self.safety_limits = {
            'position_limits': {},
            'velocity_limits': {},
            'torque_limits': {}
        }
        self.monitoring = False
        self.monitor_thread = None
        self._last_error_time = None
        self.logger = logging.getLogger(__name__)
    
    def start_monitoring(self):
        """开始安全监控"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止安全监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
    
    def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                # 模拟碰撞检测
                self._check_collisions()
                # 模拟限位检查
                self._check_limits()
                
                time.sleep(0.1)  # 100ms监控周期
            except Exception as e:
                self.logger.exception(f"安全监控错误: {e}")
                time.sleep(1)
    
    def _check_collisions(self):
        """检查碰撞（模拟）"""
        # 在实际系统中，这里会读取力/力矩传感器数据
        # 这里用随机数模拟
        # 如果设置环境变量 DEV_NO_COLLISIONS=1，则在开发/调试时禁用随机触发
        if os.environ.get('DEV_NO_COLLISIONS') == '1':
            return
        # 仅在显式启用碰撞检测时才进行随机模拟（避免开发环境频繁误报）
        try:
            if not getattr(robot_config, 'collision_detection', False):
                return
        except Exception:
            # 若无法读取配置，继续执行以保证兼容性
            pass
        import random
        # 根据 robot_config.collision_params 调整灵敏度概率阈值
        params = robot_config.get_collision_params()
        sensitivity = params.get('sensitivity', 50)
        # 把灵敏度映射到概率阈值：灵敏度越小概率越大
        # 将概率大幅降低以避免在开发环境中频繁触发（按0.1s周期）
        prob = max(0.0001, min(0.01, (100 - sensitivity) / 10000.0))
        # 轻度开发模式时进一步降低触发概率
        if os.environ.get('DEV_LOW_COLLISIONS') == '1':
            prob = min(prob, 0.001)
        if random.random() < prob:
            now = time.time()
            # 如果在允许误差时间内重复触发，不重复标记
            allowed = params.get('allowed_error_time', 0.5)
            if self._last_error_time and (now - self._last_error_time) < allowed:
                # 忽略短时触发
                return
            self._last_error_time = now
            self.collision_detected = True
            self.logger.warning("警告: 检测到碰撞!")
    
    def _check_limits(self):
        """检查安全限位"""
        # 在实际系统中，这里会检查位置、速度、力矩限制
        pass
    
    def reset_collision(self):
        """重置碰撞状态"""
        self.collision_detected = False
        return True

    def is_inside_workspace(self, position):
        """检查给定三维点是否在工作空间内。

        position: 可迭代包含 [x,y,z]
        使用 robot_config.collision_params 或 robot_config.safety_limits 中的 'workspace' 字段
        来决定边界；若未配置则使用默认边界。
        """
        try:
            x, y, z = float(position[0]), float(position[1]), float(position[2])
        except Exception:
            return False

        # 默认工作空间边界（与文档一致的保守默认值）
        default_bounds = {
            'x': (0.0, 1.2),
            'y': (0.0, 1.0),
            'z': (0.0, 0.8)
        }

        # 优先使用 robot_config.safety_limits.get('workspace') 如果存在
        bounds = None
        try:
            sl = getattr(robot_config, 'safety_limits', None) or {}
            bounds = sl.get('workspace')
        except Exception:
            bounds = None

        if bounds and isinstance(bounds, (list, tuple)) and len(bounds) == 3:
            try:
                xb = tuple(bounds[0])
                yb = tuple(bounds[1])
                zb = tuple(bounds[2])
                x_min, x_max = float(xb[0]), float(xb[1])
                y_min, y_max = float(yb[0]), float(yb[1])
                z_min, z_max = float(zb[0]), float(zb[1])
            except Exception:
                x_min, x_max = default_bounds['x']
                y_min, y_max = default_bounds['y']
                z_min, z_max = default_bounds['z']
        else:
            x_min, x_max = default_bounds['x']
            y_min, y_max = default_bounds['y']
            z_min, z_max = default_bounds['z']

        return (x_min <= x <= x_max) and (y_min <= y <= y_max) and (z_min <= z <= z_max)

# 全局安全监控实例
safety_monitor = SafetyMonitor()