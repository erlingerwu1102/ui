import requests
import time

url = 'http://127.0.0.1:8000/api/v2/stream/state?max=5&interval=0.2'
print('Connecting to', url)
with requests.get(url, stream=True, timeout=10) as r:
    if r.status_code != 200:
        print('Failed to connect', r.status_code, r.text)
    else:
        lines = r.iter_lines()
        cnt = 0
        try:
            for line in lines:
                if line:
                    text = line.decode('utf-8')
                    if text.startswith('data: '):
                        print('Event:', text[6:])
                        cnt += 1
                if cnt >= 5:
                    break
        except Exception as e:
            print('Stream error', e)

print('done')
