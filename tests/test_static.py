def test_index_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Wordbridge" in response.data
