import os
import time
import jwt
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, Optional, Tuple, List, Set
from urllib.parse import urlparse
import re

from flask import request, g, current_app, jsonify, abort

# Lista de tokens CSRF válidos com tempo de expiração
# Formato: {token: expiration_timestamp}
CSRF_TOKENS = {}

# Limites de taxa por rota e por IP
# Formato: {ip: {route: {count: int, last_request: timestamp}}}
RATE_LIMITS = {}

# Configurações de segurança
JWT_SECRET = os.environ.get("JWT_SECRET", "secure_random_key_should_be_replaced")  # Deve ser alterado em produção
CSRF_TOKEN_EXPIRY = 3600  # 1 hora em segundos
RATE_LIMIT_WINDOW = 60  # Janela de limite de taxa em segundos
RATE_LIMIT_MAX_REQUESTS = {
    "default": 60,  # 60 requisições por minuto
    "payment": 15,  # 15 requisições por minuto para rotas de pagamento
    "check_payment": 120,  # 120 requisições por minuto para verificação de status (aumentado)
    "check_for4payments_status": 200,  # 200 requisições por minuto para verificação específica de For4Payments
    "create_pix_payment": 20,  # 20 requisições por minuto para criação de pagamento PIX
    "pagar_frete": 20,  # 20 requisições por minuto para pagamento de frete
    "comprar_livro": 20,  # 20 requisições por minuto para compra de livro
    "csrf_token": 20,  # 20 requisições por minuto para geração de tokens CSRF
    "payment_token": 15  # 15 requisições por minuto para geração de tokens de pagamento
}

# Lista de domínios permitidos no header 'Referer'
ALLOWED_DOMAINS = [
    "encceja2025.com.br",
    "www.encceja2025.com.br",
    "localhost",
    "127.0.0.1",
    "replit.app",
    "replit.dev",
    "app.portalencceja.org",
    "portalencceja.org"
]

# Regex para detectar possíveis ataques de injeção
INJECTION_PATTERNS = [
    r"<script.*?>.*?</script>",
    r"javascript:",
    r"onload=",
    r"onerror=",
    r"onclick=",
    r"alert\(",
    r"eval\(",
    r"document\.cookie",
    r"\/etc\/passwd",
    r"\/bin\/bash",
    r"SELECT.*FROM",
    r"INSERT.*INTO",
    r"DELETE.*FROM",
    r"DROP.*TABLE",
    r"1=1",
    r"OR 1=1"
]

def generate_csrf_token() -> str:
    """Gera um token anti-CSRF único"""
    token = str(uuid.uuid4())
    expiry = time.time() + CSRF_TOKEN_EXPIRY
    CSRF_TOKENS[token] = expiry
    return token

def clean_expired_csrf_tokens() -> None:
    """Remove tokens CSRF expirados"""
    now = time.time()
    expired_tokens = [token for token, expiry in CSRF_TOKENS.items() if expiry < now]
    for token in expired_tokens:
        CSRF_TOKENS.pop(token, None)

