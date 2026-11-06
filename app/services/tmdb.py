"""
Cliente da API do TMDb (https://developer.themoviedb.org).

Centraliza autenticação, idioma, timeout, cache e tratamento de erros,
para que o resto do app nunca chame `requests` direto.
"""
import time

import requests

from app.models import MOVIE

BASE_URL = "https://api.themoviedb.org/3"
# Idiomas aceitos para vídeos: português, inglês e vídeos sem idioma definido.
VIDEO_LANGUAGES = "pt,en,null"


class TMDbError(RuntimeError):
    """Erro de comunicação com o TMDb, com mensagem pronta para exibir ao usuário."""

    def __init__(self, message, retryable=False, status_code=None, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = retry_after


class TMDbNotConfigured(TMDbError):
    pass


class TMDbClient:
    def __init__(self, token="", api_key="", language="pt-BR", region="BR",
                 timeout=8.0, cache_ttl=900, session=None):
        self.token = token
        self.api_key = api_key
        self.language = language
        self.region = region
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.session = session or requests.Session()
        self._cache = {}
        self._last_request = 0.0

    @classmethod
    def from_config(cls, config):
        return cls(
            token=config.get("TMDB_API_TOKEN", ""),
            api_key=config.get("TMDB_API_KEY", ""),
            language=config.get("TMDB_LANGUAGE", "pt-BR"),
            region=config.get("TMDB_REGION", "BR"),
            timeout=config.get("TMDB_TIMEOUT", 8.0),
        )

    @property
    def configured(self):
        return bool(self.token or self.api_key)

    def _get(self, path, **params):
        if not self.configured:
            raise TMDbNotConfigured("Configure TMDB_API_TOKEN (ou TMDB_API_KEY) no arquivo .env.")

        params = {"language": self.language, **{k: v for k, v in params.items() if v is not None}}
        cache_key = (path, tuple(sorted(params.items())))
        cached = self._cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            params["api_key"] = self.api_key

        delay = 0.25 - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        self._last_request = time.monotonic()
        if getattr(self, 'before_request', None):
            self.before_request()
        try:
            response = self.session.get(BASE_URL + path, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TMDbError("Não foi possível conectar ao TMDb. Verifique sua conexão.", retryable=True) from exc

        if response.status_code == 401:
            raise TMDbError("A credencial do TMDb é inválida. Confira o .env.")
        if response.status_code == 404:
            raise TMDbError("Título não encontrado no TMDb.", status_code=404)
        if response.status_code == 429:
            raw = getattr(response, 'headers', {}).get('Retry-After', '')
            try:
                delay = max(1, float(raw))
            except (ValueError, TypeError):
                delay = 5
            raise TMDbError("O TMDb limitou as requisições. Tente de novo em alguns segundos.",
                            retryable=True, status_code=429, retry_after=delay)
        if not response.ok:
            raise TMDbError(f"O TMDb respondeu com erro {response.status_code}.", retryable=response.status_code >= 500)

        data = response.json()
        if len(self._cache) >= 512:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = (time.monotonic() + self.cache_ttl, data)
        return data

    # --- Consultas -------------------------------------------------------

    def search(self, query, kind=MOVIE, page=1):
        """Busca filmes ou séries e devolve resultados já normalizados."""
        path = "/search/movie" if kind == MOVIE else "/search/tv"
        data = self._get(path, query=query, page=page, include_adult="false")
        return [summarize(item, kind) for item in data.get("results", [])]

    def movie(self, tmdb_id):
        return self._get(f"/movie/{int(tmdb_id)}", append_to_response="videos,credits",
                         include_video_language=VIDEO_LANGUAGES)

    def tv(self, tmdb_id):
        return self._get(f"/tv/{int(tmdb_id)}", append_to_response="videos,credits",
                         include_video_language=VIDEO_LANGUAGES)

    def season(self, tv_id, season_number):
        return self._get(f"/tv/{int(tv_id)}/season/{int(season_number)}")


def summarize(item, kind):
    """Formato único para resultados de busca de filmes e séries."""
    released = item.get("release_date") or item.get("first_air_date") or ""
    return {
        "tmdb_id": item["id"],
        "kind": kind,
        "title": item.get("title") or item.get("name") or "Sem título",
        "original_title": item.get("original_title") or item.get("original_name"),
        "year": released[:4] or None,
        "overview": item.get("overview") or "",
        "poster_path": item.get("poster_path"),
        "rating": item.get("vote_average") or 0,
    }


def pick_trailer(videos, language="pt"):
    """
    Escolhe o melhor vídeo do YouTube: trailer > teaser, no idioma preferido,
    oficial e mais recente.
    """
    candidates = [v for v in (videos or {}).get("results", []) if v.get("site") == "YouTube" and v.get("key")]
    if not candidates:
        return None

    def score(video):
        return (
            video.get("type") == "Trailer",
            video.get("type") == "Teaser",
            video.get("iso_639_1") == language,
            bool(video.get("official")),
            video.get("published_at") or "",
        )

    return max(candidates, key=score)["key"]
