from flask import Blueprint, request, jsonify, Response, stream_with_context
import json
import time
import functools
from flask import g
import sys
import os
import time  # 模拟函数需要

# 修正导入路径 - 确保能正确导入motion_control模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)
    
import logging
logger = logging.getLogger(__name__)
logger.debug(f"当前目录: {current_dir}")
logger.debug(f"父目录: {parent_dir}")
logger.debug(f"Python路径: {sys.path}")

from motion_control import (
    translate_object,
    rotate_object,
    get_current_status,
    reset_error,
    emergency_stop,
    set_collision_detection as mc_set_collision_detection,
    set_torque_feedforward as mc_set_torque_feedforward,
    is_pybullet_available,
)
# 直接引用模块以便访问可选的高级函数（如 preset_circle_motion 等），若不存在则降级模拟
import motion_control as mc
from robot_config import robot_config
from dynamics_identification import dynamics_identification
from safety_monitor import safety_monitor
from system_integration import system_integration
print("imports loaded successfully")

# 注意: 之前这里在模块导入时缓存 pybullet 可用性，会导致运行时安装/可用性变化无法被检测到。
# 改为运行时检查函数，避免服务启动后无法启用运动控制的问题。
def motion_control_available():
    try:
        return bool(is_pybullet_available())
    except Exception:
        return False

# 数据存储
try:
    from app.data_store import get_store
    store = get_store()
except Exception:
    store = None

# -------------------------- 任务管理（后台执行） --------------------------
import threading
import uuid


class TaskManager:
    def __init__(self):
        self.active_tasks = {}  # task_id -> {thread, start_time, cancel_flag}
        self.lock = threading.RLock()
        self.task_expire_seconds = 30

    def create_task(self, task_func, *args, **kwargs):
        task_id = str(uuid.uuid4())[:8]

        def runner(tid, func, a, kw):
            try:
                func(tid, *a, **kw)
            except Exception as e:
                logger.exception(f"任务{tid}执行异常: {e}")

        thread = threading.Thread(target=runner, args=(task_id, task_func, args, kwargs), daemon=True)
        with self.lock:
            self.active_tasks[task_id] = {
                "thread": thread,
                "start_time": time.time(),
                "cancel": False
            }
            thread.start()
        return task_id

    def get_task_status(self, task_id: str):
        with self.lock:
            info = self.active_tasks.get(task_id)
            if not info:
                return "not_found"
            return "running" if info["thread"].is_alive() else "finished"

    def cancel_task(self, task_id: str):
        with self.lock:
            info = self.active_tasks.get(task_id)
            if not info:
                return False, "任务不存在"
            info["cancel"] = True
            return True, "取消请求已发送（若任务可中断则会停止）"

    def cancel_all(self):
        with self.lock:
            for tid, info in self.active_tasks.items():
                info["cancel"] = True
        logger.warning("已向所有后台任务发送取消请求")
        return True


task_manager = TaskManager()

# 为早期路由使用提前定义 API key 验证器与速率限制（防止装饰器被提前引用导致导入失败）
# 这段定义与 V2 区域的实现等价，后者可覆盖运行时行为。
_last_cmd_time = {}  # ip -> timestamp
_min_cmd_interval = 0.05  # 最小间隔秒（防止高频指令）

def _get_client_ip():
    ip = request.headers.get('X-Real-IP') or request.headers.get('X-Forwarded-For') or request.remote_addr
    return ip

def require_api_key(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        api_key = None
        auth = request.headers.get('Authorization')
        if auth and auth.lower().startswith('bearer '):
            api_key = auth.split(None, 1)[1].strip()
        if not api_key:
            api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

        try:
            if not robot_config.validate_api_key(api_key):
                return jsonify({"code": 401, "msg": "Unauthorized: invalid API key", "data": None}), 401
        except Exception:
            return jsonify({"code": 500, "msg": "Server error during auth", "data": None}), 500

        ip = _get_client_ip()
        now = time.time()
        last = _last_cmd_time.get(ip)
        if last and (now - last) < _min_cmd_interval:
            return jsonify({"code": 429, "msg": "Too Many Requests", "data": None}), 429
        _last_cmd_time[ip] = now

        g.api_key = api_key
        return fn(*args, **kwargs)
    return wrapper

# 创建蓝图（用于管理接口）
bp = Blueprint('api', __name__, url_prefix='/api/v1')
_app_start_time = time.time()

# 添加测试路由 - 用于验证API路由是否正常工作
@bp.route('/test', methods=['GET'])
def test_route():
    return jsonify({
        "code": 200,
        "msg": "API路由测试成功",
        "data": {
            "service": "运镜控制API",
            "version": "1.0",
            "motion_control_available": motion_control_available()
        }
    })

# 全局错误处理kup/
@bp.errorhandler(404)
def handle_404(error):
    return jsonify({
        "code": 404,
        "msg": "接口不存在",
        "data": None
    }), 404

@bp.errorhandler(500)
def handle_500(error):
    return jsonify({
        "code": 500,
        "msg": "服务器内部错误",
        "data": None
    }), 500

@bp.errorhandler(405)
def handle_405(error):
    return jsonify({
        "code": 405,
        "msg": "请求方法不允许",
        "data": None
    }), 405

# 1. 平移控制接口（修复参数验证逻辑）
@bp.route('/translate', methods=['POST'])
@require_api_key
def translate():
    try:
        # 新增：打印日志，验证接口是否进入正确逻辑
        print("=== 进入平移接口，开始参数校验 ===")
        
        # 检查是否有请求体
        if not request.data:
            return jsonify({
                "code": 400, 
                "msg": "请求体不能为空",
                "data": None
            }), 400
            
        # 强制解析JSON请求体，无请求体/解析失败直接返回400
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({
                "code": 400, 
                "msg": "请求体必须为JSON格式",
                "data": None
            }), 400
        
        # 校验必填参数（x_offset/y_offset/z_offset）
        required_fields = ['x_offset', 'y_offset', 'z_offset']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                "code": 400, 
                "msg": f"缺少必填参数: {', '.join(missing_fields)}",
                "data": None
            }), 400
        
        # 参数类型校验+合法性校验（避免负数时长）
        try:
            x = float(data['x_offset'])
            y = float(data['y_offset'])
            z = float(data['z_offset'])
            duration = float(data.get('duration', 1))  # 默认为1秒
            
            # 校验时长不能为负数
            if duration < 0:
                return jsonify({
                    "code": 400,
                    "msg": "时长duration不能为负数",
                    "data": None
                }), 400
        
        except (TypeError, ValueError):
            return jsonify({
                "code": 400,
                "msg": "参数类型错误，偏移量（x_offset/y_offset/z_offset）和时长（duration）必须为数字",
                "data": None
            }), 400
        
        # 检查运动控制模块是否可用（运行时检查）
        if not motion_control_available():
            return jsonify({
                "code": 503,
                "msg": "运动控制模块不可用",
                "data": None
            }), 503
        
        # 调用平移函数（仅参数校验全通过才执行）
        # 传入 None 让 motion_control 使用其内部默认 cubeId（模块级变量），避免在路由模块中直接依赖该变量。
        translate_object(None, x, y, z, duration)
        
        # 获取执行后的状态并返回
        status_info = get_current_status()
        
        return jsonify({
            "code": 200,
            "msg": "平移指令执行成功",
            "data": {
                "current_pos": status_info["current_pos"],
                "status": status_info["status"]
            }
        })
        
    except Exception as e:
        error_msg = f"平移执行失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

