def test_list_movies_is_paginated(client, catalog):
    data = client.get("/api/v1/movie?per_page=1").get_json()
    assert data["total"] == 2
    assert data["pages"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Interestelar"


def test_list_sorted_by_title(client, catalog):
    items = client.get("/api/v1/movie?sort=title").get_json()["items"]
    assert [i["title"] for i in items] == ["Interestelar", "Oppenheimer"]


def test_invalid_sort_returns_400(client):
    response = client.get("/api/v1/movie?sort=xyz")
    assert response.status_code == 400
    assert "sort" in response.get_json()["message"]


def test_unknown_kind_returns_json_404(client):
    response = client.get("/api/v1/podcasts")
    assert response.status_code == 404
    assert response.is_json


def test_item_detail(client, catalog):
    series = catalog["series"]
    data = client.get(f"/api/v1/series/{series.id}").get_json()
    assert data["title"] == "Dark"
    assert data["genres"] == [{"name": "Ficção científica", "slug": "ficcao-cientifica"}]
    assert data["seasons"][0]["season_number"] == 1


def test_genres(client, catalog):
    data = {g["slug"]: g for g in client.get("/api/v1/genres").get_json()}
    assert data["drama"]["movies"] == 2
    assert data["ficcao-cientifica"]["series"] == 1


def test_search_requires_two_characters(client, catalog):
    assert client.get("/api/v1/search?q=i").get_json() == {"results": []}
    titles = [r["title"] for r in client.get("/api/v1/search?q=inter").get_json()["results"]]
    assert titles == ["Interestelar"]


def test_favorites_require_login(client, catalog):
    response = client.post(f"/api/v1/favorites/movie/{catalog['movie'].id}")
    assert response.status_code == 401
    assert response.get_json()["error"] == "Não autenticado"


def test_favorite_add_and_remove_are_idempotent(logged_in, catalog):
    url = f"/api/v1/favorites/movie/{catalog['movie'].id}"
    for _ in range(2):
        assert logged_in.post(url).get_json()["favorited"] is True
    assert len(logged_in.get("/api/v1/me/favorites").get_json()["movies"]) == 1
    for _ in range(2):
        assert logged_in.delete(url).get_json()["favorited"] is False
    assert logged_in.get("/api/v1/me/favorites").get_json()["movies"] == []


def test_favorites_post_requires_csrf_when_enabled(app, logged_in, catalog):
    app.config["WTF_CSRF_ENABLED"] = True
    response = logged_in.post(f"/api/v1/favorites/movie/{catalog['movie'].id}")
    assert response.status_code == 400
