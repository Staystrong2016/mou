"""
Módulo para integração com a API de Conversão do Facebook (CAPI)
Implementa o rastreamento server-side de eventos para o Facebook
"""
import os
import json
import logging
import hashlib
import requests
import uuid
import time
import functools
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from flask import request, session, current_app

# Configuração de logging
logger = logging.getLogger('facebook_capi')
logger.setLevel(logging.INFO)

# Handler para console
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Constantes para a API
FB_API_VERSION = 'v18.0'  # Usar a versão mais recente
FB_GRAPH_API_URL = f"https://graph.facebook.com/{FB_API_VERSION}"

# Pixel ID obtido de variável de ambiente
FB_PIXEL_ID = os.environ.get('FB_PIXEL_ID')

# Token de acesso do Facebook via variável de ambiente
FB_ACCESS_TOKEN = os.environ.get('FB_ACCESS_TOKEN')

# Log das configurações carregadas
if FB_PIXEL_ID:
    logger.info(f"Facebook Pixel ID configurado: {FB_PIXEL_ID}")
else:
    logger.warning("Facebook Pixel ID não encontrado nas variáveis de ambiente. Use FB_PIXEL_ID para configurar.")

if FB_ACCESS_TOKEN:
    logger.info("Facebook Access Token configurado com sucesso")
else:
    logger.warning("Facebook Access Token não encontrado nas variáveis de ambiente. Use FB_ACCESS_TOKEN para configurar.")

# Configurações para retentativas
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2  # Fator para backoff exponencial

def hash_data(data: str) -> str:
    """
    Aplica hash SHA-256 em dados pessoais para conformidade com GDPR/LGPD
    """
    if not data:
        return ""
    
    # Normalizar e limpar os dados
    normalized = str(data).strip().lower()
    
    # Aplicar hash SHA-256
    return hashlib.sha256(normalized.encode()).hexdigest()

def get_fbp_fbc_cookies() -> Dict[str, str]:
    """
    Obtém os cookies _fbp e _fbc do navegador para deduplicação
    """
    fbp = request.cookies.get('_fbp', '')
    fbc = request.cookies.get('_fbc', '')
    
    return {
        'fbp': fbp,
        'fbc': fbc
    }

def get_utm_parameters() -> Dict[str, str]:
    """
    Obtém os parâmetros UTM da sessão ou da URL
    """
    # Prioridade para parâmetros da sessão
    utm_params = {
        'utm_source': session.get('utm_source'),
        'utm_campaign': session.get('utm_campaign'),
        'utm_medium': session.get('utm_medium'),
        'utm_content': session.get('utm_content'),
        'utm_term': session.get('utm_term'),
    }
    
    # Se não estiver na sessão, verificar na URL
    if request.args:
        for param in utm_params:
            if not utm_params[param] and param in request.args:
                utm_params[param] = request.args.get(param)
    
    # Remover valores None
    return {k: v for k, v in utm_params.items() if v}

def generate_event_id() -> str:
    """
    Gera um ID de evento único para evitar duplicação
    Usa UUID v4 para garantir unicidade
    """
    return str(uuid.uuid4())

