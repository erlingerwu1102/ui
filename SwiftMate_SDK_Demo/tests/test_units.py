import unittest
from app import create_app
import json

class MotionControlTestCase(unittest.TestCase):
    
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
    
    def test_translate_validation(self):
        """测试平移接口参数验证"""
        # 测试缺少参数
        response = self.client.post('/api/v1/translate', 
                                  json={'x_offset': 1})  # 缺少 y_offset, z_offset
        self.assertEqual(response.status_code, 400)
        
        # 测试错误参数类型
        response = self.client.post('/api/v1/translate',
                                  json={'x_offset': 'invalid', 'y_offset': 0, 'z_offset': 0})
        self.assertEqual(response.status_code, 400)
        
        # 测试负数的duration
        response = self.client.post('/api/v1/translate',
                                  json={'x_offset': 1, 'y_offset': 0, 'z_offset': 0, 'duration': -1})
        self.assertEqual(response.status_code, 400)
        
        # 测试空请求体
        response = self.client.post('/api/v1/translate', data='')
        self.assertEqual(response.status_code, 400)
        
        # 测试非JSON请求体
        response = self.client.post('/api/v1/translate', data='not json')
        self.assertEqual(response.status_code, 400)
    
    def test_rotate_validation(self):
        """测试旋转接口参数验证"""
        # 测试缺少参数
        response = self.client.post('/api/v1/rotate', json={})
        self.assertEqual(response.status_code, 400)
        
        # 测试错误参数类型
        response = self.client.post('/api/v1/rotate', json={'angle_deg': 'invalid'})
        self.assertEqual(response.status_code, 400)
        
        # 测试负数的duration
        response = self.client.post('/api/v1/rotate', 
                                  json={'angle_deg': 90, 'duration': -1})
        self.assertEqual(response.status_code, 400)
        
        # 测试空请求体
        response = self.client.post('/api/v1/rotate', data='')
        self.assertEqual(response.status_code, 400)
        
        # 测试非JSON请求体
        response = self.client.post('/api/v1/rotate', data='not json')
        self.assertEqual(response.status_code, 400)
    
    def test_status_endpoint(self):
        """测试状态查询接口"""
        response = self.client.get('/api/v1/status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('current_pos', data['data'])
        self.assertIn('current_angle', data['data'])
        self.assertIn('status', data['data'])
    
    def test_api_routes(self):
        """测试API路由"""
        response = self.client.get('/api/v1/test')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['code'], 200)
        self.assertIn('motion_control_available', data['data'])
    
    def test_system_info(self):
        """测试系统信息接口"""
        response = self.client.get('/api/v1/info')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('endpoints', data['data'])
        self.assertGreater(len(data['data']['endpoints']), 0)

if __name__ == '__main__':
    unittest.main()