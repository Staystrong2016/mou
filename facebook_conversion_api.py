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
    Obtém os parâmetros UTM da sessão ou da URL com múltiplas estratégias de fallback
    para garantir máxima preservação de dados de atribuição
    """
    utm_params = {}
    utm_keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
                'fbclid', 'gclid', 'ttclid']  # Incluir parâmetros de click ID também
    
    # 1. Estratégia: verificar o objeto utm_params na sessão (forma preferida)
    if 'utm_params' in session and isinstance(session.get('utm_params'), dict):
        session_utm_params = session.get('utm_params', {})
        logger.debug(f"UTM params encontrados na sessão (objeto): {session_utm_params}")
        for key in utm_keys:
            if key in session_utm_params and session_utm_params[key]:
                utm_params[key] = session_utm_params[key]
                logger.debug(f"UTM param {key} obtido do objeto utm_params na sessão: {utm_params[key]}")
    
    # 2. Estratégia: verificar parâmetros UTM armazenados individualmente na sessão
    for key in utm_keys:
        # Se já temos o valor da estratégia anterior, pular
        if key in utm_params and utm_params[key]:
            continue
            
        if key in session and session[key]:
            utm_params[key] = session[key]
            logger.debug(f"UTM param {key} encontrado individualmente na sessão: {utm_params[key]}")
    
    # 3. Estratégia: verificar na URL atual
    if request.args:
        for key in utm_keys:
            # Se já temos o valor das estratégias anteriores, pular
            if key in utm_params and utm_params[key]:
                continue
                
            if key in request.args and request.args.get(key):
                utm_params[key] = request.args.get(key)
                # Importante: salvar na sessão para uso futuro em outros eventos
                session[key] = request.args.get(key)
                logger.debug(f"UTM param {key} encontrado na URL e salvo na sessão: {utm_params[key]}")
    
    # 4. Estratégia: verificar no referer se disponível
    referer = request.headers.get('Referer')
    if referer and not utm_params:  # Só verificar referer se ainda não temos UTMs
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(referer)
            query_params = parse_qs(parsed_url.query)
            
            for key in utm_keys:
                # Se já temos o valor das estratégias anteriores, pular
                if key in utm_params and utm_params[key]:
                    continue
                    
                if key in query_params and query_params[key][0]:
                    utm_params[key] = query_params[key][0]
                    # Salvar na sessão para uso futuro
                    session[key] = utm_params[key]
                    logger.debug(f"UTM param {key} encontrado no referer URL e salvo na sessão: {utm_params[key]}")
        except Exception as e:
            logger.warning(f"Erro ao processar referer URL para UTMs: {str(e)}")
    
    # Log final para depuração
    if utm_params:
        logger.info(f"Parâmetros UTM capturados para evento: {utm_params}")
        # Salvar todo o conjunto de parâmetros na sessão para eventos futuros
        session['utm_params'] = utm_params
    else:
        logger.warning("Nenhum parâmetro UTM encontrado em sessão, URL ou referer")
    
    return utm_params

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
    # Criar função para emitir eventos de front-end para debugging
    def emit_debug_event(event_data, is_finished=False):
        """Emite um evento para o front-end para debugging"""
        if current_app and hasattr(current_app, 'jinja_env'):
            # Criar um script para emitir o evento no template
            script = """
            <script>
                (function() {
                    const eventDetail = %s;
                    const event = new CustomEvent('fb_conversion_api_event', { detail: eventDetail });
                    window.dispatchEvent(event);
                })();
            </script>
            """ % json.dumps(event_data)
            
            # Adicionar o script ao próximo template renderizado
            if not hasattr(current_app, '_fb_debug_scripts'):
                current_app._fb_debug_scripts = []
            
            # Se estamos finalizando o evento, marcar como finalizado
            event_data['finished'] = is_finished
            
            # Adicionar à lista de scripts para injeção
            current_app._fb_debug_scripts.append(script)
            logger.debug("Evento de debugging emitido para o front-end")
    
    # Tentar obter a URL atual da requisição se não fornecida
    if not event_source_url and request:
        event_source_url = request.url
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
        logger.debug(f"Cookie _fbp encontrado: {fb_cookies['fbp']}")
    else:
        logger.debug("Cookie _fbp não encontrado na requisição")
        
    if fb_cookies['fbc']:
        user_data['fbc'] = fb_cookies['fbc']
        logger.debug(f"Cookie _fbc encontrado: {fb_cookies['fbc']}")
    else:
        logger.debug("Cookie _fbc não encontrado na requisição")
    
    # Incluir IP e User-Agent para melhor matching
    user_data['client_ip_address'] = request.remote_addr or ""
    user_data['client_user_agent'] = request.user_agent.string if request.user_agent else ""
    logger.debug(f"IP do cliente: {user_data['client_ip_address']}")
    logger.debug(f"User-Agent: {user_data['client_user_agent']}")
    
    # Se o evento for Purchase, garantir que custom_data tenha value e currency
    if event_name == 'Purchase' and not custom_data:
        custom_data = {'value': 0, 'currency': 'BRL'}
        logger.debug("Dados customizados padrão adicionados para evento Purchase")
    
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
        logger.info(f"[UTM] Parâmetros UTM encontrados para evento {event_name}: {utm_params}")
        if not event_data.get('custom_data'):
            event_data['custom_data'] = {}
        event_data['custom_data'].update(utm_params)
    else:
        logger.info(f"[UTM] Nenhum parâmetro UTM encontrado para evento {event_name}")
    
    # Preparar payload completo para a API
    payload = {
        'data': [event_data],
        'access_token': FB_ACCESS_TOKEN
    }
    
    # Endpoint específico para o pixel
    endpoint = f"{FB_GRAPH_API_URL}/{pixel_id}/events"
    
    logger.info(f"📤 Enviando evento {event_name} para Pixel {pixel_id} com ID {event_id}")
    
    # Log detalhado dos dados do evento (com redação de dados sensíveis)
    safe_payload = json.loads(json.dumps(payload))
    if 'access_token' in safe_payload:
        safe_payload['access_token'] = '***REDACTED***'
    
    # Redação de dados pessoais para logging
    if 'user_data' in safe_payload.get('data', [{}])[0]:
        user_data_log = safe_payload['data'][0]['user_data']
        for field in ['email', 'phone', 'external_id']:
            if field in user_data_log:
                user_data_log[field] = f"***{field}_REDACTED***"
    
    logger.debug(f"Payload detalhado: {json.dumps(safe_payload, indent=2)}")
    
    # Verificar dados específicos de rastreamento
    if 'custom_data' in event_data:
        utm_fields = [k for k in event_data['custom_data'].keys() if k.startswith('utm_') or k.endswith('clid')]
        if utm_fields:
            logger.info(f"[UTM] Campos de rastreamento incluídos no evento: {utm_fields}")
    
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
                logger.info(f"Resposta: {json.dumps(response_data, indent=2)}")
                
                # Verificar se o evento foi recebido corretamente
                if 'events_received' in response_data and response_data['events_received'] > 0:
                    logger.info(f"✅ Facebook confirmou recebimento de {response_data['events_received']} evento(s)")
                    # Registrar ID de rastreamento do Facebook para depuração
                    if 'fbtrace_id' in response_data:
                        logger.info(f"Facebook Trace ID: {response_data['fbtrace_id']}")
                else:
                    logger.warning(f"⚠️ Evento enviado, mas Facebook não confirmou recebimento: {response_data}")
                
                success = True
                break
            elif response.status_code == 429:  # Rate limit
                retry_count += 1
                wait_time = RETRY_BACKOFF_FACTOR ** retry_count
                logger.warning(f"⚠️ Rate limit atingido. Aguardando {wait_time}s antes de tentar novamente.")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ Erro ao enviar evento. Status: {response.status_code}, Resposta: {response.text}")
                # Log de detalhes específicos de erros
                if response_data and 'error' in response_data:
                    error_details = response_data['error']
                    logger.error(f"Detalhes do erro: Código {error_details.get('code')}, Tipo: {error_details.get('type')}")
                    logger.error(f"Mensagem de erro: {error_details.get('message')}")
                break
                
        except Exception as e:
            logger.error(f"❌ Exceção ao enviar evento: {str(e)}")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_BACKOFF_FACTOR ** retry_count
                logger.warning(f"Aguardando {wait_time}s antes de tentar novamente.")
                time.sleep(wait_time)
    
    # Resultado final do envio do evento
    result = {}
    if success:
        result = {
            'success': True,
            'message': f'Evento {event_name} enviado com sucesso',
            'response': response_data,
            'eventName': event_name,
            'eventId': event_id,
            'eventSourceUrl': event_source_url or request.url if request else '',
            'pixelId': pixel_id
        }
        
        # Adicionar dados extras para facilitar debug
        if utm_params:
            result['utm_params'] = utm_params
        
        # Adicionar dados customizados (se houver)
        if custom_data:
            result['customData'] = custom_data
    else:
        result = {
            'success': False,
            'message': f'Falha ao enviar evento {event_name} após {retry_count} tentativas',
            'response': response_data,
            'eventName': event_name,
            'eventId': event_id,
            'eventSourceUrl': event_source_url or request.url if request else '',
            'pixelId': pixel_id
        }
    
    # Registrar resultado final em log
    log_level = logging.INFO if success else logging.ERROR
    logger.log(log_level, f"Resultado final do envio do evento {event_name}: {result['message']}")
    
    # Emitir evento de depuração para o front-end
    try:
        # Criar versão segura para debugging que remove dados sensíveis
        debug_result = result.copy()
        if 'response' in debug_result and debug_result['response'] and 'access_token' in debug_result['response']:
            if isinstance(debug_result['response'], dict):
                debug_result['response']['access_token'] = '***REDACTED***'
        
        # Adicionar os UTM params separadamente para clareza na UI
        debug_result['utmParams'] = utm_params
        
        # Emitir o evento final para o front-end
        emit_debug_event(debug_result, is_finished=True)
    except Exception as debug_error:
        logger.error(f"Erro ao emitir evento de debugging: {str(debug_error)}")
    
    return result

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
    content_name: Optional[str] = None,
    user_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Envia um evento Purchase para todos os pixels
    
    Args:
        value: Valor da compra
        transaction_id: ID da transação
        content_name: Nome do produto/conteúdo
        user_data: Dados do usuário para enriquecimento do evento
    """
    # Log inicial do evento Purchase
    logger.info(f"[FACEBOOK] Iniciando rastreamento de evento Purchase: valor={value}, ID={transaction_id}")
    
    # Construir dados da compra
    custom_data = {
        'value': value,
        'currency': 'BRL'
    }
    
    if transaction_id:
        custom_data['transaction_id'] = transaction_id
    
    if content_name:
        custom_data['content_name'] = content_name
    
    # Garantir que temos todos os parâmetros UTM possíveis - Verifica sessão, URL e referrer
    try:
        # Extrair parâmetros UTM de todas as fontes possíveis
        utm_params = get_utm_parameters()
        
        # Verificar request.args diretamente aqui para capturar parâmetros UTM da URL atual
        # que podem não ter sido capturados anteriormente
        if hasattr(request, 'args') and request.args:
            utm_keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid', 'gclid', 'ttclid']
            
            for key in utm_keys:
                if key in request.args and request.args.get(key):
                    utm_value = request.args.get(key)
                    
                    # Atualizar utm_params e a sessão
                    if not utm_params:
                        utm_params = {}
                    utm_params[key] = utm_value
                    
                    # Armazenar na sessão para uso futuro
                    session[key] = utm_value
                    logger.debug(f"[FACEBOOK-PURCHASE] UTM param capturado diretamente da URL atual: {key}={utm_value}")
            
            # Se capturamos novos parâmetros UTM, atualizar a sessão
            if utm_params:
                session['utm_params'] = utm_params
                logger.info(f"[FACEBOOK-PURCHASE] Parâmetros UTM atualizados na sessão: {utm_params}")
        
        # Registrar no log detalhes sobre os parâmetros UTM encontrados
        if utm_params:
            utm_keys = [k for k in utm_params.keys() if k.startswith('utm_') or k.endswith('clid')]
            logger.info(f"✅ [UTM] Parâmetros UTM incluídos no evento Purchase: {utm_keys}")
            
            # Incluir os parâmetros UTM nos custom_data (eles serão automaticamente mesclados na função send_event)
            for key, value in utm_params.items():
                # Garantir que não sobrescrevemos campos essenciais com valores incompatíveis
                if key not in ['value', 'currency', 'transaction_id']:
                    custom_data[key] = value
        else:
            logger.warning("⚠️ [UTM] Nenhum parâmetro UTM encontrado para o evento Purchase")
    except Exception as e:
        logger.error(f"[FACEBOOK] Erro ao processar parâmetros UTM para evento Purchase: {str(e)}")
    
    # Verificar referência direta para debug
    try:
        referer = request.headers.get('Referer', 'Não disponível')
        url_atual = request.url if hasattr(request, 'url') else 'Não disponível'
        logger.info(f"[FACEBOOK-DEBUG] Referer: {referer}")
        logger.info(f"[FACEBOOK-DEBUG] URL atual: {url_atual}")
        if hasattr(request, 'args') and request.args:
            logger.info(f"[FACEBOOK-DEBUG] Query params: {dict(request.args)}")
    except Exception as e:
        logger.error(f"[FACEBOOK] Erro ao extrair informações de debug: {str(e)}")
    
    # Enviar o evento para todos os pixels configurados
    result = send_event_to_all_pixels(
        event_name='Purchase',
        custom_data=custom_data,
        user_data=user_data
    )
    
    logger.info(f"[FACEBOOK] Evento Purchase enviado com sucesso. Resultado: {result[0] if result else 'Sem resultado'}")
    return result

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