def send_event(
    pixel_id: str,
    event_name: str,
    event_id: Optional[str] = None,
    user_data: Optional[Dict[str, Any]] = None,
    custom_data: Optional[Dict[str, Any]] = None,
    event_source_url: Optional[str] = None,
    event_time: Optional[int] = None
) -> Dict[str, Any]:
    """
    Envia um evento para a API de Conversão do Facebook
    
    Args:
        pixel_id: ID do pixel do Facebook
        event_name: Nome do evento (PageView, Lead, Purchase, etc)
        event_id: ID único para o evento (para deduplicação) - gerado automaticamente se não fornecido
        user_data: Dados do usuário (email, phone, etc)
        custom_data: Dados customizados do evento (value, currency, etc)
        event_source_url: URL onde o evento aconteceu
        event_time: Timestamp do evento em segundos desde a época UNIX
    
    Returns:
        Dict contendo sucesso/falha e mensagem
    """
    if not FB_ACCESS_TOKEN:
        logger.warning("Token de acesso do Facebook não configurado. O evento não será enviado.")
        return {
            'success': False,
            'message': 'Token de acesso do Facebook não configurado'
        }
    
    # Gerar ID do evento se não fornecido
    if not event_id:
        event_id = generate_event_id()
    
    # Obter dados do usuário se não fornecidos
    if not user_data:
        user_data = {}
    
    # Incluir cookies _fbp e _fbc
    fb_cookies = get_fbp_fbc_cookies()
    if fb_cookies['fbp']:
        user_data['fbp'] = fb_cookies['fbp']
    if fb_cookies['fbc']:
        user_data['fbc'] = fb_cookies['fbc']
    
    # Incluir IP e User-Agent para melhor matching
    user_data['client_ip_address'] = request.remote_addr or ""
    user_data['client_user_agent'] = request.user_agent.string if request.user_agent else ""
    
    # Se o evento for Purchase, garantir que custom_data tenha value e currency
    if event_name == 'Purchase' and not custom_data:
        custom_data = {'value': 0, 'currency': 'BRL'}
    
    # Preparar payload do evento
    event_data = {
        'event_name': event_name,
        'event_time': event_time or int(datetime.now().timestamp()),
        'event_id': event_id,
        'event_source_url': event_source_url or request.url,
        'action_source': 'website',
        'user_data': user_data
    }
    
    # Incluir custom_data se fornecido
    if custom_data:
        event_data['custom_data'] = custom_data
    
    # Incluir parâmetros UTM como dados customizados de evento
    utm_params = get_utm_parameters()
    if utm_params:
        if not event_data.get('custom_data'):
            event_data['custom_data'] = {}
        event_data['custom_data'].update(utm_params)
    
    # Preparar payload completo para a API
    payload = {
        'data': [event_data],
        'access_token': FB_ACCESS_TOKEN
    }
    
    # Endpoint específico para o pixel
    endpoint = f"{FB_GRAPH_API_URL}/{pixel_id}/events"
    
    logger.info(f"📤 Enviando evento {event_name} para Pixel {pixel_id} com ID {event_id}")
    logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
    
    # Implementar retentativas com backoff exponencial
    success = False
    response_data = None
    retry_count = 0
    
    while not success and retry_count < MAX_RETRIES:
        try:
            if retry_count > 0:
                logger.info(f"Tentativa {retry_count + 1} de {MAX_RETRIES} para enviar evento {event_id}")
            
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            response_data = response.json()
            
            if response.status_code == 200:
                logger.info(f"✅ Evento {event_name} enviado com sucesso para Pixel {pixel_id}")
                logger.debug(f"Resposta: {json.dumps(response_data, indent=2)}")
                success = True
                break
            elif response.status_code == 429:  # Rate limit
                retry_count += 1
                wait_time = RETRY_BACKOFF_FACTOR ** retry_count
                logger.warning(f"⚠️ Rate limit atingido. Aguardando {wait_time}s antes de tentar novamente.")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ Erro ao enviar evento. Status: {response.status_code}, Resposta: {response.text}")
                break
                
        except Exception as e:
            logger.error(f"❌ Exceção ao enviar evento: {str(e)}")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_BACKOFF_FACTOR ** retry_count
                logger.warning(f"Aguardando {wait_time}s antes de tentar novamente.")
                time.sleep(wait_time)
    
    if success:
        return {
            'success': True,
            'message': f'Evento {event_name} enviado com sucesso',
            'data': response_data
        }
    else:
        return {
            'success': False,
            'message': f'Falha ao enviar evento {event_name} após {retry_count} tentativas',
            'data': response_data
        }