# 2. 旋转控制接口（修复参数验证逻辑）
@bp.route('/rotate', methods=['POST'])
@require_api_key
def rotate():
    try:
        # 检查是否有请求体
        if not request.data:
            return jsonify({
                "code": 400, 
                "msg": "请求体不能为空",
                "data": None
            }), 400
            
        # 强制解析JSON请求体，无请求体/解析失败直接返回400
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({
                "code": 400, 
                "msg": "请求体必须为JSON格式",
                "data": None
            }), 400
        
        # 校验必填参数（angle_deg）
        if 'angle_deg' not in data:
            return jsonify({
                "code": 400, 
                "msg": "缺少必填参数: angle_deg",
                "data": None
            }), 400
        
        # 参数类型校验+合法性校验（避免负数时长）
        try:
            angle = float(data['angle_deg'])
            duration = float(data.get('duration', 1))  # 默认为1秒
            
            # 校验时长不能为负数
            if duration < 0:
                return jsonify({
                    "code": 400,
                    "msg": "时长duration不能为负数",
                    "data": None
                }), 400
        except (TypeError, ValueError):
            return jsonify({
                "code": 400, 
                "msg": "参数类型错误，角度（angle_deg）和时长（duration）必须为数字",
                "data": None
            }), 400
        
        # 检查运动控制模块是否可用（运行时检查）
        if not motion_control_available():
            return jsonify({
                "code": 503,
                "msg": "运动控制模块不可用",
                "data": None
            }), 503
        
        # 调用旋转函数（仅参数校验全通过才执行）
        # 传入 None 让 motion_control 使用其内部默认 cubeId（模块级变量），避免在路由模块中直接依赖该变量。
        rotate_object(None, angle, duration)
        
        # 获取执行后的状态并返回
        status_info = get_current_status()
        
        return jsonify({
            "code": 200,
            "msg": "旋转指令执行成功",
            "data": {
                "current_angle": status_info["current_angle"],
                "status": status_info["status"]
            }
        })
        
    except Exception as e:
        error_msg = f"旋转执行失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

# 3. 状态查询接口
@bp.route('/status', methods=['GET'])
def get_status():
    try:
        # 检查运动控制模块是否可用（运行时检查）
        if not motion_control_available():
            return jsonify({
                "code": 503,
                "msg": "运动控制模块不可用",
                "data": None
            }), 503
        
        status_info = get_current_status()
        
        return jsonify({
            "code": 200,
            "msg": "状态查询成功",
            "data": {
                "current_pos": status_info["current_pos"],
                "current_angle": status_info["current_angle"],
                "status": status_info["status"],
                "current_operation": status_info["current_operation"],
                "coordinate_system": status_info["coordinate_system"],
                "collision_detection_enabled": status_info["collision_detection_enabled"],
                "torque_feedforward_enabled": status_info["torque_feedforward_enabled"],
                "error_code": 1 if status_info["status"] == "error" else 0,
                "error_message": status_info["error_message"]
            }
        })
        
    except Exception as e:
        error_msg = f"状态查询失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500


# 临时 Demo 路由（仅限本地访问），用于在服务进程内触发简单移动，帮助验证 SSE/last_known_state
@bp.route('/demo/move', methods=['POST'])
def demo_move():
    try:
        # 只允许本地回环访问
        ip = request.remote_addr
        if ip not in ('127.0.0.1', '::1', 'localhost'):
            return jsonify({"code": 403, "msg": "Forbidden: demo only allowed from localhost", "data": None}), 403

        data = request.get_json(force=True, silent=True) or {}
        dx = float(data.get('x', 0.2))
        dy = float(data.get('y', 0.0))
        dz = float(data.get('z', 0.0))
        dur = float(data.get('duration', 0.5))

        def _runner(tid, dx, dy, dz, dur):
            try:
                # 使用 motion_control 里的移动函数（会更新 last_known_state）
                translate_object(None, x_offset=dx, y_offset=dy, z_offset=dz, duration=dur)
            except Exception:
                logger.exception('demo move failed')

        tid = task_manager.create_task(_runner, dx, dy, dz, dur)
        return jsonify({"code": 200, "msg": "demo move started", "data": {"task_id": tid}})
    except Exception as e:
        logger.exception('demo move error')
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500

# 4. 错误重置接口
@bp.route('/reset', methods=['POST'])
def reset_error_route():
    try:
        success = reset_error()
        
        if success:
            return jsonify({
                "code": 200,
                "msg": "错误状态已重置",
                "data": None
            })
        else:
            return jsonify({
                "code": 500,
                "msg": "重置失败",
                "data": None
            }), 500
            
    except Exception as e:
        error_msg = f"重置操作失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500


# 5.1 紧急停止接口
@bp.route('/emergency/stop', methods=['POST'])
def emergency_stop_route():
    try:
        # 先取消所有后台任务再触发紧急停止，确保没有后台运镜继续运行
        try:
            task_manager.cancel_all()
        except Exception:
            logger.exception("取消后台任务失败")

        # 支持可选参数 ?hardware=true 强制触发硬件急停（若已配置）
        use_hw = request.args.get('hardware', 'false').lower() in ['1', 'true', 'yes']
        if use_hw:
            # 尝试启用硬件急停配置（不会覆盖持久配置，只做触发）
            try:
                # 硬件触发由 motion_control 中根据 robot_config 配置执行；这里仅 ensure flag
                pass
            except Exception:
                logger.exception("尝试触发硬件急停时发生错误")

        status_info = emergency_stop()
        return jsonify({
            "code": 200,
            "msg": "紧急停止已触发，后台任务已发送取消请求",
            "data": {
                "current_pos": status_info.get("current_pos"),
                "current_angle": status_info.get("current_angle"),
                "status": status_info.get("status"),
                "error_message": status_info.get("error_message")
            }
        })
    except Exception as e:
        error_msg = f"紧急停止失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

