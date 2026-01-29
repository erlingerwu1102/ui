import unittest
from app import create_app

class CollisionManualTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_collision_config_and_manual_dynamics(self):
        # get default collision config
        rv = self.client.get('/api/v1/config/collision')
        self.assertEqual(rv.status_code, 200)
        default = rv.get_json()['data']
        self.assertIn('sensitivity', default)

        # set collision config
        rv = self.client.post('/api/v1/config/collision', json={'sensitivity': 30, 'response_time': 0.2, 'allowed_error_time': 0.3})
        self.assertEqual(rv.status_code, 200)
        changed = rv.get_json()['data']
        self.assertEqual(changed['sensitivity'], 30)

        # manual dynamics CRUD
        rv = self.client.post('/api/v1/manual_dynamics', json={'axis':'axis1','error':1.5,'sensitivity':40})
        self.assertEqual(rv.status_code, 201)
        item = rv.get_json()['data']
        mid = item['id']

        rv = self.client.get(f'/api/v1/manual_dynamics/{mid}')
        self.assertEqual(rv.status_code, 200)
        got = rv.get_json()['data']
        self.assertEqual(got['axis'],'axis1')

        rv = self.client.put(f'/api/v1/manual_dynamics/{mid}', json={'error':2.0})
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.get_json()['data']['error'], 2.0)

        rv = self.client.delete(f'/api/v1/manual_dynamics/{mid}')
        self.assertEqual(rv.status_code, 200)

if __name__ == '__main__':
    unittest.main()