def send_event_to_all_pixels(
    event_name: str,
    user_data: Optional[Dict[str, Any]] = None,
    custom_data: Optional[Dict[str, Any]] = None,
    event_source_url: Optional[str] = None,
    event_time: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Envia um evento para o Pixel configurado na variável de ambiente FB_PIXEL_ID
    
    Args:
        event_name: Nome do evento (PageView, Lead, Purchase, etc)
        user_data: Dados do usuário
        custom_data: Dados customizados do evento
        event_source_url: URL onde o evento aconteceu
        event_time: Timestamp do evento
    
    Returns:
        Lista com os resultados do envio
    """
    results = []
    event_id = generate_event_id()  
    
    # Verificar se o Pixel ID está configurado
    if not FB_PIXEL_ID:
        logger.warning(f"Não foi possível enviar evento {event_name}: FB_PIXEL_ID não configurado")
        return [{
            'success': False,
            'message': 'FB_PIXEL_ID não configurado'
        }]
    
    # Enviar evento para o Pixel ID configurado
    result = send_event(
        pixel_id=FB_PIXEL_ID,
        event_name=event_name,
        event_id=event_id,
        user_data=user_data,
        custom_data=custom_data,
        event_source_url=event_source_url,
        event_time=event_time
    )
    results.append(result)
    
    return results

def prepare_user_data(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    gender: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    country: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Prepara os dados do usuário, aplicando hash onde necessário
    
    Args:
        email: Email do usuário
        phone: Telefone do usuário
        first_name, last_name: Nome e sobrenome
        gender: Gênero
        city, state, zip_code, country: Localização
        external_id: ID externo (como ID de cliente)
    
    Returns:
        Dict com os dados formatados para a API
    """
    user_data = {}
    
    # Aplicar hash em dados pessoais
    if email:
        user_data['em'] = hash_data(email)
    
    if phone:
        # Remover tudo exceto dígitos
        phone_clean = ''.join(c for c in phone if c.isdigit())
        user_data['ph'] = hash_data(phone_clean)
    
    if first_name:
        user_data['fn'] = hash_data(first_name)
    
    if last_name:
        user_data['ln'] = hash_data(last_name)
    
    if gender:
        user_data['ge'] = hash_data(gender)
    
    if city:
        user_data['ct'] = hash_data(city)
    
    if state:
        user_data['st'] = hash_data(state)
    
    if zip_code:
        user_data['zp'] = hash_data(zip_code)
    
    if country:
        user_data['country'] = country
    
    if external_id:
        user_data['external_id'] = hash_data(external_id)
    
    return user_data

# Funções específicas para cada tipo de evento conforme requisitos

def track_page_view(url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Envia um evento PageView para todos os pixels
    """
    return send_event_to_all_pixels(
        event_name='PageView',
        event_source_url=url
    )

def track_view_content(content_name: Optional[str] = None, content_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Envia um evento ViewContent para todos os pixels
    """
    custom_data = {}
    if content_name:
        custom_data['content_name'] = content_name
    if content_type:
        custom_data['content_type'] = content_type
    
    return send_event_to_all_pixels(
        event_name='ViewContent',
        custom_data=custom_data
    )

def track_lead(value: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Envia um evento Lead para todos os pixels
    """
    custom_data = {}
    if value is not None:
        custom_data['value'] = value
        custom_data['currency'] = 'BRL'
    
    return send_event_to_all_pixels(
        event_name='Lead',
        custom_data=custom_data
    )

def track_add_payment_info() -> List[Dict[str, Any]]:
    """
    Envia um evento AddPaymentInfo para todos os pixels
    """
    return send_event_to_all_pixels(
        event_name='AddPaymentInfo'
    )

def track_initiate_checkout(value: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Envia um evento InitiateCheckout para todos os pixels
    """
    custom_data = {}
    if value is not None:
        custom_data['value'] = value
        custom_data['currency'] = 'BRL'
    
    return send_event_to_all_pixels(
        event_name='InitiateCheckout',
        custom_data=custom_data
    )

def track_purchase(
    value: float,
    transaction_id: Optional[str] = None,
    content_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Envia um evento Purchase para todos os pixels
    
    Args:
        value: Valor da compra
        transaction_id: ID da transação
        content_name: Nome do produto/conteúdo
    """
    custom_data = {
        'value': value,
        'currency': 'BRL'
    }
    
    if transaction_id:
        custom_data['transaction_id'] = transaction_id
    
    if content_name:
        custom_data['content_name'] = content_name
    
    return send_event_to_all_pixels(
        event_name='Purchase',
        custom_data=custom_data
    )

# Middleware e função para registrar eventos automaticamente em rotas específicas
def route_event_handler(event_type: Optional[str] = None):
    """
    Decorador para lidar com eventos específicos em rotas
    
    Args:
        event_type: Tipo de evento a ser registrado ('PageView', 'Lead', etc.)
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Executar a rota normalmente
            response = f(*args, **kwargs)
            
            # Enviar evento após a execução da rota, se solicitado
            if event_type:
                try:
                    if event_type == 'PageView':
                        track_page_view()
                    elif event_type == 'ViewContent':
                        track_view_content()
                    elif event_type == 'Lead':
                        track_lead()
                    elif event_type == 'AddPaymentInfo':
                        track_add_payment_info()
                    elif event_type == 'InitiateCheckout':
                        track_initiate_checkout()
                    # Purchase requer value, então não é automático
                    
                    logger.info(f"Evento {event_type} registrado automaticamente para rota {request.path}")
                except Exception as e:
                    logger.error(f"Erro ao registrar evento {event_type}: {str(e)}")
            
            return response
        return decorated_function
    return decorator

def register_facebook_conversion_events(app):
    """
    Registra os manipuladores de eventos do Facebook para as rotas especificadas
    """
    import functools
    from flask import request, session
    
    # Verificar se as credenciais necessárias estão configuradas
    if not FB_PIXEL_ID or not FB_ACCESS_TOKEN:
        logger.warning("Facebook Conversion API não está completamente configurada. Eventos não serão registrados.")
        logger.warning("Configure FB_PIXEL_ID e FB_ACCESS_TOKEN nas variáveis de ambiente.")
        return
    
    logger.info(f"Registrando eventos de conversão do Facebook para Pixel ID: {FB_PIXEL_ID}")
    
    # Mapeamento de rotas para eventos
    route_event_mapping = {
        '/anvisa': 'PageView',
        '/cadastro': 'ViewContent',
        '/compra': 'AddPaymentInfo',
        '/pagamento_pix': 'InitiateCheckout',
    }
    
    # Adicionar o evento automaticamente para cada rota
    for route, event in route_event_mapping.items():
        # Registrar evento antes da resposta
        app.before_request_funcs.setdefault(None, []).append(
            lambda r=route, e=event: _check_route_and_track_event(r, e)
        )
    
    # Registrar evento de Lead para botão de prosseguir na rota /endereco
    # Isto precisará ser implementado no template com JavaScript
    # Também, o evento Purchase precisará ser chamado manualmente em /confirmacao_compra

def _check_route_and_track_event(route: str, event_type: str):
    """
    Verifica se a rota atual corresponde e registra o evento apropriado
    """
    if request.path == route:
        try:
            if event_type == 'PageView':
                track_page_view()
            elif event_type == 'ViewContent':
                track_view_content()
            elif event_type == 'Lead':
                # Lead específico para a rota /endereco - será acionado via JavaScript
                pass
            elif event_type == 'AddPaymentInfo':
                track_add_payment_info()
            elif event_type == 'InitiateCheckout':
                track_initiate_checkout()
            # Purchase requer value, será acionado manualmente
            
            logger.info(f"✅ Evento {event_type} registrado automaticamente para rota {route}")
        except Exception as e:
            logger.error(f"❌ Erro ao registrar evento {event_type} para rota {route}: {str(e)}")