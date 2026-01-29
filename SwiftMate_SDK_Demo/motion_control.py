import time
import threading
import os
from robot_config import robot_config
from safety_monitor import safety_monitor
from hardware_interface import EmergencyStopController

# Lazy-loaded pybullet symbols
p = None
_sim_initialized = False
physicsClient = None
planeId = None
cubeId = None


def ensure_simulation():
    """Initialize pybullet simulation on first use. Returns True if available."""
    global p, _sim_initialized, physicsClient, planeId, cubeId
    if _sim_initialized:
        return p is not None

    try:
        import pybullet as p_local

        p = p_local
        physicsClient = p.connect(p.DIRECT)
        p.setGravity(0, 0, -9.8)

        # 创建模型（simple cube for operations）
        planeId = p.createCollisionShape(p.GEOM_PLANE)
        cubeId = p.createMultiBody(
            baseMass=1,
            baseCollisionShapeIndex=p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.5, 0.5, 0.5]),
            baseVisualShapeIndex=p.createVisualShape(p.GEOM_BOX, halfExtents=[0.5, 0.5, 0.5], rgbaColor=[1, 0, 0, 1])
        )
        _sim_initialized = True
        return True
    except Exception:
        # pybullet not available or initialization failed
        # 尝试启用纯 Python 的 fallback 模拟，以便在没有 pybullet 时仍能运行演示接口
        try:
            class _FakePB:
                def __init__(self):
                    self._bodies = {}
                    self._next_id = 1

                def connect(self, mode):
                    return 1

                def disconnect(self):
                    return True

                def setGravity(self, x, y, z):
                    return True

                def createCollisionShape(self, shapeType, **kwargs):
                    return 1

                def createVisualShape(self, *args, **kwargs):
                    return 1

                def createMultiBody(self, baseMass=0, baseCollisionShapeIndex=None, baseVisualShapeIndex=None):
                    bid = self._next_id
                    self._next_id += 1
                    # store position and orientation as (pos, euler)
                    self._bodies[bid] = {
                        'pos': (0.0, 0.0, 0.0),
                        'euler': (0.0, 0.0, 0.0)
                    }
                    return bid

                def getBasePositionAndOrientation(self, bodyId):
                    b = self._bodies.get(bodyId, {'pos': (0.0,0.0,0.0),'euler':(0.0,0.0,0.0)})
                    # return position and a quaternion-like tuple (we'll store euler in second element)
                    e = b['euler']
                    # represent quaternion as euler tuple for simplicity
                    return b['pos'], (e[0], e[1], e[2])

                def resetBasePositionAndOrientation(self, bodyId, pos, orn):
                    # orn may be quaternion or euler tuple; accept either
                    if isinstance(orn, tuple) and len(orn) == 3:
                        euler = orn
                    else:
                        euler = (0.0, 0.0, 0.0)
                    self._bodies.setdefault(bodyId, {})['pos'] = tuple(pos)
                    self._bodies.setdefault(bodyId, {})['euler'] = tuple(euler)
                    return True

                def getEulerFromQuaternion(self, q):
                    # q may be our stored 'euler' tuple; return as-is
                    if isinstance(q, tuple) and len(q) == 3:
                        return q
                    return (0.0, 0.0, 0.0)

                def getQuaternionFromEuler(self, e):
                    # return euler as a placeholder
                    return tuple(e)

            p = _FakePB()
            physicsClient = 1
            planeId = None
            cubeId = p.createMultiBody()
            _sim_initialized = True
            return True
        except Exception:
            p = None
            _sim_initialized = False
            return False


def is_pybullet_available():
    # If not yet attempted, attempt lazy init
    if not _sim_initialized:
        return ensure_simulation()
    return p is not None

