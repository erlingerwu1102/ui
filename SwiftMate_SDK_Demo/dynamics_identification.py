"""
动力学参数辨识模块
实现机器人动力学参数自动辨识功能
"""

import time
import threading
import logging
from app.data_store import get_store
from safety_monitor import safety_monitor
from robot_config import robot_config

class DynamicsIdentification:
    """动力学参数辨识类"""
    
    def __init__(self):
        self.is_identifying = False
        self.progress = 0
        self.current_trajectory_range = 10
        self.current_trajectory_speed = 10
        self.identification_results = {}
        self.logger = logging.getLogger(__name__)
        self.store = get_store()
        # 每次迭代运行时长（秒），由速度映射决定
        self.iteration_duration = 1.0
    
    def start_identification(self, trajectory_range=10, trajectory_speed=10):
        """开始动力学参数辨识"""
        if self.is_identifying:
            return False, "辨识正在进行中"
        
        self.is_identifying = True
        self.progress = 0
        self.current_trajectory_range = trajectory_range
        self.current_trajectory_speed = trajectory_speed
        # 计算每次轨迹运行的时长，使用 robot_config 的映射函数
        try:
            self.iteration_duration = float(robot_config.speed_to_duration(trajectory_speed))
        except Exception:
            self.iteration_duration = 1.0
        
        # 在后台线程中运行辨识过程
        thread = threading.Thread(target=self._run_identification)
        thread.daemon = True
        thread.start()
        
        return True, "开始动力学参数辨识"
    
    def _run_identification(self):
        """运行辨识过程（模拟）"""
        try:
            # 模拟10次辨识过程
            for i in range(10):
                if not self.is_identifying:
                    break
                
                # 模拟轨迹运行，使用映射得到的 iteration_duration
                self._run_trajectory()
                
                # 模拟数据分析和参数计算
                self._analyze_data(i + 1)
                
                # 更新进度
                self.progress = (i + 1) * 10
                time.sleep(2)  # 模拟每次辨识耗时
            
            if self.is_identifying:
                self.is_identifying = False
                self.logger.info("动力学参数辨识完成")
                
        except Exception as e:
            self.is_identifying = False
            self.logger.exception(f"辨识过程出错: {e}")
    
    def _run_trajectory(self):
        """运行辨识轨迹（模拟）"""
        self.logger.info(f"运行辨识轨迹: 范围{self.current_trajectory_range}%, 速度{self.current_trajectory_speed}%，时长 {self.iteration_duration}s")
        # 当 iteration_duration 很大时可以分段睡眠以便响应 stop 请求
        remaining = self.iteration_duration
        step = 0.5
        while remaining > 0 and self.is_identifying:
            time.sleep(min(step, remaining))
            remaining -= step
    
    def _analyze_data(self, iteration):
        """分析数据并计算参数（模拟）"""
        # 模拟误差计算并持久化到数据存储
        import random

        result = {
            'timestamp': int(time.time()),
            'trajectory_range': self.current_trajectory_range,
            'trajectory_speed': self.current_trajectory_speed,
            'iteration': iteration,
            'axes': {}
        }

        for axis in range(1, 7):
            axis_key = f'axis{axis}'
            error = random.uniform(0.1, 5.0)  # 模拟误差值
            result['axes'][axis_key] = round(error, 2)
            # keep last results in memory too
            self.identification_results[axis_key] = {
                'error': round(error, 2),
                'iteration': iteration
            }

        # 持久化当前迭代结果
        try:
            self.store.append_to_collection('identification_runs', result)
            self.logger.info(f"第{iteration}次辨识完成并已持久化: {result}")
        except Exception:
            self.logger.exception("持久化辨识结果失败")
    
    def stop_identification(self):
        """停止辨识过程"""
        self.is_identifying = False
        return True, "辨识已停止"
    
    def test_trajectory_safety(self, trajectory_range, trajectory_speed):
        """测试轨迹安全性"""
        # 简单安全检查：确保当前没有检测到碰撞，并且轨迹在配置的工作范围内
        self.logger.info(f"测试轨迹安全性: 范围{trajectory_range}%, 速度{trajectory_speed}%")
        # 如果安全监控检测到碰撞，则返回不通过
        if safety_monitor.collision_detected:
            return False, "检测到碰撞，轨迹不安全"

        # 检查工作范围
        try:
            wr = robot_config.safety_limits.get('working_range', 100)
            if float(trajectory_range) < 0 or float(trajectory_range) > wr:
                return False, f"轨迹范围超出允许范围 0-{wr}"
        except Exception:
            pass

        # 模拟较短的测试过程（不阻塞太久）
        time.sleep(0.5)
        return True, "轨迹安全测试通过"

    # 新增：设置辨识参数（兼容 SDK Demo 的 set_parameters）
    def set_parameters(self, trajectory_range: int, trajectory_speed: int):
        try:
            self.current_trajectory_range = int(trajectory_range)
            self.current_trajectory_speed = int(trajectory_speed)
            return True
        except Exception:
            return False

    def confirm_zero_position(self):
        """确认零点位置（模拟）。"""
        # 在真实系统中应检测当前关节角度是否接近零点；这里返回 True 以便演示流程
        self.zero_position_confirmed = True
        return True

    def get_status(self):
        """返回结构化状态，供接口查询使用"""
        return {
            "running": bool(self.is_identifying),
            "identification_count": int(self.progress / 10) if self.progress else 0,
            "max_identification_count": 10,
            "axis_errors": [self.identification_results.get(f'axis{i}', {}).get('error', 0) for i in range(1,7)],
            "estimated_remaining_time": max(0, (10 - (self.progress/10)) * 0.5),
            "safety_check_passed": True,
            "zero_position_confirmed": getattr(self, 'zero_position_confirmed', False)
        }


# 全局辨识实例
dynamics_identification = DynamicsIdentification()