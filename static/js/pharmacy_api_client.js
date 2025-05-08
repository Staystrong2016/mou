/**
 * Cliente JavaScript para a API de farmácias
 * Esse script faz chamadas para a nossa API backend em vez de chamar diretamente a API do Google Maps,
 * protegendo assim nossa chave API.
 * 
 * A API de farmácias agora requer uma chave API para evitar uso indevido
 * por aplicações externas não autorizadas.
 */

// Armazenar a chave API de farmácia na sessionStorage
let pharmacyApiKey = sessionStorage.getItem('pharmacy_api_key');
let pharmacyApiKeyExpiry = sessionStorage.getItem('pharmacy_api_key_expiry');

// Função para obter uma nova chave API de farmácia
async function getPharmacyApiKey() {
  try {
    // Verificar se já temos uma chave API válida em sessionStorage
    const now = Date.now();
    if (pharmacyApiKey && pharmacyApiKeyExpiry && now < parseInt(pharmacyApiKeyExpiry)) {
      console.debug('Usando chave API de farmácia existente da sessionStorage');
      return pharmacyApiKey;
    }
    
    console.debug('Solicitando nova chave API de farmácia');
    // Tentar obter a chave do servidor
    try {
      const response = await fetch('/api/pharmacy-api-key');
      const data = await response.json();
      
      if (data.success) {
        // Armazenar a chave API e seu tempo de expiração na sessionStorage
        pharmacyApiKey = data.api_key;
        pharmacyApiKeyExpiry = (now + (data.expires_in * 1000)).toString(); // Converter para timestamp
        
        sessionStorage.setItem('pharmacy_api_key', pharmacyApiKey);
        sessionStorage.setItem('pharmacy_api_key_expiry', pharmacyApiKeyExpiry);
        
        console.debug('Nova chave API de farmácia obtida com sucesso');
        return pharmacyApiKey;
      } else {
        console.warn('Erro ao obter chave API:', data.error);
        // Continuar para ver se temos uma chave pré-definida
      }
    } catch (fetchError) {
      console.warn('Erro na requisição para obter chave API:', fetchError);
      // Continuar para ver se temos uma chave pré-definida
    }
    
    // Se chegamos aqui e temos uma chave API na memória (definida pelo template),
    // significa que a requisição falhou mas temos uma chave válida pré-carregada
    if (pharmacyApiKey && pharmacyApiKeyExpiry) {
      console.debug('Usando chave API de farmácia pré-carregada pelo template');
      return pharmacyApiKey;
    }
    
    // Se não conseguimos obter uma chave, lançar erro
    throw new Error('Não foi possível obter uma chave API de farmácia');
  } catch (error) {
    console.error('Erro ao obter chave API de farmácia:', error);
    throw error;
  }
}

// Função para fazer uma requisição à API de farmácia com autenticação
async function fetchWithPharmacyAuth(url) {
  try {
    // Obter chave API válida
    const apiKey = await getPharmacyApiKey();
    
    // Adicionar a chave API ao cabeçalho da requisição
    const response = await fetch(url, {
      headers: {
        'X-Pharmacy-API-Key': apiKey
      }
    });
    
    return response;
  } catch (error) {
    console.error('Erro ao fazer requisição autenticada à API de farmácia:', error);
    throw error;
  }
}

// Função para buscar farmácias próximas a um endereço
async function findNearbyPharmacies(address, radius = 15000) {
  try {
    if (!address) {
      throw new Error('Endereço não fornecido');
    }
    
    const response = await fetchWithPharmacyAuth(`/api/procurar-farmacias?address=${encodeURIComponent(address)}&radius=${radius}`);
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.error || 'Erro ao buscar farmácias');
    }
    
    return data.data.pharmacies;
  } catch (error) {
    console.error('Erro ao buscar farmácias:', error);
    throw error;
  }
}

// Função para obter detalhes de uma farmácia específica
async function getPharmacyDetails(placeId) {
  try {
    if (!placeId) {
      throw new Error('ID da farmácia não fornecido');
    }
    
    const response = await fetchWithPharmacyAuth(`/api/pharmacy-details?place_id=${encodeURIComponent(placeId)}`);
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.error || 'Erro ao obter detalhes da farmácia');
    }
    
    return data.data;
  } catch (error) {
    console.error('Erro ao obter detalhes da farmácia:', error);
    throw error;
  }
}

// Função para verificar se existem farmácias disponíveis no raio de 15km
async function checkPharmacyAvailability(address) {
  try {
    if (!address) {
      return { available: false, error: 'Endereço não fornecido' };
    }
    
    const response = await fetchWithPharmacyAuth(`/api/procurar-farmacias?address=${encodeURIComponent(address)}`);
    const data = await response.json();
    
    if (!data.success) {
      return { available: false, error: data.error };
    }
    
    return {
      available: data.data.pharmacies.length > 0,
      count: data.data.pharmacies.length,
      nearest: data.data.pharmacies.length > 0 ? data.data.pharmacies[0] : null
    };
  } catch (error) {
    console.error('Erro ao verificar disponibilidade de farmácias:', error);
    return { available: false, error: error.message };
  }
}

// Função para formatar endereço completo a partir dos campos do formulário
function formatFullAddress(street, number, complement, neighborhood, city, state, zipcode) {
  let fullAddress = '';
  
  if (street) fullAddress += street;
  if (number) fullAddress += ', ' + number;
  if (neighborhood) fullAddress += ', ' + neighborhood;
  if (city) fullAddress += ', ' + city;
  if (state) fullAddress += ' - ' + state;
  if (zipcode) fullAddress += ', ' + zipcode;
  
  return fullAddress;
}

// Função para mostrar uma mensagem de feedback na página
function showPharmacyFeedback(available, data) {
  const feedbackElement = document.getElementById('pharmacy-feedback');
  
  if (!feedbackElement) {
    console.warn('Elemento de feedback não encontrado');
    return;
  }
  
  if (available) {
    const pharmacy = data.nearest;
    feedbackElement.innerHTML = `
      <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
        <div class="flex">
          <div class="flex-shrink-0">
            <i class="fas fa-check-circle text-green-500 mr-2"></i>
          </div>
          <div>
            <p class="font-bold">Farmácia encontrada no raio de 15km!</p>
            <p><b>${pharmacy.name}</b> - ${pharmacy.vicinity}</p>
            <p class="mt-1">Distância: ${pharmacy.distanceKm} km</p>
          </div>
        </div>
      </div>
    `;
  } else {
    feedbackElement.innerHTML = `
      <div class="p-4 mb-4 text-sm text-yellow-700 bg-yellow-100 rounded-lg">
        <div class="flex">
          <div class="flex-shrink-0">
            <i class="fas fa-exclamation-triangle text-yellow-500 mr-2"></i>
          </div>
          <div>
            <p class="font-bold">Não há farmácias disponíveis em um raio de 15km do seu endereço.</p>
            <p>Por favor, escolha outra opção de entrega.</p>
          </div>
        </div>
      </div>
    `;
  }
}
