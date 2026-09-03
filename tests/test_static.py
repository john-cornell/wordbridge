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


def test_index_page_hint_button_starts_disabled_until_a_word_is_selected(client):
    # Hints are now anchored to a word the player clicks in the graph - the
    # button must start disabled since nothing is selected on page load.
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="hint-btn" class="btn btn-outline" disabled' in response.data
    assert b'id="hint-instruction"' in response.data


def test_graph_js_supports_click_to_select_a_played_word(client):
    response = client.get("/graph.js")
    assert response.status_code == 200
    assert b"getSelectedWord" in response.data
    assert b"onSelectionChange" in response.data


def test_index_page_pins_fireworks_cdn_script_with_integrity(client):
    # Must stay pinned to an exact version with a matching integrity hash -
    # never a floating range like "@2.x", and never without integrity/
    # crossorigin, since this is the app's only external runtime script.
    response = client.get("/")
    assert response.status_code == 200
    assert b"fireworks-js@2." in response.data
    assert b"fireworks-js@2.x" not in response.data
    assert b'integrity="sha384-' in response.data
    assert b'crossorigin="anonymous"' in response.data
    assert b'id="fireworks-overlay"' in response.data


def test_index_page_pins_confetti_cdn_script_with_integrity(client):
    # Same rule as fireworks-js: pinned exact version, integrity + crossorigin
    # always present so a tampered/failed CDN response can't run silently.
    response = client.get("/")
    assert response.status_code == 200
    assert b"canvas-confetti@1." in response.data
    assert b"canvas-confetti@1.x" not in response.data
    assert response.data.count(b'integrity="sha384-') == 2
    assert response.data.count(b'crossorigin="anonymous"') == 2


def test_crying_confetti_guards_against_missing_cdn_global(client):
    app_js = client.get("/app.js")
    assert b'typeof confetti === "undefined"' in app_js.data
    assert b'typeof confetti !== "undefined"' in app_js.data


def test_index_page_includes_difficulty_buttons(client):
    response = client.get("/")
    assert response.status_code == 200
    for value in ("0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.8"):
        assert f'data-threshold="{value}"'.encode() in response.data
    for label in ("Simple", "Easy", "Normal", "Tricky", "Hard", "Very Hard", "Insane"):
        assert label.encode() in response.data


def test_graph_js_served(client):
    response = client.get("/graph.js")
    assert response.status_code == 200
    assert b"class ChainGraph" in response.data


def test_negative_scores_are_styled_red(client):
    app_js = client.get("/app.js")
    scores_js = client.get("/scores.js")
    style_css = client.get("/style.css")

    assert b'classList.toggle("negative-score", data.score < 0)' in app_js.data
    assert b'classList.toggle("negative-score", entry.score < 0)' in scores_js.data
    assert b".negative-score" in style_css.data
    assert b"color: var(--danger)" in style_css.data


def test_scores_page_served(client):
    response = client.get("/scores")
    assert response.status_code == 200
    assert b'id="scores-table"' in response.data
    assert b'id="clear-scores-btn"' in response.data
    assert b"<th>Threshold</th>" in response.data


def test_index_page_links_to_scores_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'href="/scores"' in response.data


def test_scores_page_includes_player_filter_and_solution_modal(client):
    response = client.get("/scores")
    assert response.status_code == 200
    assert b'id="player-filter"' in response.data
    assert b'id="solution-modal"' in response.data
    assert b'id="solution-graph"' in response.data
    assert b'id="solution-view-direct"' in response.data
    assert b'id="solution-view-full"' in response.data


def test_scores_page_loads_graph_js(client):
    response = client.get("/scores")
    assert response.status_code == 200
    assert b'<script src="/graph.js">' in response.data


def test_version_js_served(client):
    response = client.get("/version.js")
    assert response.status_code == 200
    assert b"/api/health" in response.data


def test_index_and_scores_pages_include_version_footer_and_script(client):
    for path in ("/", "/scores"):
        response = client.get(path)
        assert response.status_code == 200
        assert b'id="version-info"' in response.data
        assert b'<script src="/version.js">' in response.data