# 全局状态管理
class MotionStatus:
    def __init__(self):
        self._status = "idle"  # idle, running, error
        self._error_message = ""
        self._current_operation = ""  # 当前执行的操作
        self._coordinate_system = "joint"  # 坐标系
        self._collision_detection_enabled = False  # 碰撞检测状态
        self._torque_feedforward_enabled = False  # 力矩前馈状态
        self._lock = threading.Lock()  # 线程锁，确保状态修改的线程安全
    
    @property
    def status(self):
        with self._lock:
            return self._status
    
    @status.setter
    def status(self, value):
        with self._lock:
            self._status = value
    
    @property
    def error_message(self):
        with self._lock:
            return self._error_message
    
    @error_message.setter
    def error_message(self, value):
        with self._lock:
            self._error_message = value
    
    @property
    def current_operation(self):
        with self._lock:
            return self._current_operation
    
    @current_operation.setter
    def current_operation(self, value):
        with self._lock:
            self._current_operation = value
    
    @property
    def coordinate_system(self):
        with self._lock:
            return self._coordinate_system
    
    @coordinate_system.setter
    def coordinate_system(self, value):
        with self._lock:
            self._coordinate_system = value
    
    @property
    def collision_detection_enabled(self):
        with self._lock:
            return self._collision_detection_enabled
    
    @collision_detection_enabled.setter
    def collision_detection_enabled(self, value):
        with self._lock:
            self._collision_detection_enabled = value
    
    @property
    def torque_feedforward_enabled(self):
        with self._lock:
            return self._torque_feedforward_enabled
    
    @torque_feedforward_enabled.setter
    def torque_feedforward_enabled(self, value):
        with self._lock:
            self._torque_feedforward_enabled = value
    
    def set_error(self, error_msg):
        with self._lock:
            self._status = "error"
            self._error_message = error_msg
    
    def set_running(self, operation=""):
        with self._lock:
            self._status = "running"
            self._current_operation = operation
            self._error_message = ""
    
    def set_idle(self):
        with self._lock:
            self._status = "idle"
            self._current_operation = ""
            self._error_message = ""

# 创建全局状态实例
motion_status = MotionStatus()

# 缓存最后已知的位姿/角度，用于在 error 或仿真不可用时仍能返回最近的有效读数
_last_known_lock = threading.RLock()
_last_known_state = {
    'pos': [0.0, 0.0, 0.0],
    'angle': 0.0,
    'timestamp': 0.0
}

# 硬件急停控制器（延迟初始化，基于 robot_config.hardware_estop）
_estop_controller = None

def _get_estop_controller():
    global _estop_controller
    if _estop_controller is None:
        try:
            he = robot_config.hardware_estop
            backend = he.get('backend') if isinstance(he, dict) else None
            cfg = he.get('config') if isinstance(he, dict) else {}
            _estop_controller = EmergencyStopController(backend=backend, config=cfg)
        except Exception:
            _estop_controller = EmergencyStopController(backend=None, config={})
    return _estop_controller

def translate_object(object_id, x_offset, y_offset, z_offset, duration=1):
    """平移物体（增强版）"""
    try:
        # ensure simulation is initialized (or raise if not available)
        if not ensure_simulation():
            raise ImportError("pybullet not available")
        # 安全检查
        if safety_monitor.collision_detected:
            raise Exception("检测到碰撞，无法执行运动")

        # if caller didn't supply an object_id, use the module cubeId
        if not object_id:
            object_id = cubeId
        
        # 设置运行状态
        motion_status.set_running(f"平移: ({x_offset}, {y_offset}, {z_offset}), 耗时: {duration}s")
        
        current_pos, current_orn = p.getBasePositionAndOrientation(object_id)
        target_pos = (current_pos[0] + x_offset, current_pos[1] + y_offset, current_pos[2] + z_offset)
        # 检查目标位置是否在工作空间内
        try:
            if not safety_monitor.is_inside_workspace(target_pos):
                raise Exception(f"目标位置{target_pos}超出工作空间")
        except Exception as e:
            # 若检查函数异常或返回 False，则当作越界处理
            error_msg = f"工作空间边界检查失败或越界: {e}"
            print(error_msg)
            motion_status.set_error(error_msg)
            raise
        
        print(f"开始平移: 从 {current_pos} 移动到 {target_pos}, 耗时 {duration} 秒")
        print(f"当前坐标系: {motion_status.coordinate_system}")
        
        # 检查力矩前馈是否启用
        if motion_status.torque_feedforward_enabled:
            print("力矩前馈控制已启用")
        
        steps = 50
        for i in range(steps):
            # 检查是否被设置为错误状态（比如外部中断）
            if motion_status.status == "error":
                print("平移被中断")
                return
            
            # 检查碰撞检测
            if motion_status.collision_detection_enabled and safety_monitor.collision_detected:
                print("检测到碰撞，停止运动")
                motion_status.set_error("碰撞检测触发")
                return
            
            progress = i / steps
            new_pos = (
                current_pos[0] + x_offset * progress,
                current_pos[1] + y_offset * progress,
                current_pos[2] + z_offset * progress
            )
            p.resetBasePositionAndOrientation(object_id, new_pos, current_orn)
            time.sleep(duration / steps)
        
        final_pos = p.getBasePositionAndOrientation(object_id)[0]
        print(f"平移完成! 最终位置: {final_pos}")
        
        # 设置空闲状态
        motion_status.set_idle()
        
    except Exception as e:
        error_msg = f"平移过程中发生错误: {str(e)}"
        print(error_msg)
        motion_status.set_error(error_msg)
        raise

