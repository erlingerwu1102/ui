import requests
import time
import json
import threading

BASE_URL = "http://localhost:8000/api/v1"

def test_dynamics_identification():
    """测试动力学参数辨识"""
    print("\n=== 测试动力学参数辨识 ===")
    
    # 1. 开始辨识
    print("1. 开始动力学参数辨识...")
    data = {
        "trajectory_range": 30,
        "trajectory_speed": 50
    }
    response = requests.post(f"{BASE_URL}/dynamics/identification", json=data, timeout=10)
    print(f"开始辨识 - 状态码: {response.status_code}")
    if response.status_code == 200:
        print("开始辨识成功:", response.json())
    else:
        print("开始辨识失败:", response.text)
        return False
    
    # 2. 监控辨识进度
    print("2. 监控辨识进度...")
    for i in range(10):
        time.sleep(3)
        response = requests.get(f"{BASE_URL}/dynamics/identification/status", timeout=5)
        if response.status_code == 200:
            status_data = response.json()['data']
            print(f"进度: {status_data['progress']}% - 正在辨识: {status_data['is_identifying']}")
            if not status_data['is_identifying']:
                print("辨识完成!")
                print("辨识结果:", status_data['results'])
                break
        else:
            print("获取状态失败:", response.text)
    
    return True

def test_safety_features():
    """测试安全功能"""
    print("\n=== 测试安全功能 ===")
    
    # 1. 启用碰撞检测
    print("1. 启用碰撞检测...")
    response = requests.post(f"{BASE_URL}/safety/collision-detection", 
                           json={"enabled": True}, timeout=5)
    print(f"启用碰撞检测 - 状态码: {response.status_code}")
    
    # 2. 启动力矩前馈
    print("2. 启动力矩前馈...")
    response = requests.post(f"{BASE_URL}/safety/torque-feedforward", 
                           json={"enabled": True}, timeout=5)
    print(f"启动力矩前馈 - 状态码: {response.status_code}")
    
    # 3. 获取安全状态
    print("3. 获取安全状态...")
    response = requests.get(f"{BASE_URL}/safety/status", timeout=5)
    if response.status_code == 200:
        print("安全状态:", response.json()['data'])
    
    return True

def test_coordinate_systems():
    """测试坐标系功能"""
    print("\n=== 测试坐标系功能 ===")
    
    coordinate_systems = ['joint', 'cartesian', 'tool', 'user']
    
    for system in coordinate_systems:
        print(f"设置坐标系: {system}")
        response = requests.post(f"{BASE_URL}/config/coordinate-system", 
                               json={"system": system}, timeout=5)
        if response.status_code == 200:
            print(f"设置成功: {response.json()['data']['system_name']}")
            
            # 验证状态中的坐标系
            status_response = requests.get(f"{BASE_URL}/status", timeout=5)
            if status_response.status_code == 200:
                current_system = status_response.json()['data']['coordinate_system']
                print(f"当前坐标系: {current_system}")
                time.sleep(1)
        else:
            print(f"设置失败: {response.text}")
    
    return True

def test_dynamics_parameters():
    """测试动力学参数设置"""
    print("\n=== 测试动力学参数设置 ===")
    
    # 设置各轴的动力学参数
    for axis in range(1, 7):
        data = {
            "axis": f"axis{axis}",
            "error": 0.1 * axis,
            "sensitivity": 50 + axis * 5
        }
        response = requests.post(f"{BASE_URL}/config/dynamics", json=data, timeout=5)
        if response.status_code == 200:
            print(f"轴{axis}参数设置成功")
        else:
            print(f"轴{axis}参数设置失败: {response.text}")
    
    # 获取当前配置
    response = requests.get(f"{BASE_URL}/config/current", timeout=5)
    if response.status_code == 200:
        print("当前配置:", json.dumps(response.json()['data']['dynamics_params'], indent=2))
    
    return True

