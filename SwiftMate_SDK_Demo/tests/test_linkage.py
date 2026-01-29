import requests
import time
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_connection():
    """测试基础连接"""
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        print(f"服务器连接测试: 状态码 {response.status_code}")
        return True
    except Exception as e:
        print(f"服务器连接失败: {e}")
        return False

def test_status():
    """测试状态查询"""
    try:
        response = requests.get(f"{BASE_URL}/status", timeout=5)
        print(f"状态查询 - 状态码: {response.status_code}")
        if response.status_code == 200:
            print("状态查询成功:", response.json())
            return True
        else:
            print(f"状态查询失败，响应内容: {response.text}")
            return False
    except Exception as e:
        print(f"状态查询异常: {e}")
        return False

def test_api_routes():
    """测试API路由是否正常注册"""
    try:
        response = requests.get(f"{BASE_URL}/test", timeout=5)
        print(f"API路由测试 - 状态码: {response.status_code}")
        if response.status_code == 200:
            print("API路由测试成功:", response.json())
            return True
        else:
            print(f"API路由测试失败: {response.text}")
            return False
    except Exception as e:
        print(f"API路由测试异常: {e}")
        return False

def test_translate(x, y, z, duration=1):
    """测试平移"""
    try:
        data = {
            "x_offset": x,
            "y_offset": y, 
            "z_offset": z,
            "duration": duration
        }
        response = requests.post(f"{BASE_URL}/translate", json=data, timeout=10)
        print(f"平移测试 - 状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"平移 ({x}, {y}, {z}):", response.json())
            return True
        else:
            print(f"平移测试失败: {response.text}")
            return False
    except Exception as e:
        print(f"平移测试异常: {e}")
        return False

def test_rotate(angle, duration=1):
    """测试旋转"""
    try:
        data = {
            "angle_deg": angle,
            "duration": duration
        }
        response = requests.post(f"{BASE_URL}/rotate", json=data, timeout=10)
        print(f"旋转测试 - 状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"旋转 {angle}度:", response.json())
            return True
        else:
            print(f"旋转测试失败: {response.text}")
            return False
    except Exception as e:
        print(f"旋转测试异常: {e}")
        return False

def test_parameter_validation():
    """测试参数验证"""
    print("\n参数验证测试:")
    
    # 测试缺少必填参数
    print("  测试缺少必填参数:")
    response = requests.post(f"{BASE_URL}/translate", json={'x_offset': 1}, timeout=5)
    print(f"    缺少y_offset,z_offset - 状态码: {response.status_code}")
    
    # 测试错误参数类型
    print("  测试错误参数类型:")
    response = requests.post(f"{BASE_URL}/translate", 
                           json={'x_offset': 'invalid', 'y_offset': 0, 'z_offset': 0}, 
                           timeout=5)
    print(f"    参数类型错误 - 状态码: {response.status_code}")
    
    # 测试负数时长
    print("  测试负数时长:")
    response = requests.post(f"{BASE_URL}/rotate", 
                           json={'angle_deg': 90, 'duration': -1}, 
                           timeout=5)
    print(f"    负数时长 - 状态码: {response.status_code}")
    
    return True

def test_integration():
    """测试API与SDK的完整集成"""
    print("\n开始完整集成测试:")
    
    # 测试顺序操作
    test_cases = [
        {"func": test_translate, "args": (0.5, 0, 0, 1)},
        {"func": test_rotate, "args": (45, 1)},
        {"func": test_translate, "args": (0, 0.3, 0, 1)},
        {"func": test_rotate, "args": (-45, 1)}
    ]
    
    all_success = True
    for i, case in enumerate(test_cases, 1):
        print(f"  步骤 {i}: {case['func'].__name__}")
        if not case['func'](*case['args']):
            print(f"  ▲ 步骤 {i} 执行失败")
            all_success = False
        time.sleep(1)
    
    return all_success

def run_diagnostic():
    """运行诊断测试"""
    print("== 开始API诊断测试 ==\n")

    # 1. 测试服务器连接
    print("1. 测试服务器连接:")
    if not test_connection():
        print("X 服务器连接失败，请检查Flask是否正常运行")
        return False

    # 2. 测试API路由
    print("\n2. 测试API路由:")
    if not test_api_routes():
        print("X API路由测试失败，请检查蓝图注册")
        return False

    # 3. 测试状态查询
    print("\n3. 测试状态查询:")
    if not test_status():
        print("▲ 状态查询失败，但继续测试其他功能")

    # 4. 测试参数验证
    print("\n4. 测试参数验证:")
    test_parameter_validation()

    # 5. 测试平移
    print("\n5. 测试平移功能:")
    if test_translate(0.5, 0, 0, 0.5):
        time.sleep(1)
    else:
        print("▲ 平移测试失败")

    # 6. 测试旋转
    print("\n6. 测试旋转功能:")
    if test_rotate(45, 0.5):
        time.sleep(1)
    else:
        print("▲ 旋转测试失败")

    # 7. 完整集成测试
    print("\n7. 完整集成测试:")
    integration_success = test_integration()
    
    if not integration_success:
        print("▲ 集成测试中有步骤失败")

    # 8. 最终状态查询
    print("\n8. 最终状态查询:")
    test_status()
    
    print("\n== 诊断测试完成 ===")
    return True

if __name__ == "__main__":
    run_diagnostic()