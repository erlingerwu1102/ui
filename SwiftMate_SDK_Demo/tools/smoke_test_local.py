import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
import json

app = create_app()

with app.test_client() as client:
    print('GET /')
    r = client.get('/')
    print(r.status_code, r.get_data(as_text=True)[:200])

    print('\nGET /api/v1/test')
    r = client.get('/api/v1/test')
    print(r.status_code, r.json)

    print('\nGET /api/v1/status')
    r = client.get('/api/v1/status')
    print(r.status_code, r.json)

    print('\nPOST /api/v1/translate (invalid body)')
    r = client.post('/api/v1/translate', json={'x_offset': 1})
    print(r.status_code, r.json)

    print('\nPOST /api/v1/translate (valid)')
    r = client.post('/api/v1/translate', json={'x_offset': 0.1, 'y_offset': 0, 'z_offset': 0, 'duration': 0})
    print(r.status_code, r.json)

    print('\nPOST /api/v1/rotate (valid)')
    r = client.post('/api/v1/rotate', json={'angle_deg': 30, 'duration': 0})
    print(r.status_code, r.json)

    print('\nGET /api/v1/identification_runs')
    r = client.get('/api/v1/identification_runs')
    print(r.status_code, r.json)
