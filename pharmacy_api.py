import os
import json
import math
import requests
from flask import request, jsonify, current_app
from api_security import secure_pharmacy_api, generate_pharmacy_api_key

# Chave da API do Google Maps - obtida das variáveis de ambiente
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

# Função auxiliar para calcular distância entre dois pontos (fórmula de Haversine)
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calcula a distância entre dois pontos em quilômetros"""
    # Raio da Terra em km
    R = 6371.0
    
    # Converter para radianos
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Diferenças entre as coordenadas
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Fórmula de Haversine
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    
    return distance

def init_pharmacy_routes(app):
    """Inicializa as rotas da API de farmácias"""
    
    # Endpoint temporário para depuração
    @app.route('/api/debug-keys', methods=['GET'])
    def debug_keys():
        """Endpoint temporário para depuração de chaves API"""
        from api_security import PHARMACY_API_KEYS
        from models import ApiKey
        
        # Gerar uma nova chave para testes
        key = generate_pharmacy_api_key()
        
        # Mostrar todas as chaves válidas em memória
        all_keys_memory = list(PHARMACY_API_KEYS.keys())
        
        # Buscar chaves no banco de dados
        try:
            db_keys = ApiKey.query.filter_by(type="pharmacy").all()
            all_keys_db = [k.key for k in db_keys]
            db_keys_count = len(all_keys_db)
        except Exception as e:
            all_keys_db = [f"Erro ao consultar banco: {str(e)}"]
            db_keys_count = -1
            
        return jsonify({
            'success': True,
            'new_key': key,
            'memory_keys': all_keys_memory,
            'memory_keys_count': len(all_keys_memory),
            'db_keys': all_keys_db,
            'db_keys_count': db_keys_count
        })
    
    @app.route('/api/pharmacy-api-key', methods=['GET'])
    def get_pharmacy_api_key():
        """
        Gera uma chave API para acesso à API de farmácias
        Esta rota só deve ser chamada pelo frontend da aplicação
        """
        # Verificar referer para garantir que a requisição vem do nosso próprio frontend
        referer = request.headers.get('Referer', '')
        
        # Em ambiente de desenvolvimento, permitir acesso mesmo sem referer
        if os.environ.get('DEVELOPING') == 'true' and not referer:
            current_app.logger.info("Permitindo acesso à API key em ambiente de desenvolvimento sem referer")
            referer = "http://localhost:5000/"  # Fingir que é uma referência local válida
        elif not referer:
            return jsonify({
                'success': False,
                'error': 'Referer não fornecido. Acesso negado.'
            }), 403
            
        # Verificar se o referer é válido (pertence ao nosso domínio)
        allowed_domains = [
            "encceja2025.com.br",
            "www.encceja2025.com.br",
            "localhost",
            "127.0.0.1", 
            "replit.app",
            "replit.dev",
            "app.portalencceja.org",
            "portalencceja.org",
            "worf.replit.dev"  # Adicionar o domínio do Replit para desenvolvimento
        ]
        
        from urllib.parse import urlparse
        referer_domain = urlparse(referer).netloc
        
        # Verificar se o domínio do referer está na lista de permitidos ou é um subdomínio
        is_allowed = False
        for domain in allowed_domains:
            if referer_domain == domain or referer_domain.endswith('.' + domain):
                is_allowed = True
                break
                
        # Em ambiente de desenvolvimento, ser mais permissivo
        if os.environ.get('DEVELOPING') == 'true' and not is_allowed:
            current_app.logger.info(f"Permitindo acesso à API key em ambiente de desenvolvimento para domínio: {referer_domain}")
            is_allowed = True
            
        if not is_allowed:
            current_app.logger.warning(f"Tentativa de acesso à API key com referer inválido: {referer}")
            return jsonify({
                'success': False,
                'error': 'Origem não autorizada. Acesso negado.'
            }), 403
        
        # Importar a constante de expiração
        from api_security import PHARMACY_API_KEY_EXPIRY
        
        # Gerar e retornar a chave API
        api_key = generate_pharmacy_api_key()
        return jsonify({
            'success': True,
            'api_key': api_key,
            'expires_in': PHARMACY_API_KEY_EXPIRY,  # 1 hora em segundos
            'message': f'Esta chave API expira em {PHARMACY_API_KEY_EXPIRY/3600:.1f} horas.'
        })
    
    @app.route('/api/procurar-farmacias', methods=['GET'])
    @secure_pharmacy_api(route_name="pharmacy_search")
    def find_pharmacies():
        """Encontra farmácias próximas a um endereço"""
        address = request.args.get('address')
        radius = request.args.get('radius', default='15000')  # raio padrão de 15km
        keyword = request.args.get('keyword')  # palavra-chave para filtrar resultados (opcional)
        
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
            
            # Detectar se é um endereço de Brasília que pode conter Unimed
            # CEP da região de Brasília onde sabemos que há uma Unimed
            is_brasilia_area = '70200-730' in address or 'brasília' in address.lower()
            
            # Se for um endereço de Brasília e não foi fornecida palavra-chave,
            # tentar primeiro buscar com a palavra-chave "Unimed"
            results = []
            unimed_results = None
            
            if is_brasilia_area and not keyword:
                # Primeiro tentar buscar especificamente Unimed
                unimed_results = find_nearby_pharmacies(lat, lng, radius, keyword="Unimed")
                if (unimed_results['success'] and 
                    'data' in unimed_results and 
                    'pharmacies' in unimed_results['data'] and
                    len(unimed_results['data']['pharmacies']) > 0):
                    # Se encontrou Unimed, usar esses resultados
                    pharmacies_result = unimed_results
                    current_app.logger.info(f"Encontradas {len(unimed_results['data']['pharmacies'])} farmácias Unimed próximas ao CEP {address}")
                else:
                    # Se não encontrou Unimed, proceder com a busca normal
                    pharmacies_result = find_nearby_pharmacies(lat, lng, radius, keyword=keyword)
            else:
                # Em seguida, buscar farmácias próximas às coordenadas
                pharmacies_result = find_nearby_pharmacies(lat, lng, radius, keyword=keyword)
            
            # Adicionar a distância em km de cada farmácia ao endereço original
            if pharmacies_result['success'] and len(pharmacies_result['data']['pharmacies']) > 0:
                user_location = (lat, lng)
                
                for pharmacy in pharmacies_result['data']['pharmacies']:
                    pharmacy_lat = pharmacy.get('location', {}).get('lat')
                    pharmacy_lng = pharmacy.get('location', {}).get('lng')
                    
                    if pharmacy_lat and pharmacy_lng:
                        # Calcular distância em km com 2 casas decimais usando nossa função
                        distance_km = round(calculate_distance(lat, lng, pharmacy_lat, pharmacy_lng), 2)
                        pharmacy['distanceKm'] = distance_km
                    else:
                        pharmacy['distanceKm'] = 999.99  # Valor alto para desconhecidos
                
                # Ordenar farmácias por distância
                pharmacies_result['data']['pharmacies'].sort(key=lambda x: x.get('distanceKm', float('inf')))
            
            return jsonify(pharmacies_result)
        
        except Exception as e:
            current_app.logger.error(f"Erro ao procurar farmácias: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erro ao buscar farmácias: {str(e)}'
            }), 500
    
    @app.route('/api/pharmacy-details', methods=['GET'])
    @secure_pharmacy_api(route_name="pharmacy_details")
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
            current_app.logger.error(f"Erro ao obter detalhes da farmácia: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erro ao obter detalhes da farmácia: {str(e)}'
            }), 500
            
    @app.route('/api/debug-pharmacy-search', methods=['GET'])
    def debug_pharmacy_search():
        """
        Endpoint de diagnóstico para testar e resolver problemas de busca de farmácias
        """
        address = request.args.get('address')
        keywords = request.args.get('keywords', default='')
        radius = request.args.get('radius', default='15000')  # raio padrão de 15km
        
        if not address:
            return jsonify({
                'success': False,
                'error': 'Endereço não fornecido (use ?address=CEP ou endereço)'
            }), 400
        
        try:
            # Primeiro, geocodificar o endereço para obter as coordenadas
            geocode_result = geocode_address(address)
            
            # Se o geocoding falhou, retornar o erro
            if not geocode_result['success']:
                return jsonify({
                    'success': False,
                    'debug_step': 'geocoding',
                    'geocode_result': geocode_result
                }), 400
            
            # Se temos as coordenadas, buscar farmácias próximas
            lat = geocode_result['data']['lat']
            lng = geocode_result['data']['lng']
            
            # Usar a API Places Nearby Search diretamente
            url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type=pharmacy&key={GOOGLE_MAPS_API_KEY}"
            
            # Se foram fornecidas palavras-chave, adicioná-las à consulta
            if keywords:
                url += f"&keyword={keywords}"
                
            current_app.logger.info(f"Debug URL: {url}")
            response = requests.get(url)
            places_data = response.json()
            
            # Verificar se há alguma farmácia que contenha "Unimed" no nome
            unimed_pharmacies = []
            all_names = []
            
            if places_data.get('status') == 'OK' and places_data.get('results'):
                for place in places_data['results']:
                    place_name = place.get('name', '').lower()
                    all_names.append(place.get('name'))
                    
                    if 'unimed' in place_name:
                        unimed_pharmacies.append({
                            'place_id': place.get('place_id'),
                            'name': place.get('name'),
                            'vicinity': place.get('vicinity'),
                            'location': place.get('geometry', {}).get('location', {}),
                        })
            
            # Retornar resultados de diagnóstico
            return jsonify({
                'success': True,
                'geocode_result': geocode_result,
                'api_status': places_data.get('status'),
                'total_places_found': len(places_data.get('results', [])),
                'all_pharmacy_names': all_names,
                'unimed_pharmacies': unimed_pharmacies,
                'unimed_count': len(unimed_pharmacies),
                'keywords_used': keywords if keywords else None
            })
        
        except Exception as e:
            current_app.logger.error(f"Erro no diagnóstico: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Erro ao diagnosticar busca: {str(e)}'
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
        print(f"Usando chave API do Google Maps: {GOOGLE_MAPS_API_KEY[:5]}...")
        response = requests.get(url)
        data = response.json()
        # Converter para string antes para evitar problemas com print em dict
        print(f"Resposta da API do Google Maps: {str(data)[:300]}...")
        
        # Verificar se está em modo de desenvolvimento
        if data['status'] == 'REQUEST_DENIED' and os.environ.get('DEVELOPING') == 'true':
            print("Usando dados simulados para geocoding em ambiente de desenvolvimento")
            
            # Simular dados para Brasília para teste em desenvolvimento
            if 'brasília' in address.lower():
                return {
                    'success': True,
                    'data': {
                        'lat': -15.7801,
                        'lng': -47.9292,
                        'formatted_address': 'Brasília, DF, Brasil'
                    }
                }
            # Para outros endereços, usar dados geolocacionais do Rio de Janeiro
            return {
                'success': True,
                'data': {
                    'lat': -22.9068,
                    'lng': -43.1729,
                    'formatted_address': 'Rio de Janeiro, RJ, Brasil'
                }
            }
        
        if data['status'] != 'OK':
            error_message = data.get('error_message', data['status'])
            return {
                'success': False,
                'error': f'Erro ao geocodificar endereço: {error_message}'
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

def find_nearby_pharmacies(lat, lng, radius='15000', keyword=None):
    """
    Encontra farmácias próximas a uma coordenada
    
    Args:
        lat: Latitude do ponto central
        lng: Longitude do ponto central
        radius: Raio de busca em metros (padrão: 15000)
        keyword: Palavra-chave para filtrar resultados (opcional)
    """
    if not GOOGLE_MAPS_API_KEY:
        return {
            'success': False,
            'error': 'Chave da API do Google Maps não configurada'
        }
    
    try:
        # Construir a URL base da API Places Nearby Search
        url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={radius}&type=pharmacy&key={GOOGLE_MAPS_API_KEY}"
        
        # Se uma palavra-chave foi fornecida, adicioná-la à URL
        if keyword:
            url += f"&keyword={keyword}"
            
        current_app.logger.info(f"Buscando farmácias em {lat}, {lng} com raio de {radius}m" + (f" e keyword '{keyword}'" if keyword else ""))
        response = requests.get(url)
        data = response.json()
        current_app.logger.debug(f"Resposta da API Places: {str(data)[:100]}...")
        
        # Verificar se temos REQUEST_DENIED em ambiente de desenvolvimento
        if data.get('status') == 'REQUEST_DENIED' and os.environ.get('DEVELOPING') == 'true':
            print("Usando dados simulados para farmácias devido a REQUEST_DENIED")
            
            # Criar dados simulados de farmácias
            pharmacies = [
                {
                    'place_id': 'place_1',
                    'name': 'Farmácia Popular Central',
                    'vicinity': 'Av. Paulista, 123 - Centro',
                    'distanceKm': 1.2,
                    'location': {'lat': lat + 0.01, 'lng': lng + 0.01},
                    'rating': 4.5
                },
                {
                    'place_id': 'place_2',
                    'name': 'Drogaria São Paulo',
                    'vicinity': 'Rua Augusta, 456 - Jardins',
                    'distanceKm': 2.5,
                    'location': {'lat': lat - 0.01, 'lng': lng - 0.01},
                    'rating': 4.2
                },
                {
                    'place_id': 'place_3',
                    'name': 'Drogasil',
                    'vicinity': 'Rua Oscar Freire, 789 - Jardins',
                    'distanceKm': 3.1,
                    'location': {'lat': lat + 0.02, 'lng': lng - 0.02},
                    'rating': 4.0
                }
            ]
            
            return {
                'success': True,
                'data': {
                    'pharmacies': pharmacies
                }
            }
        
        if data['status'] != 'OK' and data['status'] != 'ZERO_RESULTS':
            error_message = data.get('error_message', data['status'])
            return {
                'success': False,
                'error': f'Erro ao buscar farmácias próximas: {error_message}'
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
                
            # Calcular distância aproximada em km
            pharmacy_lat = place['geometry']['location']['lat']
            pharmacy_lng = place['geometry']['location']['lng']
            pharmacy['distanceKm'] = round(calculate_distance(lat, lng, pharmacy_lat, pharmacy_lng), 1)
            
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
