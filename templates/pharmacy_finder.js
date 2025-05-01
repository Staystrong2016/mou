// Função para buscar farmácias próximas com base no endereço
function findNearbyPharmacies(address, radius = 15000) { // Raio em metros (15km)
  return new Promise((resolve, reject) => {
    if (!address) {
      reject(new Error('Endereço não fornecido'));
      return;
    }
    
    // Geocodificar o endereço para obter coordenadas
    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ address: address }, (results, status) => {
      if (status !== 'OK' || !results[0]) {
        reject(new Error('Não foi possível encontrar coordenadas para o endereço fornecido'));
        return;
      }
      
      const location = results[0].geometry.location;
      
      // Buscar farmácias próximas usando Places API
      const service = new google.maps.places.PlacesService(document.createElement('div'));
      
      service.nearbySearch({
        location: location,
        radius: radius,
        type: 'pharmacy'
      }, (results, status) => {
        if (status === google.maps.places.PlacesServiceStatus.OK) {
          // Ordenar por distância (usando distância em linha reta como aproximação inicial)
          const pharmaciesWithDistance = results.map(place => {
            const placeLocation = place.geometry.location;
            const distance = google.maps.geometry.spherical.computeDistanceBetween(location, placeLocation);
            
            return {
              ...place,
              distance: distance,
              distanceKm: (distance / 1000).toFixed(2)
            };
          }).sort((a, b) => a.distance - b.distance);
          
          resolve(pharmaciesWithDistance);
        } else {
          reject(new Error('Não foi possível encontrar farmácias próximas'));
        }
      });
    });
  });
}

// Função para obter a farmácia mais próxima
function getNearestPharmacy(address) {
  return findNearbyPharmacies(address)
    .then(pharmacies => {
      if (pharmacies && pharmacies.length > 0) {
        return pharmacies[0]; // Retorna a farmácia mais próxima
      }
      throw new Error('Nenhuma farmácia encontrada no raio de 15km');
    });
}

// Função para calcular rota e tempo estimado até a farmácia
function calculateRouteToPharmacy(originAddress, pharmacyLocation) {
  return new Promise((resolve, reject) => {
    const directionsService = new google.maps.DirectionsService();
    
    directionsService.route({
      origin: originAddress,
      destination: { lat: pharmacyLocation.lat(), lng: pharmacyLocation.lng() },
      travelMode: google.maps.TravelMode.DRIVING
    }, (result, status) => {
      if (status === 'OK') {
        const route = result.routes[0];
        const leg = route.legs[0];
        
        resolve({
          distance: leg.distance.text,
          duration: leg.duration.text,
          directions: result
        });
      } else {
        reject(new Error('Não foi possível calcular a rota para a farmácia'));
      }
    });
  });
}

// Função para verificar se existem farmácias no raio de 15km
async function checkPharmacyAvailability(address) {
  try {
    const pharmacies = await findNearbyPharmacies(address);
    return {
      available: pharmacies.length > 0,
      count: pharmacies.length,
      nearest: pharmacies.length > 0 ? pharmacies[0] : null
    };
  } catch (error) {
    console.error('Erro ao verificar disponibilidade de farmácias:', error);
    return {
      available: false,
      error: error.message
    };
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
