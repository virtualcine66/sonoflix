// Configuração unificada
const categorias = [
    { nome: 'Filmes', id: 'row-filmes', tipo: 'movie', filtro: 'popular', comFiltros: true },
    { nome: 'Séries', id: 'row-series', tipo: 'tv', filtro: 'popular', comFiltros: true }, // Mantemos igual
    { nome: 'Ação', id: 'row-acao', idGenero: '28', tipo: 'movie', filtro: 'discover', comFiltros: false },
    { nome: 'Comédia', id: 'row-comedia', idGenero: '35', tipo: 'movie', filtro: 'discover', comFiltros: false },
    { nome: 'Em Alta', id: 'row-alta', idGenero: '', tipo: 'movie', filtro: 'top_rated', comFiltros: false }
];

// Forçamos o uso de filtros padronizados que sabemos que funcionam
function criarHTMLFiltros(cat) {
    if (!cat.comFiltros) return '';
    
    // Se for Filmes ou Séries, usa uma lógica padrão de popularidade
    return `
        <div class="tabs">
            <button class="active" onclick="filtrar('${cat.tipo}', '${cat.id}', 'popular', this, event)">Populares</button>
            <button onclick="filtrar('${cat.tipo}', '${cat.id}', 'top_rated', this, event)">Mais Votados</button>
        </div>`;
}

// Carrega os filmes de uma categoria específica
async function carregarLinha(tipo, containerId, filtro, genero = '') {
    const row = document.getElementById(containerId);
    if (!row) return;

    // Adicione um log para ver no F12 se ele realmente achou o container
    console.log("Preenchendo container:", containerId);

    const url = genero ? `/pesquisar?tipo=${tipo}&filtro=${filtro}&genero=${genero}` : `/pesquisar?tipo=${tipo}&filtro=${filtro}`;
    
    try {
        const res = await fetch(url);
        const data = await res.json();
        
        // Em vez de limpar o HTML do pai, limpe apenas o filho
        row.innerHTML = ''; 
        
        if (data.results && data.results.length > 0) {
            data.results.forEach(i => {
                if(i.poster_path) {
                    row.insertAdjacentHTML('beforeend', `
                        <div class="card">
                            <a href="/detalhes/${tipo}/${i.id}">
                                <img src="https://image.tmdb.org/t/p/w500${i.poster_path}" class="card-img">
                            </a>
                        </div>`);
                }
            });
        }
    } catch (err) {
        console.error("Erro ao carregar:", err);
    }
}

// Função dos botões de filtro
function filtrar(tipo, containerId, filtro, btn, event) {
    if (event) event.stopPropagation(); // Impede que o clique dispare várias vezes
    
    // Remove classe ativa apenas dos irmãos deste botão
    btn.parentElement.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    // Chama a função
    carregarLinha(tipo, containerId, filtro);
}

// Scroll lateral
function scrollRow(id, amt) {
    const el = document.getElementById(id);
    if (el) el.scrollBy({ left: amt, behavior: 'smooth' });
}

// Inicializa a página
window.onload = async () => {
    const container = document.getElementById('main-content');
    container.innerHTML = ''; 
    
    for (const cat of categorias) {
        const rowId = cat.id;
        
        const section = document.createElement('div');
        section.className = 'category-section';
        section.innerHTML = `
            <div style="display:flex; align-items:center;">
                <h2 class="category-title">${cat.nome}</h2>
                ${criarHTMLFiltros(cat)}
            </div>
            <div class="carousel-container">
                <button class="arrow left" onclick="scrollRow('${rowId}', -600)">❮</button>
                <div class="carousel" id="${rowId}"></div>
                <button class="arrow right" onclick="scrollRow('${rowId}', 600)">❯</button>
            </div>`;
        
        container.appendChild(section);
        await carregarLinha(cat.tipo, rowId, cat.filtro, cat.idGenero);
    }
};