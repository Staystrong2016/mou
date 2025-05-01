import os
import json
import requests
from flask import request, jsonify
from geopy.distance import geodesic

# Chave da API do Google Maps - obtida das variáveis de ambiente
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

def init_pharmacy_routes(app):
    """Inicializa as rotas da API de farmácias"""
    
    @app.route('/api/find-pharmacies', methods=['GET'])
    def find_pharmacies():
        """Encontra farmácias próximas a um endereço"""
        address = request.args.get('address')
        radius = request.args.get('radius', default='15000')  # raio padrão de 15km
        
        if not address:
            return jsonify({
                'success': False,
                'error': 'Endereço não fornecido'
            }), 400
        
        try:
            # Primeiro, geocodificar o endereço para obter as coordenadas
            geocode_result = geocode_address(address)
            if not geocode_result['success']:
                return jsonify(geocode_result), 400
            
            lat = geocode_result['data']['lat']
            lng = geocode_result['data']['lng']
            
            # Em seguida, buscar farmácias próximas às coordenadas
            pharmacies_result = find_nearby_pharmacies(lat, lng, radius)
            
            # Adicionar a distância em km de cada farmácia ao endereço original
            if pharmacies_result['success'] and len(pharmacies_result['data']['pharmacies']) > 0:
                user_location = (lat, lng)
                
                for pharmacy in pharmacies_result['data']['pharmacies']:
                    pharmacy_location = (pharmacy.get('geometry', {}).get('location', {}).get('lat'), 
                                       pharmacy.get('geometry', {}).get('location', {}).get('lng'))
                    
                    # Calcular distância em km com 2 casas decimais
                    distance_km = round(geodesic(user_location, pharmacy_location).kilometers, 2)
                    pharmacy['distanceKm'] = distance_km
                
                # Ordenar farmácias por distância
                pharmacies_result['data']['pharmacies'].sort(key=lambda x: x.get('distanceKm', float('inf')))
            
            return jsonify(pharmacies_result)
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Erro ao buscar farmácias: {str(e)}'
            }), 500
    
    @app.route('/api/pharmacy-details', methods=['GET'])
    def pharmacy_details():
        """Obter detalhes de uma farmácia específica"""
        place_id = request.args.get('place_id')
        
        if not place_id:
            return jsonify({
                'success': False,
                'error': 'ID da farmácia não fornecido'
            }), 400
        
        try:
            # Buscar detalhes da farmácia pelo ID do local
            details_result = get_pharmacy_details(place_id)
            return jsonify(details_result)
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Erro ao obter detalhes da farmácia: {str(e)}'
            }), 500


def geocode_address(address):
    """Converte um endereço em coordenadas geográficas usando a API do Google Maps"""
    if not GOOGLE_MAPS_API_KEY:
        return {
            'success': False,
            'error': 'Chave da API do Google Maps não configurada'
        }
    
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_MAPS_API_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if data['status'] != 'OK':
            return {
                'success': False,
                'error': f'Erro ao geocodificar endereço: {data["status"]}'
            }
        
        # Extrair coordenadas da resposta
        location = data['results'][0]['geometry']['location']
        lat = location['lat']
        lng = location['lng']
        
        return {
            'success': True,
            'data': {
                'lat': lat,
                'lng': lng,
                'formatted_address': data['results'][0]['formatted_address']
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Erro ao geocodificar endereço: {str(e)}'
        }

def find_nearby_pharmacies(lat, lng, radius='15000'):
    """Encontra farmácias próximas a uma coordenada"""
    if not GOOGLE_MAPS_API_KEY:
        return {
            'success': False,
            'error': 'Chave da API do Google Maps não configurada'
        }
    
    try:
        # Usar a API Places Nearby Search para encontrar farmácias
        url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type=pharmacy&key={GOOGLE_MAPS_API_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if data['status'] != 'OK' and data['status'] != 'ZERO_RESULTS':
            return {
                'success': False,
                'error': f'Erro ao buscar farmácias próximas: {data["status"]}'
            }
        
        # Se o status for ZERO_RESULTS, retornar uma lista vazia, mas com sucesso
        if data['status'] == 'ZERO_RESULTS':
            return {
                'success': True,
                'data': {
                    'pharmacies': []
                }
            }
        
        # Extrair informações relevantes das farmácias encontradas
        pharmacies = []
        for place in data['results']:
            pharmacy = {
                'place_id': place['place_id'],
                'name': place['name'],
                'vicinity': place['vicinity'],
                'location': place['geometry']['location'],
                'geometry': place['geometry']
            }
            
            # Adicionar foto se disponível
            if 'photos' in place and len(place['photos']) > 0:
                pharmacy['photo_reference'] = place['photos'][0]['photo_reference']
            
            # Adicionar classificação se disponível
            if 'rating' in place:
                pharmacy['rating'] = place['rating']
            
            pharmacies.append(pharmacy)
        
        return {
            'success': True,
            'data': {
                'pharmacies': pharmacies
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Erro ao buscar farmácias próximas: {str(e)}'
        }

def get_pharmacy_details(place_id):
    """Obter detalhes de uma farmácia específica pelo ID do lugar"""
    if not GOOGLE_MAPS_API_KEY:
        return {
            'success': False,
            'error': 'Chave da API do Google Maps não configurada'
        }
    
    try:
        # Usar a API Places Details para obter informações detalhadas
        url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address,formatted_phone_number,opening_hours,geometry,rating,website,photos&key={GOOGLE_MAPS_API_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if data['status'] != 'OK':
            return {
                'success': False,
                'error': f'Erro ao obter detalhes da farmácia: {data["status"]}'
            }
        
        # Extrair informações detalhadas
        result = data['result']
        details = {
            'place_id': place_id,
            'name': result.get('name', ''),
            'address': result.get('formatted_address', ''),
            'phone': result.get('formatted_phone_number', ''),
            'location': result.get('geometry', {}).get('location', {}),
            'rating': result.get('rating', 0),
            'website': result.get('website', '')
        }
        
        # Adicionar horário de funcionamento se disponível
        if 'opening_hours' in result and 'weekday_text' in result['opening_hours']:
            details['opening_hours'] = result['opening_hours']['weekday_text']
        
        # Adicionar URL da foto se disponível
        if 'photos' in result and len(result['photos']) > 0:
            photo_reference = result['photos'][0]['photo_reference']
            details['photo_url'] = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={GOOGLE_MAPS_API_KEY}"
        
        return {
            'success': True,
            'data': details
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Erro ao obter detalhes da farmácia: {str(e)}'
        }
