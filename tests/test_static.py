def test_index_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Wordbridge" in response.data


def test_index_page_uses_graph_instead_of_list(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="chain-list"' not in response.data
    assert b'id="chain-graph"' in response.data
    assert b'id="threshold-slider"' in response.data
    assert b'id="graph-tooltip"' in response.data


def test_index_page_includes_give_up_button(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="give-up-btn"' in response.data


def test_graph_js_served(client):
    response = client.get("/graph.js")
    assert response.status_code == 200
    assert b"class ChainGraph" in response.data
