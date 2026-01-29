"""
机器人配置管理模块
负责动力学参数、坐标系配置、安全设置等
"""

class RobotConfig:
    """机器人配置类"""
    
    def __init__(self):
        self.dynamics_params = {
            'axis1': {'error': 0.0, 'sensitivity': 50},
            'axis2': {'error': 0.0, 'sensitivity': 50},
            'axis3': {'error': 0.0, 'sensitivity': 50},
            'axis4': {'error': 0.0, 'sensitivity': 50},
            'axis5': {'error': 0.0, 'sensitivity': 50},
            'axis6': {'error': 0.0, 'sensitivity': 50}
        }
        self.coordinate_systems = {
            'joint': '关节坐标系',
            'cartesian': '直角坐标系', 
            'tool': '工具坐标系',
            'user': '用户坐标系'
        }
        self.current_coordinate_system = 'joint'
        self.collision_detection = False
        self.torque_feedforward = False
        self.safety_limits = {
            'max_velocity': 100,
            'max_acceleration': 50,
            'working_range': 100,
            # 工作空间边界：[[x_min,x_max],[y_min,y_max],[z_min,z_max]]
            'workspace': [
                (0.0, 1.2),
                (0.0, 1.0),
                (0.0, 0.8)
            ]
        }
        # 是否锁定示教器（禁止示教器操作）
        self.teach_locked = False
        # 碰撞检测参数化
        self.collision_params = {
            # 灵敏度（数值越小越灵敏，数值解释可与辨识误差关联），默认50
            'sensitivity': 50,
            # 指令位置响应时间（秒），用于避免延迟报错
            'response_time': 0.1,
            # 误差允许时间（秒），在误差触发后允许的宽限时间以防止误报警
            'allowed_error_time': 0.5
        }
        # API key 管理（用于保护敏感接口）
        # 默认为空列表；部署时请通过环境变量或管理接口注入密钥
        self.allowed_api_keys = []

    def add_api_key(self, key: str):
        try:
            if key and key not in self.allowed_api_keys:
                self.allowed_api_keys.append(key)
            return True
        except Exception:
            return False

    def remove_api_key(self, key: str):
        try:
            if key in self.allowed_api_keys:
                self.allowed_api_keys.remove(key)
            return True
        except Exception:
            return False

    def validate_api_key(self, key: str) -> bool:
        """验证传入的 API key 是否在白名单中。"""
        try:
            if not key:
                return False
            return key in self.allowed_api_keys
        except Exception:
            return False
        # 硬件急停配置（用于与 PLC / IO 设备对接）
        self.hardware_estop = {
            # 是否启用硬件急停触发（默认 False，仅软件层急停）
            'enabled': False,
            # backend: 'gpio' | 'modbus' | None
            'backend': None,
            # backend 相关配置，如 {'gpio_pin':17} 或 {'modbus_host':'192.168.1.10','modbus_port':502}
            'config': {}
        }

    def enable_hardware_estop(self, enabled: bool = True, backend: str = None, config: dict = None):
        """启用或配置硬件急停后端。"""
        try:
            self.hardware_estop['enabled'] = bool(enabled)
            if backend is not None:
                self.hardware_estop['backend'] = backend
            if config is not None:
                self.hardware_estop['config'] = dict(config)
            return True
        except Exception:
            return False
    
    def set_dynamics_params(self, axis, error, sensitivity):
        """设置动力学参数"""
        if axis in self.dynamics_params:
            self.dynamics_params[axis]['error'] = error
            self.dynamics_params[axis]['sensitivity'] = sensitivity
    
    def set_coordinate_system(self, system):
        """设置坐标系"""
        if system in self.coordinate_systems:
            self.current_coordinate_system = system
    
    def enable_collision_detection(self, enable=True):
        """启用碰撞检测"""
        self.collision_detection = enable
    
    def enable_torque_feedforward(self, enable=True):
        """启动力矩前馈"""
        self.torque_feedforward = enable

    def lock_teach(self, locked: bool = True):
        """锁定或解锁示教器输入（True 表示锁定，禁止示教器操作）"""
        self.teach_locked = bool(locked)

    def speed_to_duration(self, speed_percent: float) -> float:
        """把速度百分比映射为轨迹运行时长。

        映射规则（按文档要求）：
        - 速度 100 -> 10 秒
        - 速度 50  -> 20 秒
        - 速度 10  -> 100 秒

        使用分段线性插值（10-50 和 50-100 两段）。对于超出范围的值做裁剪。
        """
        try:
            sp = float(speed_percent)
        except Exception:
            sp = 10.0

        if sp <= 10:
            return 100.0
        if sp <= 50:
            # 线性从 (10,100) 到 (50,20)
            # slope = (20-100)/(50-10) = -2
            return 120.0 - 2.0 * sp
        if sp <= 100:
            # 线性从 (50,20) 到 (100,10)
            # slope = (10-20)/(100-50) = -0.2
            return 30.0 - 0.2 * sp
        # 超过100按100处理
        return 10.0

    def set_collision_params(self, sensitivity: int = None, response_time: float = None, allowed_error_time: float = None):
        """设置碰撞检测参数，None 表示不修改对应值"""
        if sensitivity is not None:
            try:
                self.collision_params['sensitivity'] = int(sensitivity)
            except Exception:
                pass
        if response_time is not None:
            try:
                self.collision_params['response_time'] = float(response_time)
            except Exception:
                pass
        if allowed_error_time is not None:
            try:
                self.collision_params['allowed_error_time'] = float(allowed_error_time)
            except Exception:
                pass

    def set_workspace(self, x_range=None, y_range=None, z_range=None):
        """设置工作空间边界，参数为二元序列 (min, max)。None 表示不修改对应维度。"""
        try:
            w = self.safety_limits.get('workspace', None)
            if w is None or not isinstance(w, (list, tuple)):
                w = [(0.0,1.2),(0.0,1.0),(0.0,0.8)]
            # parse and set
            if x_range is not None:
                self.safety_limits['workspace'][0] = (float(x_range[0]), float(x_range[1]))
            if y_range is not None:
                self.safety_limits['workspace'][1] = (float(y_range[0]), float(y_range[1]))
            if z_range is not None:
                self.safety_limits['workspace'][2] = (float(z_range[0]), float(z_range[1]))
            return True
        except Exception:
            return False

    def get_workspace(self):
        w = self.safety_limits.get('workspace')
        # return normalized list of lists
        try:
            return [list(w[0]), list(w[1]), list(w[2])]
        except Exception:
            return [[0.0,1.2],[0.0,1.0],[0.0,0.8]]

    def get_collision_params(self):
        return dict(self.collision_params)

# 全局配置实例
robot_config = RobotConfig()