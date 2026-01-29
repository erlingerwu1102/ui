import unittest
from app import create_app
from app.error_handlers import APIException

class ErrorHandlerTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

        @self.app.route('/raise_api')
        def raise_api():
            raise APIException("invalid input", status_code=422, payload={"field":"x"})

        @self.app.route('/raise_exc')
        def raise_exc():
            raise RuntimeError("boom")

    def test_api_exception(self):
        r = self.client.get('/raise_api')
        self.assertEqual(r.status_code, 422)
        data = r.get_json()
        self.assertIn('error', data)
        self.assertEqual(data['error']['type'], 'APIException')
        self.assertEqual(data['error']['message'], 'invalid input')
        self.assertEqual(data['error']['details'], {'field':'x'})

    def test_http_exception(self):
        r = self.client.get('/this-does-not-exist')
        self.assertEqual(r.status_code, 404)
        data = r.get_json()
        self.assertEqual(data['error']['type'], 'HTTPException')

    def test_generic_exception(self):
        r = self.client.get('/raise_exc')
        self.assertEqual(r.status_code, 500)
        data = r.get_json()
        self.assertEqual(data['error']['type'], 'InternalError')
        self.assertEqual(data['error']['message'], 'An internal error occurred')

if __name__ == '__main__':
    unittest.main()
