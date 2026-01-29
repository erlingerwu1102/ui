import requests
import time

base = 'http://127.0.0.1:8000/api/v2'

# 等待服务就绪
for i in range(10):
    try:
        r = requests.get(f'{base}/test', timeout=2)
        if r.status_code == 200:
            print('V2 test OK:', r.json())
            break
    except Exception as e:
        print('等待服务启动...', i, e)
    time.sleep(1)
else:
    print('服务未能在超时内启动'); raise SystemExit(1)

# 测试多段运镜
payload = {
    'waypoints': [[0.4,0.4,0.3],[0.6,0.4,0.3],[0.6,0.6,0.3]],
    'interpolation_type': 'linear',
    'duration': 3.0
}

r = requests.post(f'{base}/trajectory/multi-segment', json=payload)
print('/trajectory/multi-segment ->', r.status_code, r.text)

data = r.json() if r.status_code==200 else {}
if data.get('data') and data['data'].get('task_id'):
    tid = data['data']['task_id']
    print('任务ID:', tid)
    time.sleep(1)
    r2 = requests.get(f'{base}/task/status', params={'task_id': tid})
    print('/task/status ->', r2.status_code, r2.text)

# 测试力矩前馈开关
r = requests.post(f'{base}/torque/feedforward/enable', json={'enabled': True})
print('/torque/feedforward/enable ->', r.status_code, r.text)

# 测试预设环绕（降级模式或真实现）
r = requests.post(f'{base}/trajectory/preset/circle', json={'center_pos':[0.5,0.5,0.3], 'radius':0.2, 'duration':4})
print('/trajectory/preset/circle ->', r.status_code, r.text)

print('测试完成')
