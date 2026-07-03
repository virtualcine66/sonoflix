import os
import requests
from flask import Flask, render_template, request, abort, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API_KEY = os.getenv('MINHA_API_KEY')
API_URL = "https://api.themoviedb.org/3"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/pesquisar')
def pesquisar():
    tipo = request.args.get('tipo', 'movie')
    filtro = request.args.get('filtro', 'popular')
    genero = request.args.get('genero', '')
    
    # Se for 'discover', usamos o endpoint de descoberta com gênero
    if filtro == 'discover':
        url = f"{API_URL}/discover/{tipo}?with_genres={genero}&language=pt-BR&sort_by=popularity.desc"
    else:
        # Para popular, now_playing, upcoming, top_rated
        url = f"{API_URL}/{tipo}/{filtro}?language=pt-BR"
    
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    
    # Se a API falhar, retornamos uma lista vazia em vez de dar erro
    if 'results' not in data:
        return jsonify({"results": []})
        
    return jsonify(data)

@app.route('/buscar')
def buscar():
    query = request.args.get('query')
    # O endpoint 'multi' pesquisa tudo de uma vez
    url = f"{API_URL}/search/multi?query={query}&language=pt-BR&page=1"
    resp = requests.get(url, headers=HEADERS)
    return render_template('buscar.html', data=resp.json(), query=query)

@app.route('/explorar/<tipo>')
def explorar(tipo):
    # 'tipo' pode ser 'movie', 'tv' ou 'anime'
    return render_template('explorar.html', tipo=tipo)

# Mude de @app.route('/explorar/tv') para:
@app.route('/explorar/series')
def explorar_series():
    return render_template('explorar.html', tipo='tv') # Mantemos 'tv' para a API, mas a rota é 'series'

@app.route('/api/discover')
@app.route('/api/discover')
def api_discover():
    tipo = request.args.get('tipo', 'movie')
    genero = request.args.get('genero', '')
    ano = request.args.get('ano', '')
    ordem = request.args.get('ordem', 'popularity.desc')
    page = request.args.get('page', 1)
    
    is_anime = (tipo == 'anime')
    api_tipo = 'tv' if is_anime else tipo
    
    base_url = f"{API_URL}/discover/{api_tipo}"
    params = {"api_key": API_KEY, "language": "pt-BR", "sort_by": ordem, "page": page}
    
    if is_anime:
        params["with_genres"] = "16"            # Apenas Animação
        params["with_original_language"] = "ja" # Apenas Japonês
    else:
        if genero: 
            params["with_genres"] = genero
        
        # A MÁGICA: Se for Série, exclui o gênero Animação (16)
        if tipo == 'tv':
            params["without_genres"] = "16"

    if ano:
        params["first_air_date_year" if api_tipo == 'tv' else "primary_release_year"] = ano
        
    resp = requests.get(base_url, params=params, headers=HEADERS)
    return jsonify(resp.json())
    

@app.route('/api/episodios/<serie_id>/<season_num>')
def get_episodios(serie_id, season_num):
    # Certifique-se de passar o 'api_key' corretamente aqui:
    url = f"{API_URL}/tv/{serie_id}/season/{season_num}?api_key={API_KEY}&language=pt-BR"
    
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    
    return jsonify(data)

@app.route('/detalhes/<tipo>/<int:item_id>')
def detalhes(tipo, item_id):
    # 1. Faz a requisição à API do TMDB
    url = f"{API_URL}/{tipo}/{item_id}?language=pt-BR&append_to_response=credits"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200: 
        abort(404)
    data = resp.json()

    # 2. Define a URL base conforme a documentação da EmbedMovies
    base_url = "https://myembed.biz"
    if tipo == 'movie':
        player_url = f"{base_url}/filme/{item_id}"
    else:
        player_url = f"{base_url}/serie/{item_id}"

    
        
    # 3. Monta o dicionário com os dados
    detalhe = {
        "id": item_id,
        "title": data.get("title") or data.get("name"),
        "overview": data.get("overview") or "Sem sinopse.",
        "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path', '')}",
        "backdrop": f"https://image.tmdb.org/t/p/original{data.get('backdrop_path', '')}",
        "nota": round(data.get("vote_average", 0), 1),
        "duracao": data.get("runtime") or (data.get("episode_run_time")[0] if data.get("episode_run_time") else "N/A"),
        "ano": (data.get("release_date") or data.get("first_air_date", ""))[0:4],
        "temporadas": data.get("seasons", []),
        "url_player": player_url
    }


    # 4 Lógica de seleção de template

    if tipo == 'tv':
        # Passamos 'detalhe' como 'item' para o template
        return render_template('detalhes_serie.html', item=detalhe, tipo=tipo)
    else:
        # Passamos 'detalhe' como 'item' para o template
        return render_template('detalhes.html', item=detalhe, tipo=tipo)
    

    

    

@app.route('/api/generos/<tipo>')
def get_generos(tipo):
    
    url = f"{API_URL}/genre/{tipo}/list?language=pt-BR"
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    
    # Se a lista de gêneros não existir, retorna um array vazio para não quebrar o JS
    return jsonify(data if 'genres' in data else {"genres": []})



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)