def rotate_object(object_id, angle_deg, duration=1):
    """旋转物体（增强版）"""
    try:
        if not ensure_simulation():
            raise ImportError("pybullet not available")
        # 安全检查
        if safety_monitor.collision_detected:
            raise Exception("检测到碰撞，无法执行运动")

        # use default cubeId when object_id is falsy
        if not object_id:
            object_id = cubeId
        
        # 设置运行状态
        motion_status.set_running(f"旋转: {angle_deg}度, 耗时: {duration}s")
        
        # 获取当前朝向（转成度，方便计算）
        current_orn = p.getBasePositionAndOrientation(object_id)[1]
        current_angle_rad = p.getEulerFromQuaternion(current_orn)[2]  # Z轴旋转弧度
        current_angle_deg = current_angle_rad * 180 / 3.14159  # 转成度
        
        # 计算目标旋转角度
        target_angle_deg = current_angle_deg + angle_deg
        
        print(f"开始旋转：从 {current_angle_deg:.1f} 度旋转到 {target_angle_deg:.1f} 度，耗时 {duration} 秒")
        print(f"当前坐标系: {motion_status.coordinate_system}")
        
        # 检查力矩前馈是否启用
        if motion_status.torque_feedforward_enabled:
            print("力矩前馈控制已启用")
        
        # 分步旋转
        steps = 50
        for i in range(steps):
            # 检查是否被设置为错误状态
            if motion_status.status == "error":
                print("旋转被中断")
                return
                
            # 检查碰撞检测
            if motion_status.collision_detection_enabled and safety_monitor.collision_detected:
                print("检测到碰撞，停止运动")
                motion_status.set_error("碰撞检测触发")
                return
                
            progress = i / steps
            # 计算当前步骤的角度（分步逼近目标角度）
            current_step_angle_deg = current_angle_deg + (target_angle_deg - current_angle_deg) * progress
            current_step_angle_rad = current_step_angle_deg * 3.14159 / 180  # 转成弧度
            
            # 生成旋转四元数
            new_orn = p.getQuaternionFromEuler([0, 0, current_step_angle_rad])
            
            # 更新物体旋转状态
            current_pos = p.getBasePositionAndOrientation(object_id)[0]
            p.resetBasePositionAndOrientation(object_id, current_pos, new_orn)
            time.sleep(duration / steps)
        
        # 打印旋转结果
        final_orn = p.getBasePositionAndOrientation(object_id)[1]
        final_angle_deg = p.getEulerFromQuaternion(final_orn)[2] * 180 / 3.14159
        print(f"旋转完成！最终角度：{final_angle_deg:.1f} 度")
        
        # 设置空闲状态
        motion_status.set_idle()
        
    except Exception as e:
        error_msg = f"旋转过程中发生错误: {str(e)}"
        print(error_msg)
        motion_status.set_error(error_msg)
        raise

