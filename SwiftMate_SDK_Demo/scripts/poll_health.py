import time
import requests
import sys

for i in range(10):
    try:
        r = requests.get('http://127.0.0.1:8000/api/v1/health', timeout=2)
        print('HEALTH', r.status_code)
        print(r.text)
        sys.exit(0)
    except Exception as e:
        print('attempt', i, 'failed:', e)
        time.sleep(1)

print('service did not become available')
sys.exit(2)
