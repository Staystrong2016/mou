/**
 * UTM Parameter Tracker
 * 
 * Este script é responsável por capturar, armazenar e propagar 
 * parâmetros UTM e outros parâmetros de URL em todo o funil de vendas.
 * 
 * Ele deve ser incluído em todas as páginas do funil para garantir que os 
 * parâmetros sejam preservados entre páginas.
 */

// Função para obter parâmetros da URL
function getUrlParams() {
  const urlSearchParams = new URLSearchParams(window.location.search);
  return Object.fromEntries(urlSearchParams.entries());
}

// Função para salvar parâmetros UTM no localStorage
function saveUtmParams() {
  // Obter todos os parâmetros da URL
  const urlParams = getUrlParams();
  
  // Lista de parâmetros UTM para rastrear
  const utmParamsList = [
    'utm_source', 
    'utm_medium', 
    'utm_campaign', 
    'utm_content', 
    'utm_term',
    'fbclid',      // Facebook Click ID
    'gclid',       // Google Click ID
    'ttclid',      // TikTok Click ID
    'ref'          // Referral ID
  ];
  
  // Objeto para armazenar apenas os parâmetros UTM
  const utmParams = {};
  
  // Verificar se existem parâmetros UTM na URL atual
  let hasUtmParams = false;
  utmParamsList.forEach(param => {
    if (urlParams[param]) {
      utmParams[param] = urlParams[param];
      hasUtmParams = true;
    }
  });
  
  // Se houver parâmetros UTM na URL, atualize o localStorage
  if (hasUtmParams) {
    // Armazenar como string JSON
    localStorage.setItem('utmParams', JSON.stringify(utmParams));
    console.log('UTM params captured and saved:', utmParams);
  } else {
    // Se não houver na URL, tente recuperar do localStorage
    const storedUtmParams = localStorage.getItem('utmParams');
    if (storedUtmParams) {
      console.log('Using UTM params from localStorage:', JSON.parse(storedUtmParams));
    } else {
      console.log('No UTM params found in URL or localStorage');
    }
  }
}

// Função para adicionar parâmetros UTM a uma URL
function appendUtmParamsToUrl(url) {
  // Verificar se temos parâmetros UTM armazenados
  const storedUtmParams = localStorage.getItem('utmParams');
  if (!storedUtmParams) {
    return url; // Retornar URL original se não houver parâmetros
  }
  
  // Parseie os parâmetros armazenados
  const utmParams = JSON.parse(storedUtmParams);
  
  // Criar objeto de URL para manipular facilmente
  let urlObj;
  try {
    urlObj = new URL(url);
  } catch (e) {
    // Se a URL não for completa, assume que é um caminho relativo
    urlObj = new URL(url, window.location.origin);
  }
  
  // Adicionar cada parâmetro UTM à URL
  for (const [key, value] of Object.entries(utmParams)) {
    urlObj.searchParams.set(key, value);
  }
  
  return urlObj.href;
}

// Função para obter parâmetros UTM como um objeto
function getUtmParams() {
  const storedUtmParams = localStorage.getItem('utmParams');
  return storedUtmParams ? JSON.parse(storedUtmParams) : {};
}

// Função para adicionar parâmetros UTM a todos os links na página
function addUtmParamsToAllLinks() {
  // Verificar se temos parâmetros UTM armazenados
  const storedUtmParams = localStorage.getItem('utmParams');
  if (!storedUtmParams) {
    return; // Não fazer nada se não houver parâmetros
  }
  
  // Obter todos os links na página
  const links = document.querySelectorAll('a');
  
  // Para cada link, adicionar os parâmetros UTM
  links.forEach(link => {
    // Ignorar links externos ou âncoras
    const href = link.getAttribute('href') || '';
    if (href.startsWith('#') || href.startsWith('javascript:') || href === '') {
      return;
    }
    
    // Não modificar links para domínios externos
    if (href.startsWith('http') && !href.includes(window.location.hostname)) {
      return;
    }
    
    // Adicionar parâmetros UTM ao link
    link.setAttribute('href', appendUtmParamsToUrl(href));
  });
}

// Inicializar quando a página carregar
document.addEventListener('DOMContentLoaded', function() {
  // Salvar parâmetros UTM da URL atual
  saveUtmParams();
  
  // Adicionar parâmetros UTM a todos os links na página
  addUtmParamsToAllLinks();
  
  // Log para debug
  console.log('UTM Tracker initialized');
});

// Expor funções para uso global
window.utmTracker = {
  getUrlParams,
  saveUtmParams,
  appendUtmParamsToUrl,
  getUtmParams,
  addUtmParamsToAllLinks
};