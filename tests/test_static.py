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
    assert b'id="threshold-input"' in response.data
    assert b'id="graph-tooltip"' in response.data


def test_index_page_includes_give_up_button(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="give-up-btn"' in response.data


def test_index_page_includes_hint_button(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="hint-btn"' in response.data


def test_index_page_includes_difficulty_buttons(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'data-threshold="0.25"' in response.data
    assert b'data-threshold="0.5"' in response.data
    assert b'data-threshold="0.7"' in response.data


def test_graph_js_served(client):
    response = client.get("/graph.js")
    assert response.status_code == 200
    assert b"class ChainGraph" in response.data


def test_scores_page_served(client):
    response = client.get("/scores")
    assert response.status_code == 200
    assert b'id="scores-table"' in response.data


def test_index_page_links_to_scores_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'href="/scores"' in response.data