# 5. 系统信息接口
@bp.route('/info', methods=['GET'])
def get_info():
    return jsonify({
        "code": 200,
        "msg": "系统信息查询成功",
        "data": {
            "service": "运镜控制API",
            "version": "1.0",
                "motion_control_available": motion_control_available(),
            "endpoints": [
                "POST /api/v1/translate - 平移控制",
                "POST /api/v1/rotate - 旋转控制", 
                "POST /api/v1/emergency/stop - 紧急停止",
                "GET /api/v1/status - 状态查询",
                "POST /api/v1/reset - 错误重置",
                "GET /api/v1/info - 系统信息",
                "POST /api/v1/dynamics/identification - 动力学参数辨识",
                "GET /api/v1/dynamics/identification/status - 辨识状态查询",
                "POST /api/v1/safety/collision/reset - 重置碰撞状态",
                "GET /api/v1/safety/status - 安全状态查询",
                "POST /api/v1/config/coordinate-system - 设置坐标系",
                "POST /api/v1/config/dynamics - 设置动力学参数",
                "GET /api/v1/system/status - 系统集成状态查询"
            ]
        }
    })

# 6. 动力学参数辨识接口
@bp.route('/dynamics/identification', methods=['POST'])
def start_dynamics_identification():
    """开始动力学参数辨识"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({
                "code": 400, 
                "msg": "请求体必须为JSON格式",
                "data": None
            }), 400
        
        trajectory_range = data.get('trajectory_range', 10)
        trajectory_speed = data.get('trajectory_speed', 10)
        # 安全校验：示教器锁定与工作空间无碰撞
        from robot_config import robot_config
        from safety_monitor import safety_monitor

        if not robot_config.teach_locked:
            return jsonify({"code": 423, "msg": "请先锁定示教器以禁止示教器操作", "data": None}), 423

        ok, reason = dynamics_identification.test_trajectory_safety(trajectory_range, trajectory_speed)
        if not ok:
            return jsonify({"code": 400, "msg": f"轨迹安全校验失败: {reason}", "data": None}), 400

        # 触发辨识（会在后台线程运行）
        success, message = dynamics_identification.start_identification(
            trajectory_range, trajectory_speed
        )
        
        if success:
            return jsonify({
                "code": 200,
                "msg": message,
                "data": {
                    "identification_id": id(dynamics_identification),
                    "trajectory_range": trajectory_range,
                    "trajectory_speed": trajectory_speed
                }
            })
        else:
            return jsonify({
                "code": 400,
                "msg": message,
                "data": None
            }), 400
            
    except Exception as e:
        error_msg = f"动力学参数辨识失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/dynamics/identification/stop', methods=['POST'])
def stop_dynamics_identification():
    """停止动力学参数辨识"""
    try:
        success, message = dynamics_identification.stop_identification()
        
        if success:
            return jsonify({
                "code": 200,
                "msg": message,
                "data": None
            })
        else:
            return jsonify({
                "code": 400,
                "msg": message,
                "data": None
            }), 400
            
    except Exception as e:
        error_msg = f"停止辨识失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/dynamics/identification/status', methods=['GET'])
def get_identification_status():
    """获取辨识状态"""
    try:
        return jsonify({
            "code": 200,
            "msg": "获取辨识状态成功",
            "data": {
                "is_identifying": dynamics_identification.is_identifying,
                "progress": dynamics_identification.progress,
                "current_trajectory_range": dynamics_identification.current_trajectory_range,
                "current_trajectory_speed": dynamics_identification.current_trajectory_speed,
                "results": dynamics_identification.identification_results
            }
        })
        
    except Exception as e:
        error_msg = f"获取辨识状态失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

# 7. 安全监控接口
@bp.route('/safety/collision/reset', methods=['POST'])
def reset_collision():
    """重置碰撞状态"""
    try:
        success = safety_monitor.reset_collision()
        
        if success:
            return jsonify({
                "code": 200,
                "msg": "碰撞状态已重置",
                "data": None
            })
        else:
            return jsonify({
                "code": 500,
                "msg": "重置失败",
                "data": None
            }), 500
            
    except Exception as e:
        error_msg = f"重置碰撞状态失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/safety/status', methods=['GET'])
def get_safety_status():
    """获取安全状态"""
    try:
        return jsonify({
            "code": 200,
            "msg": "获取安全状态成功",
            "data": {
                "collision_detected": safety_monitor.collision_detected,
                "monitoring_active": safety_monitor.monitoring,
                "safety_limits": safety_monitor.safety_limits
            }
        })
        
    except Exception as e:
        error_msg = f"获取安全状态失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/safety/collision-detection', methods=['POST'])
def set_collision_detection():
    """设置碰撞检测"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'enabled' not in data:
            return jsonify({
                "code": 400, 
                "msg": "缺少enabled参数",
                "data": None
            }), 400
        
        enabled = data['enabled']
        success = mc_set_collision_detection(enabled)
        
        if success:
            return jsonify({
                "code": 200,
                "msg": f"碰撞检测已{'启用' if enabled else '禁用'}",
                "data": {
                    "collision_detection_enabled": enabled
                }
            })
        else:
            return jsonify({
                "code": 500,
                "msg": "设置失败",
                "data": None
            }), 500
            
    except Exception as e:
        error_msg = f"设置碰撞检测失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/safety/torque-feedforward', methods=['POST'])
def set_torque_feedforward():
    """设置力矩前馈"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'enabled' not in data:
            return jsonify({
                "code": 400, 
                "msg": "缺少enabled参数",
                "data": None
            }), 400
        
        enabled = data['enabled']
        success = mc_set_torque_feedforward(enabled)
        
        if success:
            return jsonify({
                "code": 200,
                "msg": f"力矩前馈已{'启用' if enabled else '禁用'}",
                "data": {
                    "torque_feedforward_enabled": enabled
                }
            })
        else:
            return jsonify({
                "code": 500,
                "msg": "设置失败",
                "data": None
            }), 500
            
    except Exception as e:
        error_msg = f"设置力矩前馈失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

# 8. 系统配置接口
@bp.route('/config/coordinate-system', methods=['POST'])
def set_coordinate_system():
    """设置坐标系"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'system' not in data:
            return jsonify({
                "code": 400, 
                "msg": "缺少坐标系参数",
                "data": None
            }), 400
        
        system = data['system']
        robot_config.set_coordinate_system(system)
        
        # 更新运动状态中的坐标系
        from motion_control import motion_status
        motion_status.coordinate_system = system
        
        return jsonify({
            "code": 200,
            "msg": f"坐标系已设置为: {robot_config.coordinate_systems[system]}",
            "data": {
                "current_system": system,
                "system_name": robot_config.coordinate_systems[system]
            }
        })
        
    except Exception as e:
        error_msg = f"设置坐标系失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/config/dynamics', methods=['POST'])
