// --- INTERVENÇÃO ANTI-ANÚNCIOS ---
document.addEventListener("DOMContentLoaded", () => {
    const areaProtegida = document.querySelector('.bloqueio-ads');
    if (areaProtegida) {
        const observer = new MutationObserver(() => {
            const adSelectors = ['div[id*="ad"]', 'div[class*="popup"]', 'iframe[src*="ad"]', '.ad-overlay', '.ad-container'];
            adSelectors.forEach(selector => {
                areaProtegida.querySelectorAll(selector).forEach(el => el.remove());
            });
        });
        observer.observe(areaProtegida, { childList: true, subtree: true });
    }
});

function carregarPlayer() {
    const container = document.getElementById('player-container');
    // Agora ele lê a variável que definimos no HTML
    const url = window.PLAYER_URL; 
    
    if (url) {
        container.innerHTML = `
            <iframe 
                src="${url}" 
                style="width:100%; height:100%; border:none;" 
                allow="autoplay; fullscreen; encrypted-media; picture-in-picture" 
                allowfullscreen>
            </iframe>
        `;
        container.scrollIntoView({ behavior: 'smooth' });
    }
}

function salvarHistorico(id, title, poster, tipo) {
    let historico = JSON.parse(localStorage.getItem('continuarAssistindo') || '[]');
    historico = historico.filter(item => item.id !== id);
    historico.unshift({id, title, poster, tipo, time: Date.now()});
    localStorage.setItem('continuarAssistindo', JSON.stringify(historico.slice(0, 10)));
}

