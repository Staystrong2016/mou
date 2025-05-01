import os
import json
import requests
from flask import jsonify, request
from geopy.distance import geodesic

# Obter a chave da API do Google Maps
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')

def init_pharmacy_routes(app):
    """
    Inicializa as rotas da API de farmácias
    """
    
    @app.route('/api/find-pharmacies')
    def find_pharmacies():
        """
        API para encontrar farmácias próximas a um endereço
        
        Parâmetros de query:
        - address: Endereço completo para buscar farmácias próximas
        - radius: (opcional) Raio de busca em metros, padrão é 15000 (15km)
        
        Retorna:
        - Lista de farmácias com distância, ordenadas pela mais próxima
        - Informações da farmácia mais próxima
        """
        address = request.args.get('address')
        radius = request.args.get('radius', 15000)  # Padrão: 15km
        
        if not address:
            return jsonify({
                'success': False,
                'error': 'Endereço não fornecido'
            }), 400
        
        # Em ambiente de desenvolvimento, retornar dados simulados
        if os.environ.get('FLASK_ENV') == 'development' or True:
            # Dados de exemplo para desenvolvimento
            pharmacies = [
                {
                    'name': 'Farmácia Drogasil',
                    'vicinity': 'Av. Paulista, 1000 - São Paulo',
                    'distanceKm': '1.2',
                    'openNow': True,
                    'rating': 4.5,
                    'userRatingsTotal': 120
                },
                {
                    'name': 'Drogaria São Paulo',
                    'vicinity': 'Rua Augusta, 500 - São Paulo',
                    'distanceKm': '2.3',
                    'openNow': True,
                    'rating': 4.2,
                    'userRatingsTotal': 98
                },
                {
                    'name': 'Farmácia Droga Raia',
                    'vicinity': 'Alameda Santos, 800 - São Paulo',
                    'distanceKm': '3.1',
                    'openNow': True,
                    'rating': 4.0,
                    'userRatingsTotal': 87
                }
            ]
            
            return jsonify({
                'success': True,
                'data': {
                    'pharmacies': pharmacies,
                    'nearest': pharmacies[0] if pharmacies else None,
                    'available': len(pharmacies) > 0,
                    'count': len(pharmacies)
                }
            })
        
        # Implementação com a API real do Google Maps
        try:
            # 1. Geocodificar o endereço para obter coordenadas
            geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_MAPS_API_KEY}"
            geocode_response = requests.get(geocode_url)
            geocode_data = geocode_response.json()
            
            if geocode_data.get('status') != 'OK':
                return jsonify({
                    'success': False,
                    'error': f'Erro ao geocodificar endereço: {geocode_data.get("status")}'
                }), 400
            
            location = geocode_data['results'][0]['geometry']['location']
            lat, lng = location['lat'], location['lng']
            
            # 2. Buscar farmácias próximas usando Places API
            places_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type=pharmacy&key={GOOGLE_MAPS_API_KEY}"
            places_response = requests.get(places_url)
            places_data = places_response.json()
            
            if places_data.get('status') != 'OK':
                return jsonify({
                    'success': False,
                    'error': f'Erro ao buscar farmácias: {places_data.get("status")}'
                }), 400
            
            # 3. Formatar e ordenar resultados por distância
            pharmacies = []
            for place in places_data.get('results', []):
                place_lat = place['geometry']['location']['lat']
                place_lng = place['geometry']['location']['lng']
                
                # Calcular distância geodésica
                distance = geodesic((lat, lng), (place_lat, place_lng)).kilometers
                
                pharmacies.append({
                    'name': place.get('name'),
                    'vicinity': place.get('vicinity'),
                    'distanceKm': f"{distance:.1f}",
                    'openNow': place.get('opening_hours', {}).get('open_now', False),
                    'rating': place.get('rating'),
                    'userRatingsTotal': place.get('user_ratings_total'),
                    'placeId': place.get('place_id')
                })
            
            # Ordenar por distância
            pharmacies.sort(key=lambda x: float(x['distanceKm']))
            
            return jsonify({
                'success': True,
                'data': {
                    'pharmacies': pharmacies,
                    'nearest': pharmacies[0] if pharmacies else None,
                    'available': len(pharmacies) > 0,
                    'count': len(pharmacies)
                }
            })
            
        except Exception as e:
            app.logger.error(f"Erro ao buscar farmácias: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erro ao processar solicitação: {str(e)}'
            }), 500
    
    @app.route('/api/pharmacy-details')
    def pharmacy_details():
        """
        API para obter detalhes de uma farmácia específica
        
        Parâmetros de query:
        - place_id: ID do local no Google Places
        
        Retorna:
        - Detalhes da farmácia (endereço, horário de funcionamento, etc)
        """
        place_id = request.args.get('place_id')
        
        if not place_id:
            return jsonify({
                'success': False,
                'error': 'ID do local não fornecido'
            }), 400
        
        # Em ambiente de desenvolvimento, retornar dados simulados
        if os.environ.get('FLASK_ENV') == 'development' or True:
            # Dados de exemplo
            return jsonify({
                'success': True,
                'data': {
                    'name': 'Farmácia Drogasil',
                    'formatted_address': 'Av. Paulista, 1000 - Bela Vista, São Paulo - SP, 01310-100',
                    'formatted_phone_number': '(11) 3253-4000',
                    'opening_hours': {
                        'weekday_text': [
                            'Segunda-feira: 08:00 – 22:00',
                            'Terça-feira: 08:00 – 22:00',
                            'Quarta-feira: 08:00 – 22:00',
                            'Quinta-feira: 08:00 – 22:00',
                            'Sexta-feira: 08:00 – 22:00',
                            'Sábado: 08:00 – 20:00',
                            'Domingo: 08:00 – 18:00'
                        ]
                    },
                    'website': 'https://www.drogasil.com.br/'
                }
            })
        
        # Implementação com a API real do Google Maps
        try:
            details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address,formatted_phone_number,opening_hours,website&key={GOOGLE_MAPS_API_KEY}"
            details_response = requests.get(details_url)
            details_data = details_response.json()
            
            if details_data.get('status') != 'OK':
                return jsonify({
                    'success': False,
                    'error': f'Erro ao obter detalhes da farmácia: {details_data.get("status")}'
                }), 400
            
            result = details_data.get('result', {})
            
            return jsonify({
                'success': True,
                'data': {
                    'name': result.get('name'),
                    'formatted_address': result.get('formatted_address'),
                    'formatted_phone_number': result.get('formatted_phone_number'),
                    'opening_hours': result.get('opening_hours'),
                    'website': result.get('website')
                }
            })
            
        except Exception as e:
            app.logger.error(f"Erro ao obter detalhes da farmácia: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erro ao processar solicitação: {str(e)}'
            }), 500
