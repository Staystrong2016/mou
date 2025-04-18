/**
 * Utmify Helper
 * 
 * Este script facilita a integração entre o funil de vendas e a Utmify,
 * permitindo o rastreamento e atribuição corretos de conversões.
 */

// Namespace para as funções Utmify
const UtmifyHelper = {
  
  /**
   * Coleta os parâmetros UTM da URL ou do localStorage
   * @returns {Object} Objeto com parâmetros UTM
   */
  collectUtmParams: function() {
    // Primeiro, tenta recuperar do localStorage (caso o utm_tracker.js esteja sendo usado)
    const storedParams = localStorage.getItem('utmParams');
    if (storedParams) {
      try {
        return JSON.parse(storedParams);
      } catch (e) {
        console.error('Erro ao analisar UTM params do localStorage:', e);
      }
    }
    
    // Se não encontrar no localStorage, busca na URL atual
    const urlSearchParams = new URLSearchParams(window.location.search);
    const params = {};
    
    // Parâmetros UTM padrão
    const standardParams = [
      'utm_source', 
      'utm_medium', 
      'utm_campaign', 
      'utm_content', 
      'utm_term',
      'fbclid',
      'gclid',
      'ttclid',
      'ref'
    ];
    
    // Extrair parâmetros da URL
    standardParams.forEach(param => {
      if (urlSearchParams.has(param)) {
        params[param] = urlSearchParams.get(param);
      }
    });
    
    return params;
  },
  
  /**
   * Adiciona os parâmetros UTM a uma requisição de pagamento
   * @param {Object} paymentData - Dados de pagamento
   * @returns {Object} Dados de pagamento com parâmetros UTM adicionados
   */
  addUtmParamsToPayment: function(paymentData) {
    const utmParams = this.collectUtmParams();
    
    // Se houver parâmetros UTM, adicione-os ao objeto de pagamento
    if (Object.keys(utmParams).length > 0) {
      paymentData.utm_params = utmParams;
      console.log('UTM params added to payment data:', utmParams);
    } else {
      console.log('No UTM params found to add to payment data');
    }
    
    return paymentData;
  },
  
  /**
   * Adiciona dados do cliente e parâmetros UTM para envio à Utmify
   * @param {Object} transactionData - Dados da transação
   * @returns {Object} Dados completos para Utmify
   */
  prepareUtmifyData: function(transactionData) {
    // Obter parâmetros UTM
    const utmParams = this.collectUtmParams();
    
    // Dados básicos para Utmify (definidos pelo backend)
    const utmifyData = { ...transactionData };
    
    // Adicionar parâmetros UTM individualmente para facilitar a integração
    if (utmParams.utm_source) utmifyData.utm_source = utmParams.utm_source;
    if (utmParams.utm_medium) utmifyData.utm_medium = utmParams.utm_medium;
    if (utmParams.utm_campaign) utmifyData.utm_campaign = utmParams.utm_campaign;
    if (utmParams.utm_content) utmifyData.utm_content = utmParams.utm_content;
    if (utmParams.utm_term) utmifyData.utm_term = utmParams.utm_term;
    
    // Adicionar Pixel IDs se disponíveis
    if (utmParams.fbclid) utmifyData.fbclid = utmParams.fbclid;
    if (utmParams.gclid) utmifyData.gclid = utmParams.gclid;
    if (utmParams.ttclid) utmifyData.ttclid = utmParams.ttclid;
    
    return utmifyData;
  },
  
  /**
   * Registra um evento na Utmify (para uso futuro)
   * @param {string} eventName - Nome do evento
   * @param {Object} eventData - Dados do evento
   */
  trackEvent: function(eventName, eventData = {}) {
    // Obter parâmetros UTM
    const utmParams = this.collectUtmParams();
    
    // Combinar dados do evento com parâmetros UTM
    const combinedData = {
      ...eventData,
      ...utmParams,
      event: eventName,
      timestamp: new Date().toISOString()
    };
    
    // Log para debug
    console.log('Utmify event tracked:', combinedData);
    
    // Para futuras implementações, poderia enviar para a API da Utmify
    // fetch('/api/utmify/track', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(combinedData)
    // });
  }
};

// Adicionar ao objeto window para acesso global
window.UtmifyHelper = UtmifyHelper;