from app import create_app

app = create_app()
client = app.test_client()
res = client.get('/api/v1/health')
print(res.status_code)
print(res.get_data(as_text=True))