def get_current_status():
    """获取当前运动状态信息"""
    try:
        # 如果仿真可用，从仿真中读取并更新最后已知值
        if ensure_simulation():
            current_pos = p.getBasePositionAndOrientation(cubeId)[0]
            current_orn = p.getBasePositionAndOrientation(cubeId)[1]
            current_angle_rad = p.getEulerFromQuaternion(current_orn)[2]
            current_angle_deg = current_angle_rad * 180 / 3.14159

            # 更新最后已知位姿缓存
            try:
                with _last_known_lock:
                    _last_known_state['pos'] = list(current_pos)
                    _last_known_state['angle'] = current_angle_deg
                    _last_known_state['timestamp'] = time.time()
            except Exception:
                pass

            return {
                "status": motion_status.status,
                "current_operation": motion_status.current_operation,
                "error_message": motion_status.error_message,
                "current_pos": list(current_pos),
                "current_angle": current_angle_deg,
                "coordinate_system": motion_status.coordinate_system,
                "collision_detection_enabled": motion_status.collision_detection_enabled,
                "torque_feedforward_enabled": motion_status.torque_feedforward_enabled
            }

        # 仿真不可用：若处于 error 状态，返回最后已知位姿以便 SSE/监控保留上次读数
        if motion_status.status == 'error':
            try:
                with _last_known_lock:
                    return {
                        "status": motion_status.status,
                        "current_operation": motion_status.current_operation,
                        "error_message": motion_status.error_message,
                        "current_pos": list(_last_known_state.get('pos', [0.0,0.0,0.0])),
                        "current_angle": float(_last_known_state.get('angle', 0.0)),
                        "coordinate_system": motion_status.coordinate_system,
                        "collision_detection_enabled": motion_status.collision_detection_enabled,
                        "torque_feedforward_enabled": motion_status.torque_feedforward_enabled
                    }
            except Exception:
                pass

        # 否则回退到安全默认值
        return {
            "status": motion_status.status,
            "current_operation": motion_status.current_operation,
            "error_message": motion_status.error_message,
            "current_pos": [0, 0, 0],
            "current_angle": 0,
            "coordinate_system": motion_status.coordinate_system,
            "collision_detection_enabled": motion_status.collision_detection_enabled,
            "torque_feedforward_enabled": motion_status.torque_feedforward_enabled
        }
    except Exception as e:
        error_msg = f"获取状态时发生错误: {str(e)}"
        motion_status.set_error(error_msg)
        return {
            "status": "error",
            "current_operation": "",
            "error_message": error_msg,
            "current_pos": [0, 0, 0],
            "current_angle": 0,
            "coordinate_system": "joint",
            "collision_detection_enabled": False,
            "torque_feedforward_enabled": False
        }

def reset_error():
    """重置错误状态"""
    motion_status.set_idle()
    safety_monitor.reset_collision()
    return True


# -------------------------- 高级运镜与力矩前馈（降级实现以支持 V2 路由） --------------------------
class _TorqueFeedforward:
    def __init__(self):
        self.params = {"mass": [], "inertia": [], "friction": []}
        self._collision_sensitivity = {}

    def update_dynamics_params(self, params: dict):
        self.params.update(params)
        return True

    def set_collision_sensitivity(self, axis: int, sensitivity: int):
        if axis < 1 or axis > 6 or sensitivity <= 0:
            return False
        self._collision_sensitivity[axis] = sensitivity
        return True


torque_feedforward = _TorqueFeedforward()


def preset_circle_motion(object_id, center_pos, radius=1.0, duration=10, clockwise=True):
    """环绕运镜预设：如果 simulation 可用则在圆周上分点移动，否则 sleep 模拟。"""
    try:
        if not ensure_simulation():
            # fallback: simple sleep
            time.sleep(duration)
            return

        motion_status.set_running("环绕运镜")
        import math
        steps = 36
        for i in range(steps):
            if motion_status.status == "error":
                return
            theta = (2 * math.pi * i) / steps
            if not clockwise:
                theta = -theta
            x = center_pos[0] + radius * math.cos(theta)
            y = center_pos[1] + radius * math.sin(theta)
            z = center_pos[2]
            try:
                p.resetBasePositionAndOrientation(cubeId, (x, y, z), p.getBasePositionAndOrientation(cubeId)[1])
            except Exception:
                pass
            time.sleep(max(0.01, duration / steps))

        motion_status.set_idle()
    except Exception as e:
        motion_status.set_error(str(e))
        raise


