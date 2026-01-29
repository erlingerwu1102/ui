import unittest
import json
from app import create_app

class DataStoreAPITest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_drugs_crud(self):
        # create
        rv = self.client.post('/api/v1/drugs', json={'name':'aspirin','qty':10,'unit':'mg','price':1.5})
        self.assertEqual(rv.status_code, 201)
        data = rv.get_json()['data']
        self.assertIn('id', data)
        item_id = data['id']

        # get
        rv = self.client.get(f'/api/v1/drugs/{item_id}')
        self.assertEqual(rv.status_code, 200)
        got = rv.get_json()['data']
        self.assertEqual(got['name'], 'aspirin')

        # update
        rv = self.client.put(f'/api/v1/drugs/{item_id}', json={'qty': 20})
        self.assertEqual(rv.status_code, 200)
        updated = rv.get_json()['data']
        self.assertEqual(updated['qty'], 20)

        # delete
        rv = self.client.delete(f'/api/v1/drugs/{item_id}')
        self.assertEqual(rv.status_code, 200)

        # not found
        rv = self.client.get(f'/api/v1/drugs/{item_id}')
        self.assertEqual(rv.status_code, 404)

    def test_pipelines_and_metrics(self):
        # pipeline create/list
        rv = self.client.post('/api/v1/pipelines', json={'pipeline_no':'P-001','material':'steel'})
        self.assertEqual(rv.status_code, 201)
        pid = rv.get_json()['data']['id']

        rv = self.client.get('/api/v1/pipelines')
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(any(p['id']==pid for p in rv.get_json()['data']))

        # metrics
        rv = self.client.post('/api/v1/metrics', json={'name':'temp','value':36.5})
        self.assertEqual(rv.status_code, 201)
        mid = rv.get_json()['data']['id']

        rv = self.client.get('/api/v1/metrics')
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(any(m['id']==mid for m in rv.get_json()['data']))

if __name__ == '__main__':
    unittest.main()
