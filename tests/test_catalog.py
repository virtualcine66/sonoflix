def test_home_with_empty_catalog(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "O catálogo ainda está vazio" in response.get_data(as_text=True)


def test_home_shows_featured_and_rails(client, catalog):
    html = client.get("/").get_data(as_text=True)
    assert "Filmes em alta" in html
    assert "Séries em alta" in html
    assert "Interestelar" in html


def test_movie_list_filters_by_genre(client, catalog):
    html = client.get("/movies?genre=ficcao-cientifica").get_data(as_text=True)
    assert "Interestelar" in html
    assert "Oppenheimer" not in html


def test_unknown_genre_returns_404(client, catalog):
    assert client.get("/movies?genre=nao-existe").status_code == 404


def test_invalid_sort_falls_back_to_default(client, catalog):
    assert client.get("/series?sort=DROP TABLE").status_code == 200


def test_detail_redirects_to_canonical_slug(client, catalog):
    movie = catalog["movie"]
    response = client.get(f"/movie/{movie.id}")
    assert response.status_code == 301
    assert response.headers["Location"].endswith(f"/movie/{movie.id}/interestelar")


def test_movie_detail_page(client, catalog):
    html = client.get(f"/movie/{catalog['movie'].id}/interestelar").get_data(as_text=True)
    assert "Christopher Nolan" in html
    assert "youtube-nocookie.com/embed/zSWdZVtXT7E" in html
    assert "Você também pode gostar" in html


def test_series_detail_lists_seasons(client, catalog):
    html = client.get(f"/series/{catalog['series'].id}/dark").get_data(as_text=True)
    assert "Temporada 1" in html


def test_missing_title_returns_404_page(client):
    response = client.get("/movie/999")
    assert response.status_code == 404
    assert "Página não encontrada" in response.get_data(as_text=True)


def test_search_matches_title_and_people(client, catalog):
    html = client.get("/search?query=nolan").get_data(as_text=True)
    assert "Interestelar" in html and "Oppenheimer" in html
    html = client.get("/search?query=hathaway").get_data(as_text=True)
    assert "Interestelar" in html and "Oppenheimer" not in html


def test_search_treats_wildcards_literally(client, catalog):
    html = client.get("/search?query=%25").get_data(as_text=True)
    assert "Nada encontrado" in html


def test_profile_requires_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_toggle_favorite_without_javascript(logged_in, catalog):
    movie = catalog["movie"]
    response = logged_in.post(f"/favorites/movie/{movie.id}", data={"next": "/profile"})
    assert response.headers["Location"] == "/profile"
    assert "Interestelar" in logged_in.get("/profile").get_data(as_text=True)
    logged_in.post(f"/favorites/movie/{movie.id}")
    assert "Sua lista está vazia" in logged_in.get("/profile").get_data(as_text=True)