def create_jwt_token(data: Dict[str, Any]) -> str:
    """
    Cria um token JWT para autenticação interna
    """
    payload = {
        'data': data,
        'exp': datetime.utcnow() + timedelta(minutes=30),  # Token expira em 30 minutos
        'iat': datetime.utcnow(),
        'jti': str(uuid.uuid4())  # ID único para este token
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_jwt_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Verifica um token JWT e retorna o payload se válido
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return True, payload.get('data', {})
    except jwt.ExpiredSignatureError:
        current_app.logger.warning("Token JWT expirado")
        return False, None
    except jwt.InvalidTokenError as e:
        current_app.logger.warning(f"Token JWT inválido: {str(e)}")
        return False, None

def get_client_fingerprint() -> str:
    """
    Cria uma impressão digital do cliente combinando diversos fatores
    para identificar clientes mesmo que usem diferentes IPs/proxies
    """
    # Obter os headers mais distintivos
    user_agent = request.headers.get('User-Agent', '')
    accept_lang = request.headers.get('Accept-Language', '')
    accept_encoding = request.headers.get('Accept-Encoding', '')
    
    # Coletar todos os headers potencialmente relacionados a proxies
    forwarded = request.headers.get('Forwarded', '')
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    x_forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
    x_forwarded_host = request.headers.get('X-Forwarded-Host', '')
    via = request.headers.get('Via', '')
    
    # Obter o IP real do cliente considerando possíveis proxies
    ip = request.remote_addr
    possible_ips = []
    
    # Tentar extrair IPs de vários headers
    if x_forwarded_for:
        possible_ips.extend([ip.strip() for ip in x_forwarded_for.split(',')])
        
    if forwarded:
        # Extrair IPs do header Forwarded (formato mais complexo)
        for part in forwarded.split(';'):
            if '=' in part and part.lower().startswith('for='):
                ip_part = part.split('=')[1].strip().strip('"[]')
                if ':' in ip_part:  # IPv6
                    possible_ips.append(ip_part)
                else:
                    possible_ips.append(ip_part)
    
    # Coletar cookies ativos (outra forma de fingerprinting)
    cookies_str = "|".join(sorted(request.cookies.keys())) if request.cookies else ""
    
    # Detectar características de cliente que persistem através de proxies
    # Incluir o IP original e outros possíveis IPs encontrados
    fingerprint_parts = [
        # Headers básicos do navegador
        f"ua:{user_agent[:100]}",  # Limitar tamanho para evitar DoS
        f"lang:{accept_lang[:50]}",
        f"enc:{accept_encoding[:50]}",
        
        # Informações de proxy/encaminhamento
        f"via:{via[:50]}",
        f"fwd_host:{x_forwarded_host[:50]}",
        f"fwd_proto:{x_forwarded_proto[:20]}",
        
        # Cookies ativos (padrão de uso)
        f"cookies:{cookies_str[:100]}",
        
        # Incluir o IP original
        f"ip:{ip}"
    ]
    
    # Adicionar outros IPs detectados
    for idx, possible_ip in enumerate(possible_ips[:3]):  # Limitar a 3 IPs para evitar ataques
        fingerprint_parts.append(f"alt_ip{idx}:{possible_ip}")
    
    # Criar uma string combinando os fatores e ordenada para consistência
    fingerprint_str = "|".join(sorted(fingerprint_parts))
    
    # Gerar hash da string para criar o fingerprint
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()

def check_rate_limit(route_name: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Verifica se um cliente atingiu o limite de taxa para uma rota específica
    
    Retorna: (is_allowed, rate_limit_info)
    """
    # Obter cliente por IP + fingerprint para maior precisão
    ip = request.remote_addr or "unknown"
    fingerprint = get_client_fingerprint()
    client_id = f"{ip}:{fingerprint[:8]}"
    
    # Inicializar a estrutura de dados se necessário
    if client_id not in RATE_LIMITS:
        RATE_LIMITS[client_id] = {}
    
    now = time.time()
    
    # Limpar dados antigos primeiro
    for r in list(RATE_LIMITS[client_id].keys()):
        if now - RATE_LIMITS[client_id][r]['last_request'] > RATE_LIMIT_WINDOW:
            del RATE_LIMITS[client_id][r]
    
    # Obter o limite para esta rota específica ou usar o padrão
    if route_name in RATE_LIMIT_MAX_REQUESTS:
        max_requests = RATE_LIMIT_MAX_REQUESTS[route_name]
    else:
        max_requests = RATE_LIMIT_MAX_REQUESTS['default']
    
    # Verificar a contagem atual
    if route_name in RATE_LIMITS[client_id]:
        route_info = RATE_LIMITS[client_id][route_name]
        
        # Se a última requisição foi há mais de X segundos, resetar o contador
        if now - route_info['last_request'] > RATE_LIMIT_WINDOW:
            RATE_LIMITS[client_id][route_name] = {'count': 1, 'last_request': now}
            return True, {
                'limit': max_requests, 
                'remaining': max_requests - 1, 
                'reset': int(now + RATE_LIMIT_WINDOW)
            }
        
        # Verificar se o limite foi atingido
        if route_info['count'] >= max_requests:
            reset_time = route_info['last_request'] + RATE_LIMIT_WINDOW
            return False, {
                'limit': max_requests, 
                'remaining': 0, 
                'reset': int(reset_time)
            }
        
        # Incrementar contador
        route_info['count'] += 1
        route_info['last_request'] = now
        return True, {
            'limit': max_requests, 
            'remaining': max_requests - route_info['count'], 
            'reset': int(now + RATE_LIMIT_WINDOW)
        }
    else:
        # Primeira requisição para esta rota
        RATE_LIMITS[client_id][route_name] = {'count': 1, 'last_request': now}
        return True, {
            'limit': max_requests, 
            'remaining': max_requests - 1, 
            'reset': int(now + RATE_LIMIT_WINDOW)
        }

def verify_referer() -> bool:
    """
    Verifica se o referer é permitido
    """
    # Rotas de verificação de pagamento não precisam de verificação de referer
    # para compatibilidade com webhooks e atualizações de status no frontend
    if request.path and (
        request.path.endswith('/verificar-pagamento') or
        request.path.endswith('/verificar_pagamento') or
        request.path.endswith('/check-payment-status') or
        request.path.endswith('/payment-status') or
        request.path.endswith('/check_for4payments_status') or
        request.path.endswith('/check_discount_payment_status') or
        request.path.endswith('/verificar_pagamento_frete') or
        request.path.endswith('/create-pix-payment') or
        request.path.endswith('/pagar-frete') or
        request.path.endswith('/comprar-livro')
    ):
        return True
    
    referer = request.headers.get('Referer')
    if not referer:
        return False
    
    # Extrair o domínio do referer
    try:
        referer_domain = urlparse(referer).netloc
        # Remover a porta se presente
        if ':' in referer_domain:
            referer_domain = referer_domain.split(':')[0]
            
        return any(referer_domain.endswith(domain) for domain in ALLOWED_DOMAINS)
    except Exception as e:
        current_app.logger.error(f"Erro ao analisar referer: {str(e)}")
        return False

def verify_csrf_token(token: str) -> bool:
    """
    Verifica se um token CSRF é válido
    """
    if token in CSRF_TOKENS:
        if time.time() < CSRF_TOKENS[token]:
            return True
        else:
            # Token expirado
            CSRF_TOKENS.pop(token, None)
    return False

def secure_api(route_name: str = None):
    """
    Decorador para proteger rotas de API com múltiplas camadas de segurança
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verificação 1: Limites de taxa
            rate_limit_name = route_name or request.endpoint or 'default'
            allowed, rate_info = check_rate_limit(rate_limit_name)
            if not allowed:
                current_app.logger.warning(f"Taxa limite excedida para {rate_limit_name}")
                response = jsonify({
                    'error': 'Muitas requisições. Tente novamente em alguns segundos.',
                    'rate_limit': rate_info
                })
                response.status_code = 429
                return response
            
            # Adicionar headers com informações de limite de taxa
            g.rate_limit_info = rate_info
            
            # Verificação 2: Origem do Referer
            if not verify_referer():
                current_app.logger.warning(f"Referer inválido: {request.headers.get('Referer')}")
                return jsonify({'error': 'Acesso não autorizado'}), 403
            
            # Verificação 3: Detectar possíveis ataques de injeção nos parâmetros
            for key, value in request.values.items():
                if isinstance(value, str):
                    for pattern in INJECTION_PATTERNS:
                        if re.search(pattern, value, re.IGNORECASE):
                            current_app.logger.warning(f"Possível ataque de injeção detectado: {key}={value}")
                            return jsonify({'error': 'Requisição inválida'}), 400
            
            # Para rotas POST, verificar token CSRF (exceto rotas de verificação de status de pagamento e páginas específicas de geração de PIX)
            if request.method == 'POST' and not (request.path and (
                request.path.endswith('/verificar-pagamento') or 
                request.path.endswith('/verificar_pagamento') or 
                request.path.endswith('/check-payment-status') or 
                request.path.endswith('/payment-status') or 
                request.path.endswith('/check_for4payments_status') or 
                request.path.endswith('/check_discount_payment_status') or 
                request.path.endswith('/verificar_pagamento_frete') or
                # Adicionar exceção para a rota de criação de PIX na página de agradecimento
                request.path.endswith('/create-pix-payment') or
                request.path.endswith('/pagar-frete') or
                request.path.endswith('/comprar-livro')
            )):
                csrf_token = request.headers.get('X-CSRF-Token')
                if not csrf_token or not verify_csrf_token(csrf_token):
                    current_app.logger.warning("Token CSRF inválido ou ausente")
                    return jsonify({'error': 'Token de segurança inválido ou expirado'}), 403
            
            # Limpar tokens CSRF expirados periodicamente
            clean_expired_csrf_tokens()
            
            # Se tudo estiver ok, prosseguir com a rota
            return f(*args, **kwargs)
        return decorated_function
    return decorator