def test_system_integration():
    """测试系统集成功能"""
    print("\n=== 测试系统集成功能 ===")
    
    # 1. 连接以太网
    print("1. 连接以太网...")
    response = requests.post(f"{BASE_URL}/system/ethernet/connect", timeout=5)
    print(f"以太网连接 - 状态码: {response.status_code}")
    
    # 2. 连接现场总线
    print("2. 连接现场总线...")
    response = requests.post(f"{BASE_URL}/system/fieldbus/connect", timeout=5)
    print(f"现场总线连接 - 状态码: {response.status_code}")
    
    # 3. 获取系统状态
    print("3. 获取系统状态...")
    response = requests.get(f"{BASE_URL}/system/status", timeout=5)
    if response.status_code == 200:
        system_status = response.json()['data']
        print("系统状态:")
        print(f"  以太网连接: {system_status['ethernet_connected']}")
        print(f"  现场总线连接: {system_status['fieldbus_connected']}")
        print(f"  远程管理: {system_status['remote_management']}")
    
    return True

def test_collision_recovery():
    """测试碰撞恢复功能"""
    print("\n=== 测试碰撞恢复功能 ===")
    
    # 模拟碰撞情况
    print("1. 模拟碰撞情况...")
    # 注意：在实际系统中，这里会触发真实的碰撞检测
    # 这里我们只是测试重置功能
    
    # 重置碰撞状态
    print("2. 重置碰撞状态...")
    response = requests.post(f"{BASE_URL}/safety/collision/reset", timeout=5)
    if response.status_code == 200:
        print("碰撞状态重置成功")
    
    # 测试在碰撞状态下执行运动（应该被阻止）
    print("3. 测试碰撞状态下的运动...")
    data = {"x_offset": 1, "y_offset": 0, "z_offset": 0}
    response = requests.post(f"{BASE_URL}/translate", json=data, timeout=5)
    print(f"碰撞状态下平移 - 状态码: {response.status_code}")
    
    return True

def test_enhanced_motion_with_safety():
    """测试带安全功能的运动控制"""
    print("\n=== 测试带安全功能的运动控制 ===")
    
    # 启用所有安全功能
    requests.post(f"{BASE_URL}/safety/collision-detection", json={"enabled": True})
    requests.post(f"{BASE_URL}/safety/torque-feedforward", json={"enabled": True})
    
    # 测试运动序列
    motions = [
        {"type": "translate", "data": {"x_offset": 0.5, "y_offset": 0, "z_offset": 0, "duration": 1}},
        {"type": "rotate", "data": {"angle_deg": 45, "duration": 1}},
        {"type": "translate", "data": {"x_offset": 0, "y_offset": 0.3, "z_offset": 0, "duration": 1}},
        {"type": "rotate", "data": {"angle_deg": -45, "duration": 1}},
    ]
    
    for i, motion in enumerate(motions, 1):
        print(f"执行运动 {i}/{len(motions)}: {motion['type']}")
        
        if motion['type'] == 'translate':
            response = requests.post(f"{BASE_URL}/translate", json=motion['data'], timeout=10)
        else:
            response = requests.post(f"{BASE_URL}/rotate", json=motion['data'], timeout=10)
        
        if response.status_code == 200:
            print(f"运动执行成功: {response.json()['msg']}")
        else:
            print(f"运动执行失败: {response.text}")
        
        # 检查状态
        status_response = requests.get(f"{BASE_URL}/status", timeout=5)
        if status_response.status_code == 200:
            status_data = status_response.json()['data']
            print(f"  当前位置: {status_data['current_pos']}")
            print(f"  当前角度: {status_data['current_angle']}")
            print(f"  安全状态: 碰撞检测={status_data['collision_detection_enabled']}, 力矩前馈={status_data['torque_feedforward_enabled']}")
        
        time.sleep(1)
    
    return True

def run_comprehensive_test():
    """运行综合测试"""
    print("🚀 开始高级功能综合测试")
    print("=" * 50)
    
    tests = [
        test_safety_features,
        test_coordinate_systems,
        test_dynamics_parameters,
        test_system_integration,
        test_collision_recovery,
        test_enhanced_motion_with_safety,
        # test_dynamics_identification  # 这个测试时间较长，可以单独运行
    ]
    
    all_passed = True
    for test_func in tests:
        try:
            success = test_func()
            if not success:
                all_passed = False
                print(f"❌ {test_func.__name__} 测试失败")
            else:
                print(f"✅ {test_func.__name__} 测试通过")
        except Exception as e:
            print(f"❌ {test_func.__name__} 测试异常: {e}")
            all_passed = False
        
        print("-" * 30)
        time.sleep(1)
    
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败，请检查日志")
    
    return all_passed

if __name__ == "__main__":
    run_comprehensive_test()