def set_dynamics_params():
    """设置动力学参数"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({
                "code": 400, 
                "msg": "请求体必须为JSON格式",
                "data": None
            }), 400
        
        axis = data.get('axis')
        error = data.get('error')
        sensitivity = data.get('sensitivity')
        
        if not all([axis, error is not None, sensitivity is not None]):
            return jsonify({
                "code": 400, 
                "msg": "缺少必要参数: axis, error, sensitivity",
                "data": None
            }), 400
        
        robot_config.set_dynamics_params(axis, error, sensitivity)
        
        return jsonify({
            "code": 200,
            "msg": "动力学参数设置成功",
            "data": {
                "axis": axis,
                "error": error,
                "sensitivity": sensitivity
            }
        })
        
    except Exception as e:
        error_msg = f"设置动力学参数失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/config/current', methods=['GET'])
def get_current_config():
    """获取当前配置"""
    try:
        return jsonify({
            "code": 200,
            "msg": "配置获取成功",
            "data": {
                "dynamics_params": robot_config.dynamics_params,
                "coordinate_systems": robot_config.coordinate_systems,
                "current_coordinate_system": robot_config.current_coordinate_system,
                "collision_detection": robot_config.collision_detection,
                "torque_feedforward": robot_config.torque_feedforward,
                "safety_limits": robot_config.safety_limits
            }
        })
        
    except Exception as e:
        error_msg = f"获取配置失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

# 9. 系统集成接口
@bp.route('/system/status', methods=['GET'])
def get_system_status():
    """获取系统集成状态"""
    try:
        status = system_integration.get_system_status()
        
        return jsonify({
            "code": 200,
            "msg": "系统状态查询成功",
            "data": status
        })
        
    except Exception as e:
        error_msg = f"系统状态查询失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/system/ethernet/connect', methods=['POST'])
def connect_ethernet():
    """连接以太网"""
    try:
        success, message = system_integration.connect_ethernet()
        
        if success:
            return jsonify({
                "code": 200,
                "msg": message,
                "data": None
            })
        else:
            return jsonify({
                "code": 500,
                "msg": message,
                "data": None
            }), 500
            
    except Exception as e:
        error_msg = f"以太网连接失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

@bp.route('/system/fieldbus/connect', methods=['POST'])
def connect_fieldbus():
    """连接现场总线"""
    try:
        success, message = system_integration.connect_fieldbus()
        
        if success:
            return jsonify({
                "code": 200,
                "msg": message,
                "data": None
            })
        else:
            return jsonify({
                "code": 500,
                "msg": message,
                "data": None
            }), 500
            
    except Exception as e:
        error_msg = f"现场总线连接失败: {str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "msg": error_msg,
            "data": None
        }), 500

print("routes.py loaded")


@bp.route('/health', methods=['GET'])
def health_check():
    """Basic health endpoint reporting uptime, pybullet availability and store status."""
    try:
        uptime = time.time() - _app_start_time
        # store check
        store_ok = False
        if 'store' in globals() and store is not None:
            try:
                # try a read operation
                _ = store.list_items('drugs')
                store_ok = True
            except Exception:
                store_ok = False

        pyb_available = False
        try:
            pyb_available = bool(is_pybullet_available())
        except Exception:
            pyb_available = False

        return jsonify({
            "code": 200,
            "msg": "ok",
            "data": {
                "uptime": int(uptime),
                "pybullet_available": pyb_available,
                "store_ok": store_ok
            }
        })
    except Exception as e:
        return jsonify({"code": 500, "msg": f"health check failed: {e}", "data": None}), 500


# -------------------------- V2 Blueprint（新增，高级运镜） --------------------------
bp_v2 = Blueprint('api_v2', __name__, url_prefix='/api/v2')

# 简单的 API key 验证器和速率限制（进程内）
_last_cmd_time = {}  # ip -> timestamp
_min_cmd_interval = 0.05  # 最小间隔秒（防止高频指令）

def _get_client_ip():
    # 兼容直接请求和代理模式（不处理 X-Forwarded-For 多值）
    ip = request.headers.get('X-Real-IP') or request.headers.get('X-Forwarded-For') or request.remote_addr
    return ip

def require_api_key(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        # emergency stop intentionally not decorated when used (safety path)
        api_key = None
        auth = request.headers.get('Authorization')
        if auth and auth.lower().startswith('bearer '):
            api_key = auth.split(None, 1)[1].strip()
        if not api_key:
            api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

        try:
            if not robot_config.validate_api_key(api_key):
                return jsonify({"code": 401, "msg": "Unauthorized: invalid API key", "data": None}), 401
        except Exception:
            return jsonify({"code": 500, "msg": "Server error during auth", "data": None}), 500

        # 基本速率限制（按 IP）
        ip = _get_client_ip()
        now = time.time()
        last = _last_cmd_time.get(ip)
        if last and (now - last) < _min_cmd_interval:
            return jsonify({"code": 429, "msg": "Too Many Requests", "data": None}), 429
        _last_cmd_time[ip] = now

        # expose api_key in flask.g for handlers if needed
        g.api_key = api_key
        return fn(*args, **kwargs)
    return wrapper


# -------------------------- 状态推送优化（缓存 + 后台更新器） --------------------------
# 全局最近状态缓存，由后台线程定期更新，SSE 读取缓存以确保低延迟和稳定性
_state_lock = threading.RLock()
_latest_state = None
_state_updater_thread = None
_state_updater_running = False
_state_update_interval = 0.05  # 默认 50ms 采样频率，可在运行时调整

def _start_state_updater():
    global _state_updater_thread, _state_updater_running
    with _state_lock:
        if _state_updater_thread and _state_updater_thread.is_alive():
            return
        _state_updater_running = True

    def _updater():
        global _latest_state, _state_updater_running
        try:
            while _state_updater_running:
                try:
                    st = get_current_status()
                    snap = {
                        'timestamp': time.time(),
                        'current_pos': st.get('current_pos', [0.0, 0.0, 0.0]),
                        'current_angle': st.get('current_angle', 0.0),
                        'status': st.get('status'),
                        'error_message': st.get('error_message')
                    }
                    with _state_lock:
                        _latest_state = snap
                except Exception:
                    logger.exception('状态更新器获取状态失败')
                time.sleep(_state_update_interval)
        finally:
            with _state_lock:
                _state_updater_running = False

    _state_updater_thread = threading.Thread(target=_updater, daemon=True)
    _state_updater_thread.start()

def _stop_state_updater():
    global _state_updater_running
    with _state_lock:
        _state_updater_running = False



@bp_v2.route('/test', methods=['GET'])
def test_v2():
    return jsonify({
        "code": 200,
        "msg": "API路由测试成功（V2）",
        "data": {
            "service": "运镜控制API",
            "version": "2.0",
            "support_features": ["多段拼接", "预设模式", "高并发", "动力学辨识", "力矩前馈"],
            "max_concurrent_tasks": 3
        }
    })


def _multi_segment_runner(task_id, waypoints, interpolation_type, duration):
    """在后台逐段执行平移（相对位移），尽量使用 motion_control.translate_object。"""
    try:
        if not waypoints:
            return
        seg_count = max(1, len(waypoints))
        seg_dur = max(0.5, float(duration) / seg_count)
        for wp in waypoints:
            # 检查取消标志
            if task_manager.active_tasks.get(task_id, {}).get('cancel'):
                logger.warning(f"任务{task_id}被取消，中止多段运镜")
                return

            # 读取当前位姿并计算偏移到目标点
            status = get_current_status()
            cur = status.get('current_pos', [0, 0, 0])
            try:
                dx = float(wp[0]) - float(cur[0])
                dy = float(wp[1]) - float(cur[1])
                dz = float(wp[2]) - float(cur[2])
            except Exception:
                logger.warning(f"路径点格式错误，跳过: {wp}")
                continue

            # 如果 motion control 不可用，使用 sleep 模拟
            if motion_control_available():
                try:
                    translate_object(None, dx, dy, dz, seg_dur)
                except Exception:
                    logger.exception("调用 translate_object 失败，降级为等待模拟")
                    time.sleep(seg_dur)
            else:
                time.sleep(seg_dur)

    except Exception:
        logger.exception(f"多段运镜任务{task_id}执行异常")


@bp_v2.route('/trajectory/multi-segment', methods=['POST'])
@require_api_key
def multi_segment_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'waypoints' not in data:
            return jsonify({"code": 400, "msg": "缺少 waypoints 参数", "data": None}), 400

        waypoints = data['waypoints']
        interpolation_type = data.get('interpolation_type', 'linear')
        duration = float(data.get('duration', 5))

        # 简单校验
        if len(waypoints) < 2:
            return jsonify({"code": 400, "msg": "路径点数量至少为2", "data": None}), 400

        # 工作空间边界预校验：若有任一路径点超出边界，拒绝整个任务
        for i, wp in enumerate(waypoints):
            try:
                if not safety_monitor.is_inside_workspace(wp):
                    return jsonify({"code": 400, "msg": f"第{i+1}个路径点{wp}超出工作空间", "data": None}), 400
            except Exception:
                return jsonify({"code": 400, "msg": f"第{i+1}个路径点格式错误或边界检查失败: {wp}", "data": None}), 400

        if not motion_control_available():
            return jsonify({"code": 503, "msg": "运动控制模块不可用", "data": None}), 503

        task_id = task_manager.create_task(_multi_segment_runner, waypoints, interpolation_type, duration)
        return jsonify({
            "code": 200,
            "msg": "多段运镜指令已接收（后台执行）",
            "data": {
                "task_id": task_id,
                "task_status_url": f"/api/v2/task/status?task_id={task_id}"
            }
        })
    except Exception as e:
        logger.exception("多段运镜接口失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/task/status', methods=['GET'])
def task_status_v2():
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({"code": 400, "msg": "缺少 task_id 参数", "data": None}), 400
    status = task_manager.get_task_status(task_id)
    return jsonify({"code": 200, "msg": "任务状态查询成功", "data": {"task_id": task_id, "status": status}})


@bp_v2.route('/task/cancel', methods=['POST'])
def task_cancel_v2():
    data = request.get_json(force=True, silent=True)
    if not data or 'task_id' not in data:
        return jsonify({"code": 400, "msg": "缺少 task_id 参数", "data": None}), 400
    task_id = data['task_id']
    # 限制只有授权用户可取消任务
    if not robot_config.validate_api_key(request.headers.get('X-API-Key') or (request.headers.get('Authorization') and request.headers.get('Authorization').split(None,1)[1])):
        return jsonify({"code": 401, "msg": "Unauthorized: invalid API key", "data": None}), 401
    success, msg = task_manager.cancel_task(task_id)
    if success:
        return jsonify({"code": 200, "msg": msg, "data": {"task_id": task_id}})
    else:
        return jsonify({"code": 400, "msg": msg, "data": None}), 400


# -------------------------- V2 预设运镜 + 力矩前馈/坐标/关节控制等 --------------------------
@bp_v2.route('/trajectory/preset/circle', methods=['POST'])
@require_api_key
def preset_circle_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'center_pos' not in data:
            return jsonify({"code": 400, "msg": "缺少 center_pos 参数", "data": None}), 400

        center_pos = data['center_pos']
        radius = float(data.get('radius', 0.4))
        duration = float(data.get('duration', 6.0))
        clockwise = bool(data.get('clockwise', True))

        if len(center_pos) != 3:
            return jsonify({"code": 400, "msg": "中心点格式错误，需为[x,y,z]列表", "data": None}), 400
        if not safety_monitor.is_inside_workspace(center_pos):
            return jsonify({"code": 400, "msg": f"中心点{center_pos}超出工作空间", "data": None}), 400

        if radius < 0.1:
            radius = 0.1
        elif radius > 0.8:
            radius = 0.8
        if duration < 2:
            duration = 2
        elif duration > 15:
            duration = 15

        if not motion_control_available():
            return jsonify({"code": 503, "msg": "运动控制模块不可用", "data": None}), 503

        # 优先调用 motion_control 中的高级函数，否则降级为在后台按路径点模拟
        preset_fn = getattr(mc, 'preset_circle_motion', None)
        if callable(preset_fn):
            task_id = task_manager.create_task(lambda tid, *a, **kw: preset_fn(None, center_pos, radius, duration, clockwise))
        else:
            # 降级：把圆周拆成若干点并复用多段运镜执行器
            def circle_runner(tid):
                import math
                pts = []
                for i in range(12):
                    theta = (2 * math.pi * i) / 12.0
                    x = center_pos[0] + radius * math.cos(theta)
                    y = center_pos[1] + radius * math.sin(theta)
                    z = center_pos[2]
                    pts.append([x, y, z])
                _multi_segment_runner(tid, pts, 'bezier', duration)

            task_id = task_manager.create_task(circle_runner)

        return jsonify({"code": 200, "msg": "环绕运镜指令已接收", "data": {"task_id": task_id}})
    except Exception as e:
        logger.exception("环绕运镜接口失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/trajectory/preset/push-pull', methods=['POST'])
@require_api_key
def preset_push_pull_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'direction' not in data:
            return jsonify({"code": 400, "msg": "缺少 direction 参数", "data": None}), 400

        direction = data['direction']
        distance = float(data.get('distance', 0.6))
        duration = float(data.get('duration', 5.0))

        if direction not in ['x', 'y', 'z']:
            return jsonify({"code": 400, "msg": "direction 必须为 x/y/z", "data": None}), 400
        if distance <= 0:
            return jsonify({"code": 400, "msg": "distance 必须大于0", "data": None}), 400

        if not motion_control_available():
            return jsonify({"code": 503, "msg": "运动控制模块不可用", "data": None}), 503

        preset_fn = getattr(mc, 'preset_push_pull_motion', None)
        if callable(preset_fn):
            task_id = task_manager.create_task(lambda tid, *a, **kw: preset_fn(None, direction, distance, duration))
        else:
            # 降级模拟：计算两个端点并调用多段运镜
            def pushpull_runner(tid):
                status = get_current_status()
                cur = status.get('current_pos', [0, 0, 0])
                idx = {'x': 0, 'y': 1, 'z': 2}[direction]
                pt1 = cur.copy()
                pt2 = cur.copy()
                pt1[idx] = cur[idx] - distance/2
                pt2[idx] = cur[idx] + distance/2
                _multi_segment_runner(tid, [pt1, pt2, pt1], 'linear', duration)

            task_id = task_manager.create_task(pushpull_runner)

        return jsonify({"code": 200, "msg": "推拉运镜指令已接收", "data": {"task_id": task_id}})
    except Exception as e:
        logger.exception("推拉运镜接口失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/torque/feedforward/enable', methods=['POST'])
@require_api_key
def enable_torque_feedforward_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'enabled' not in data:
            return jsonify({"code": 400, "msg": "缺少 enabled 参数", "data": None}), 400
        enabled = bool(data['enabled'])
        success = mc_set_torque_feedforward(enabled)
        if success:
            return jsonify({"code": 200, "msg": f"力矩前馈已{'启用' if enabled else '禁用'}", "data": {"enabled": enabled}})
        else:
            return jsonify({"code": 500, "msg": "设置失败", "data": None}), 500
    except Exception as e:
        logger.exception("力矩前馈 enable 失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/torque/feedforward/update-params', methods=['POST'])
@require_api_key
def update_feedforward_params_v2():
    try:
        data = request.get_json(force=True, silent=True)
        mass = data.get('mass') if data else None
        inertia = data.get('inertia') if data else None
        friction = data.get('friction') if data else None
        if not mass or not inertia or not friction or len(mass) != 6 or len(inertia) != 6 or len(friction) != 6:
            return jsonify({"code": 400, "msg": "参数错误：需要6个关节的 mass/inertia/friction 列表", "data": None}), 400

        tf = getattr(mc, 'torque_feedforward', None)
        if tf and hasattr(tf, 'update_dynamics_params'):
            tf.update_dynamics_params({"mass": mass, "inertia": inertia, "friction": friction})
        return jsonify({"code": 200, "msg": "动力学参数更新成功", "data": {"mass": mass, "inertia": inertia, "friction": friction}})
    except Exception as e:
        logger.exception("更新力矩前馈参数失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/collision/sensitivity', methods=['POST'])
@require_api_key
def set_collision_sensitivity_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求体不能为空", "data": None}), 400
        axis = int(data.get('axis')) if 'axis' in data else None
        sensitivity = int(data.get('sensitivity')) if 'sensitivity' in data else None
        if not axis or sensitivity is None:
            return jsonify({"code": 400, "msg": "缺少 axis 或 sensitivity 参数", "data": None}), 400

        tf = getattr(mc, 'torque_feedforward', None)
        if tf and hasattr(tf, 'set_collision_sensitivity'):
            ok = tf.set_collision_sensitivity(axis, sensitivity)
            if ok:
                return jsonify({"code": 200, "msg": "碰撞灵敏度设置成功", "data": {"axis": axis, "sensitivity": sensitivity}})
        return jsonify({"code": 400, "msg": "设置不被支持或参数不合法", "data": None}), 400
    except Exception as e:
        logger.exception("设置碰撞灵敏度失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/coordinate/switch', methods=['POST'])
@require_api_key
def switch_coordinate_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'coordinate_type' not in data:
            return jsonify({"code": 400, "msg": "缺少 coordinate_type 参数", "data": None}), 400
        coord = data['coordinate_type']
        supported = ['joint', 'cartesian', 'tool', 'user']
        if coord not in supported:
            return jsonify({"code": 400, "msg": f"不支持的坐标系: {coord}", "data": None}), 400

        robot_config.set_coordinate_system(coord)
        # 更新 motion_status（若存在）
        try:
            from motion_control import motion_status
            motion_status.coordinate_system = coord
        except Exception:
            logger.debug("更新 motion_status 失败或不存在")

        return jsonify({"code": 200, "msg": "坐标系切换成功", "data": {"current_coordinate": robot_config.current_coordinate_system}})
    except Exception as e:
        logger.exception("切换坐标系失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/joint/move-single', methods=['POST'])
@require_api_key
def move_single_joint_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求体不能为空", "data": None}), 400
        joint_id = int(data.get('joint_id') or data.get('joint')) if ('joint_id' in data or 'joint' in data) else None
        target_angle = float(data.get('target_angle') or data.get('angle')) if ('target_angle' in data or 'angle' in data) else None
        speed = float(data.get('speed', 50.0))
        if not joint_id or target_angle is None:
            return jsonify({"code": 400, "msg": "缺少 joint_id 或 target_angle", "data": None}), 400
        if not (1 <= joint_id <= 6):
            return jsonify({"code": 400, "msg": "joint_id 必须1-6", "data": None}), 400

        move_fn = getattr(mc, 'move_joint', None)
        if callable(move_fn):
            task_id = task_manager.create_task(lambda tid, *a, **kw: move_fn(joint_id, target_angle, speed))
        else:
            # 降级：直接 sleep 模拟运动
            def sim(tid):
                time.sleep(max(0.5, abs(target_angle) / 90.0 * 1.0))
            task_id = task_manager.create_task(sim)

        return jsonify({"code": 200, "msg": "关节运动指令已接收", "data": {"task_id": task_id}})
    except Exception as e:
        logger.exception("单关节运动失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/joint/move-all', methods=['POST'])
@require_api_key
def move_all_joints_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data or 'target_angles' not in data:
            return jsonify({"code": 400, "msg": "缺少 target_angles 参数", "data": None}), 400
        target_angles = data['target_angles']
        speed = float(data.get('speed', 50.0))
        if len(target_angles) != 6:
            return jsonify({"code": 400, "msg": "需要6个目标角度", "data": None}), 400

        move_all_fn = getattr(mc, 'move_joints', None)
        if callable(move_all_fn):
            task_id = task_manager.create_task(lambda tid, *a, **kw: move_all_fn(target_angles, speed))
        else:
            def sim_all(tid):
                time.sleep(max(0.5, max(abs(a) for a in target_angles) / 90.0 * 1.0))
            task_id = task_manager.create_task(sim_all)

        return jsonify({"code": 200, "msg": "所有关节同步运动指令已接收", "data": {"task_id": task_id}})
    except Exception as e:
        logger.exception("同步关节运动失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/final/recommend', methods=['GET'])
@require_api_key
def final_recommend_v2():
    return jsonify({
        "code": 200,
        "msg": "决赛推荐配置查询成功",
        "data": {
            "recommend_endpoints": [
                {"name": "环绕运镜", "url": "/api/v2/trajectory/preset/circle", "params": {"center_pos": [0.5,0.5,0.3], "radius": 0.4, "duration": 6, "clockwise": True}},
                {"name": "动力学辨识", "url": "/api/v2/dynamics/identification/start", "params": {}},
                {"name": "推拉运镜", "url": "/api/v2/trajectory/preset/push-pull", "params": {"direction": "x", "distance": 0.6, "duration": 5}}
            ],
            "performance_tips": [
                "最多支持3个并发任务，避免同时发起更多",
                "辨识过程较长，展示可仅演示启动流程",
                "异常时优先调用 /api/v2/task/cancel 再重置错误",
            ]
        }
    })


@bp_v2.route('/state', methods=['GET'])
def state_snapshot_v2():
    """实时状态快照（位置、角度、运行状态、错误信息）。"""
    try:
        status = get_current_status()
        return jsonify({
            "code": 200,
            "msg": "状态快照",
            "data": {
                "position": status.get('current_pos'),
                "angle": status.get('current_angle'),
                "status": status.get('status'),
                "error_message": status.get('error_message')
            }
        })
    except Exception as e:
        logger.exception("获取状态快照失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/stream/state', methods=['GET'])
def stream_state_v2():
    """Server-Sent Events 推送：position/velocity/fault_code。支持查询参数 `interval`（秒，默认0.5）和 `max`（最大消息数，0=无限）。"""
    try:
        interval = float(request.args.get('interval', 0.5))
    except Exception:
        interval = 0.5
    try:
        max_events = int(request.args.get('max', 0))
    except Exception:
        max_events = 0

    # 确保后台状态更新器在有客户端订阅时运行
    _start_state_updater()

    def event_stream():
        prev = None
        count = 0
        while True:
            try:
                # 读取最近缓存的状态，若不存在则回退到直接采样
                with _state_lock:
                    cached = dict(_latest_state) if _latest_state else None

                if cached:
                    pos = cached.get('current_pos', [0.0, 0.0, 0.0])
                    angle = cached.get('current_angle', 0.0)
                    status_str = cached.get('status')
                    err_msg = (cached.get('error_message') or '').lower()
                    now = cached.get('timestamp', time.time())
                else:
                    st = get_current_status()
                    pos = st.get('current_pos', [0.0, 0.0, 0.0])
                    angle = st.get('current_angle', 0.0)
                    status_str = st.get('status')
                    err_msg = (st.get('error_message') or '').lower()
                    now = time.time()

                # 速度由两次采样差分估算（使用时间戳更可靠）
                if prev and 'time' in prev and prev.get('pos'):
                    dt = now - prev['time']
                    if dt > 0:
                        vel = [round((pos[i] - prev['pos'][i]) / dt, 6) for i in range(3)]
                    else:
                        vel = [0.0, 0.0, 0.0]
                else:
                    vel = [0.0, 0.0, 0.0]

                # 故障码映射：0=正常，1=collision，2=error/stop，3=其他
                fault_code = 0
                if 'collision' in err_msg:
                    fault_code = 1
                elif status_str == 'error':
                    fault_code = 2

                payload = {
                    "timestamp": int(now),
                    "position": pos,
                    "angle": angle,
                    "velocity": vel,
                    "fault_code": fault_code,
                    "status": status_str,
                    "error_message": (cached.get('error_message') if cached else (st.get('error_message') if 'st' in locals() else None))
                }

                prev = {"pos": pos, "time": now}
                # SSE data
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                count += 1
                if max_events > 0 and count >= max_events:
                    break
                # 使用短睡眠以降低延迟；`interval` 是客户端期望的最小间隔
                time.sleep(min(interval, _state_update_interval))
            except GeneratorExit:
                break
            except Exception:
                logger.exception('SSE 推送发生异常')
                break

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


# -------------------------- V2 动力学辨识辅助接口（与 SDK Demo 对齐） --------------------------
@bp_v2.route('/dynamics/identification/set-params', methods=['POST'])
def set_identification_params_v2():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求体不能为空", "data": None}), 400
        traj_range = int(data.get('trajectory_range', 10))
        traj_speed = int(data.get('trajectory_speed', 10))

        if hasattr(dynamics_identification, 'set_parameters'):
            ok = dynamics_identification.set_parameters(traj_range, traj_speed)
            if ok:
                return jsonify({"code": 200, "msg": "辨识参数设置成功", "data": {"trajectory_range": traj_range, "trajectory_speed": traj_speed}})
        return jsonify({"code": 400, "msg": "参数设置失败或不被支持", "data": None}), 400
    except Exception as e:
        logger.exception("设置辨识参数失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/dynamics/identification/confirm-zero', methods=['POST'])
def confirm_zero_position_v2():
    try:
        if hasattr(dynamics_identification, 'confirm_zero_position'):
            ok = dynamics_identification.confirm_zero_position()
            if ok:
                return jsonify({"code": 200, "msg": "零点位置已确认", "data": {"zero_position_confirmed": True}})
        return jsonify({"code": 400, "msg": "确认零点失败或不被支持", "data": None}), 400
    except Exception as e:
        logger.exception("确认零点失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/dynamics/identification/test-safety', methods=['POST'])
def test_identification_safety_v2():
    try:
        if hasattr(dynamics_identification, 'test_trajectory_safety'):
            ok = dynamics_identification.test_trajectory_safety()
            if ok:
                return jsonify({"code": 200, "msg": "轨迹安全测试通过", "data": {"safety_check_passed": True}})
            else:
                return jsonify({"code": 400, "msg": "轨迹安全测试未通过", "data": None}), 400
        return jsonify({"code": 400, "msg": "不支持的操作", "data": None}), 400
    except Exception as e:
        logger.exception("轨迹安全测试失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/dynamics/identification/start', methods=['POST'])
def start_identification_v2():
    try:
        # 复用已有 dynamics_identification.start_identification
        if hasattr(dynamics_identification, 'start_identification'):
            success, message = dynamics_identification.start_identification()
            if success:
                return jsonify({"code": 200, "msg": message, "data": {"identification_id": id(dynamics_identification)}})
            else:
                return jsonify({"code": 400, "msg": message, "data": None}), 400
        return jsonify({"code": 400, "msg": "不支持的操作", "data": None}), 400
    except Exception as e:
        logger.exception("启动辨识失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/dynamics/identification/stop', methods=['POST'])
def stop_identification_v2():
    try:
        if hasattr(dynamics_identification, 'stop_identification'):
            success, message = dynamics_identification.stop_identification()
            if success:
                return jsonify({"code": 200, "msg": message, "data": None})
            else:
                return jsonify({"code": 400, "msg": message, "data": None}), 400
        return jsonify({"code": 400, "msg": "不支持的操作", "data": None}), 400
    except Exception as e:
        logger.exception("停止辨识失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@bp_v2.route('/dynamics/identification/status', methods=['GET'])
def get_identification_status_v2():
    try:
        if hasattr(dynamics_identification, 'is_identifying'):
            return jsonify({
                "code": 200,
                "msg": "辨识状态查询成功",
                "data": {
                    "is_identifying": dynamics_identification.is_identifying,
                    "progress": getattr(dynamics_identification, 'progress', 0),
                    "current_trajectory_range": getattr(dynamics_identification, 'current_trajectory_range', None),
                    "current_trajectory_speed": getattr(dynamics_identification, 'current_trajectory_speed', None),
                    "results": getattr(dynamics_identification, 'identification_results', None)
                }
            })
        return jsonify({"code": 400, "msg": "不支持的操作", "data": None}), 400
    except Exception as e:
        logger.exception("查询辨识状态失败")
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500




# --- CRUD 接口: drugs, pipelines, identification_runs, metrics ---


@bp.route('/drugs', methods=['GET'])
def list_drugs():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    items = store.list_items('drugs')
    return jsonify({"code":200, "msg":"ok", "data": items})


@bp.route('/drugs', methods=['POST'])
def create_drug():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
    item = store.create_item('drugs', data)
    return jsonify({"code":201, "msg":"创建成功","data":item}),201


@bp.route('/drugs/<int:item_id>', methods=['GET'])
def get_drug(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    item = store.get_item('drugs', item_id)
    if not item:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"ok","data":item})


@bp.route('/drugs/<int:item_id>', methods=['PUT'])
def update_drug(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
    item = store.update_item('drugs', item_id, data)
    if not item:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"更新成功","data":item})


@bp.route('/drugs/<int:item_id>', methods=['DELETE'])
def delete_drug(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    ok = store.delete_item('drugs', item_id)
    if not ok:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"删除成功","data":None})


@bp.route('/pipelines', methods=['GET'])
def list_pipelines():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    items = store.list_items('pipelines')
    return jsonify({"code":200, "msg":"ok", "data": items})


@bp.route('/pipelines', methods=['POST'])
def create_pipeline():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
    item = store.create_item('pipelines', data)
    return jsonify({"code":201, "msg":"创建成功","data":item}),201


@bp.route('/identification_runs', methods=['GET'])
def list_identification_runs():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    items = store.list_items('identification_runs')
    return jsonify({"code":200, "msg":"ok", "data": items})


@bp.route('/identification_runs/<int:item_id>', methods=['GET'])
def get_identification_run(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    item = store.get_item('identification_runs', item_id)
    if not item:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"ok","data":item})


@bp.route('/metrics', methods=['GET'])
def list_metrics():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    items = store.list_items('metrics')
    return jsonify({"code":200, "msg":"ok", "data": items})


@bp.route('/metrics', methods=['POST'])
def create_metric():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
    item = store.create_item('metrics', data)
    return jsonify({"code":201, "msg":"创建成功","data":item}),201


# --- 手填动力学参数（manual_dynamics） CRUD ---
@bp.route('/manual_dynamics', methods=['GET'])
def list_manual_dynamics():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    items = store.list_items('manual_dynamics')
    return jsonify({"code":200, "msg":"ok", "data": items})


@bp.route('/manual_dynamics', methods=['POST'])
def create_manual_dynamics():
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
    # 期望字段例如: axis, error, sensitivity, source='manual'
    data.setdefault('source', 'manual')
    item = store.create_item('manual_dynamics', data)
    return jsonify({"code":201, "msg":"创建成功","data":item}),201


@bp.route('/manual_dynamics/<int:item_id>', methods=['GET'])
def get_manual_dynamics(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    item = store.get_item('manual_dynamics', item_id)
    if not item:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"ok","data":item})


@bp.route('/manual_dynamics/<int:item_id>', methods=['PUT'])
def update_manual_dynamics(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
    item = store.update_item('manual_dynamics', item_id, data)
    if not item:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"更新成功","data":item})


@bp.route('/manual_dynamics/<int:item_id>', methods=['DELETE'])
def delete_manual_dynamics(item_id):
    if not store:
        return jsonify({"code":500, "msg":"数据存储不可用","data":None}),500
    ok = store.delete_item('manual_dynamics', item_id)
    if not ok:
        return jsonify({"code":404, "msg":"未找到","data":None}),404
    return jsonify({"code":200, "msg":"删除成功","data":None})


# --- 碰撞参数配置接口 ---
@bp.route('/config/collision', methods=['GET'])
def get_collision_config():
    try:
        from robot_config import robot_config
        return jsonify({"code":200, "msg":"ok", "data": robot_config.get_collision_params()})
    except Exception as e:
        return jsonify({"code":500, "msg": str(e), "data":None}),500


@bp.route('/config/collision', methods=['POST'])
def set_collision_config():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code":400, "msg":"请求体必须为JSON","data":None}),400
        from robot_config import robot_config
        robot_config.set_collision_params(
            sensitivity=data.get('sensitivity'),
            response_time=data.get('response_time'),
            allowed_error_time=data.get('allowed_error_time')
        )
        return jsonify({"code":200, "msg":"设置成功","data": robot_config.get_collision_params()})
    except Exception as e:
        return jsonify({"code":500, "msg": str(e), "data":None}),500