def preset_push_pull_motion(object_id, direction, distance=2.0, duration=8):
    """推拉运镜预设：在当前点沿 direction 轴往返移动。"""
    try:
        if not ensure_simulation():
            time.sleep(duration)
            return

        motion_status.set_running("推拉运镜")
        idx = {'x': 0, 'y': 1, 'z': 2}[direction]
        cur_pos = p.getBasePositionAndOrientation(cubeId)[0]
        pt1 = list(cur_pos)
        pt2 = list(cur_pos)
        pt1[idx] = cur_pos[idx] - distance / 2
        pt2[idx] = cur_pos[idx] + distance / 2
        # split into segments: cur -> pt2 -> pt1 -> cur
        pts = [pt1, pt2, pt1]
        seg_dur = max(0.5, duration / len(pts))
        for wp in pts:
            if motion_status.status == "error":
                return
            # move directly (linear interpolation)
            steps = 30
            start = p.getBasePositionAndOrientation(cubeId)[0]
            for i in range(steps):
                if motion_status.status == "error":
                    return
                frac = i / steps
                new_pos = (
                    start[0] + (wp[0] - start[0]) * frac,
                    start[1] + (wp[1] - start[1]) * frac,
                    start[2] + (wp[2] - start[2]) * frac,
                )
                try:
                    p.resetBasePositionAndOrientation(cubeId, new_pos, p.getBasePositionAndOrientation(cubeId)[1])
                except Exception:
                    pass
                time.sleep(max(0.01, seg_dur / steps))

        motion_status.set_idle()
    except Exception as e:
        motion_status.set_error(str(e))
        raise


def move_joint(joint_id, target_angle, speed=50.0):
    """单关节运动的降级实现（仅模拟时间和进度）。"""
    try:
        motion_status.set_running(f"关节{joint_id}移动到{target_angle}度")
        # simulate time proportional to angle change
        dur = max(0.5, abs(target_angle) / 90.0)
        steps = 20
        for i in range(steps):
            if motion_status.status == "error":
                return
            time.sleep(dur / steps)
        motion_status.set_idle()
    except Exception as e:
        motion_status.set_error(str(e))
        raise


def move_joints(target_angles, speed=50.0):
    """同步控制所有关节（降级实现）。"""
    try:
        motion_status.set_running("所有关节同步运动")
        dur = max(0.5, max(abs(a) for a in target_angles) / 90.0)
        steps = 30
        for i in range(steps):
            if motion_status.status == "error":
                return
            time.sleep(dur / steps)
        motion_status.set_idle()
    except Exception as e:
        motion_status.set_error(str(e))
        raise



def emergency_stop(reason="emergency stop triggered"):
    """触发紧急停止：将状态置为 error，并记录原因。"""
    # 1) 软件层面：设置 motion_status 为 error，通知后台任务中断
    motion_status.set_error(reason)
    # 2) 重置安全监控检测（保守策略）
    safety_monitor.reset_collision()

    # 3) 若配置启用了硬件急停，则尝试触发硬件
    try:
        he = getattr(robot_config, 'hardware_estop', {})
        if isinstance(he, dict) and he.get('enabled'):
            ctrl = _get_estop_controller()
            engaged = ctrl.engage()
            if engaged:
                # 记录在状态消息中
                motion_status.error_message = f"{reason} (hardware estop engaged)"
            else:
                motion_status.error_message = f"{reason} (hardware estop FAILED)"
    except Exception:
        # 忽略硬件触发错误，但保留软件急停
        pass

    return get_current_status()

def set_collision_detection(enabled=True):  # 添加参数
    """设置碰撞检测状态"""
    motion_status.collision_detection_enabled = enabled
    robot_config.enable_collision_detection(enabled)
    print(f"碰撞检测已{'启用' if enabled else '禁用'}")
    return True

def set_torque_feedforward(enabled=True):  # 添加参数
    """设置力矩前馈状态"""
    motion_status.torque_feedforward_enabled = enabled
    robot_config.enable_torque_feedforward(enabled)
    print(f"力矩前馈已{'启用' if enabled else '禁用'}")
    return True

# 测试脚本
if __name__ == "__main__":
    print("=== 运镜控制脚本测试开始 ===")
    print(f"初始状态: {get_current_status()}")
    
    # ensure sim available for demo
    ensure_simulation()
    translate_object(cubeId, x_offset=2, y_offset=1, z_offset=0, duration=2)
    print(f"平移后状态: {get_current_status()}")
    
    time.sleep(1)
    rotate_object(cubeId, angle_deg=90, duration=1)
    print(f"旋转后状态: {get_current_status()}")
    
    time.sleep(1)
    print("=== 运镜控制脚本测试结束 ===")
    p.disconnect()