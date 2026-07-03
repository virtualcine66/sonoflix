let currentPage = 1;

// Gerar anos automaticamente
function popularAnos() {
    const select = document.getElementById('ano');
    if (!select) return;
    const anoAtual = new Date().getFullYear();
    for (let i = anoAtual; i >= 1950; i--) {
        select.innerHTML += `<option value="${i}">${i}</option>`;
    }
}

async function carregarGeneros(tipo) {
    const res = await fetch(`/api/generos/${tipo}`);
    const data = await res.json();
    const select = document.getElementById('genero');
    if (!select) return;
    data.genres.forEach(genero => {
        const option = document.createElement('option');
        option.value = genero.id;
        option.textContent = genero.name;
        select.appendChild(option);
        // No carregarGeneros
    if (tipo === 'anime') {
    // Opcional: Se for anime, podemos esconder o select de gênero ou 
    // carregar apenas gêneros específicos
        document.getElementById('genero').style.display = 'none'; 
}
    });
}

async function carregarExplorar(page = 1) {
    currentPage = page;
    const genero = document.getElementById('genero') ? document.getElementById('genero').value : '';
    const ano = document.getElementById('ano') ? document.getElementById('ano').value : '';
    const ordem = document.getElementById('ordem') ? document.getElementById('ordem').value : 'popularity.desc';

    // BUSCA DUPLA: Carrega a página atual e a próxima para garantir pelo menos 27 itens
    const res = await fetch(`/api/discover?tipo=${TIPO}&genero=${genero}&ano=${ano}&ordem=${ordem}&page=${page}`);
    const data = await res.json();
    
    const resNext = await fetch(`/api/discover?tipo=${TIPO}&genero=${genero}&ano=${ano}&ordem=${ordem}&page=${page + 1}`);
    const dataNext = await resNext.json();
    
    // Combina os resultados
    const todosItens = [...(data.results || []), ...(dataNext.results || [])];
    const itensParaExibir = todosItens.slice(0, 27); // Corta exatamente em 27

    const grid = document.getElementById('results-grid');
    if (!grid) return;
    grid.innerHTML = '';
    
    itensParaExibir.forEach(i => {
        if(i.poster_path) {
            grid.innerHTML += `<div class="card"><a href="/detalhes/${TIPO}/${i.id}"><img src="https://image.tmdb.org/t/p/w500${i.poster_path}"></a></div>`;
        }
    });

    window.scrollTo({ top: 0, behavior: 'smooth' });
    
    // Passamos data.total_pages para a paginação continuar funcionando normalmente
    renderPagination(data.total_pages || 1, page);
}

function renderPagination(totalPages, currentPage) {
    const pag = document.getElementById('page-buttons');
    if (!pag) return;
    pag.innerHTML = '';

    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);

    if (currentPage > 1) {
        pag.innerHTML += `<button class="btn-page" onclick="carregarExplorar(${currentPage - 1})">« Anterior</button>`;
    }

    for (let i = startPage; i <= endPage; i++) {
        pag.innerHTML += `<button class="btn-page ${i === currentPage ? 'active' : ''}" onclick="carregarExplorar(${i})">${i}</button>`;
    }

    if (currentPage < totalPages) {
        pag.innerHTML += `<button class="btn-page" onclick="carregarExplorar(${currentPage + 1})">Próximo »</button>`;
    }
}

function resetAndLoad() { 
    carregarExplorar(1); 
}

window.onload = () => { 
    popularAnos(); 
    carregarGeneros(TIPO); 
    carregarExplorar(1); 
};