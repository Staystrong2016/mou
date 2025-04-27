import os
import re
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any
from functools import wraps
from urllib.parse import urlparse, parse_qs
from flask import request, redirect, g, current_app, Request, Response

class RequestAnalyzer:
    def __init__(self):
        # Configurações do analisador
        self.config = {
            'detect_mobile': True,
            'detect_social_ads': True,
            'log_all_requests': False,
            'rate_limit_window': 60,  # segundos
            'max_requests': 100,
            'cache_ttl': 15 * 60  # 15 minutos em segundos
        }

        # Padrões para detecção de dispositivos móveis
        self.mobile_patterns = {
            'devices': re.compile(r'(android|iphone|ipad|ipod|windows phone|blackberry|mobile)', re.I),
            'browsers': re.compile(r'(mobi|opera mini)', re.I),
            'mobile_hints': re.compile(r'(; wv|mobile\/)', re.I)
        }

        # Padrões para detecção de anúncios de redes sociais
        self.social_ad_domains = ['instagram.com', 'facebook.com', 'fb.watch', 'm.facebook.com', 'l.instagram.com']
        self.social_ad_params = ['fbclid', 'igshid', 'utm_source=ig', 'utm_source=fb', 'gclid', 'ad_id']
        self.meta_specific = ['facebook.com/ads', 'instagram.com/p/', 'facebook.com/reel/', 'instagram.com/reel/']

        # Padrões para detecção de scrapers/bots
        self.scraper_patterns = re.compile(r'(httrack|curl|wget|python-requests|saveweb2zip|bot|spider|crawler)', re.I)
        
        # Armazenamento das requisições para rate limiting
        self.request_store = {}  # {ip: {'count': int, 'first_request': timestamp}}
        
        # Cache de análises de requisições
        self.cache = {}  # {fingerprint: {'user_source': dict, 'timestamp': int, 'is_bot': bool}}
        
        self.logger = logging.getLogger('request_analyzer')

    def get_request_data(self, req: Request) -> Dict[str, Any]:
        """Extrai dados relevantes da requisição"""
        user_agent = req.headers.get('User-Agent', '').lower()
        referer = req.headers.get('Referer', '').lower()
        
        # Extrair parâmetros de consulta da URL
        query_params = {}
        if '?' in req.url:
            query_part = req.url.split('?', 1)[1]
            parsed_qs = parse_qs(query_part)
            for key, values in parsed_qs.items():
                query_params[key] = values[0] if values else ''
        
        # Extrair cabeçalhos relacionados a proxies
        proxy_headers = {
            'x-forwarded-for': req.headers.get('X-Forwarded-For'),
            'via': req.headers.get('Via'),
            'client-ip': req.headers.get('Client-IP'),
            'x-real-ip': req.headers.get('X-Real-IP')
        }
        
        return {
            'ip': req.remote_addr,
            'user_agent': user_agent,
            'referer': referer,
            'query_params': query_params,
            'proxy_headers': proxy_headers
        }

    def is_mobile(self, user_agent: Optional[str]) -> bool:
        """Verifica se o user agent indica um dispositivo móvel"""
        if not user_agent or not self.config['detect_mobile']:
            return False
        
        # Verifica padrões de dispositivos e navegadores móveis
        is_mobile_device = self.mobile_patterns['devices'].search(user_agent) is not None
        is_mobile_browser = self.mobile_patterns['browsers'].search(user_agent) is not None
        has_mobile_hints = self.mobile_patterns['mobile_hints'].search(user_agent) is not None
        
        # Verifica se tem informação de largura no user agent
        has_width = False
        if 'width' in user_agent:
            width_match = re.search(r'width=(\d+)', user_agent)
            if width_match:
                width = int(width_match.group(1))
                has_width = width <= 768
                
        return is_mobile_device or is_mobile_browser or has_mobile_hints or has_width

    def is_from_social_ad(self, referer: Optional[str], query_params: Dict[str, str]) -> bool:
        """Verifica se o acesso veio de um anúncio em rede social"""
        if not self.config['detect_social_ads']:
            return False
            
        # Se não tem referer mas tem parâmetros específicos de anúncios, pode ser de anúncio
        if not referer:
            # Verifica se tem parâmetros que indicam origem de anúncios
            ad_param_in_query = any(param in query_params for param in self.social_ad_params)
            
            # Verifica se utm_source indica origem de rede social
            social_utm = False
            if 'utm_source' in query_params:
                utm_source = query_params['utm_source']
                social_utm = re.search(r'facebook|instagram|meta|fb|ig', utm_source, re.I) is not None
                
            return ad_param_in_query or social_utm
        
        # ---- Verificações com referer ----
        
        # Verifica se o referer contém algum dos domínios de redes sociais
        from_social_domain = any(domain in referer for domain in self.social_ad_domains)
        
        # Verifica se há parâmetros que indicam origem de anúncios no referer
        has_ad_params_in_referer = any(param in referer for param in self.social_ad_params)
        
        # Verifica se há parâmetros que indicam origem de anúncios nos query params
        has_ad_params_in_query = any(param in query_params for param in self.social_ad_params)
        
        # Verifica padrões específicos da Meta
        has_meta_pattern = any(pattern in referer for pattern in self.meta_specific)
        
        # Verifica se utm_source indica origem de rede social
        from_social_utm = False
        if 'utm_source' in query_params:
            utm_source = query_params['utm_source']
            from_social_utm = re.search(r'facebook|instagram|meta|fb|ig', utm_source, re.I) is not None
        
        # Log para debug detalhado
        print(f"DEBUG - Social Ad Detection Details:")
        print(f"  From Social Domain: {from_social_domain}")
        print(f"  Has Ad Params in Referer: {has_ad_params_in_referer}")
        print(f"  Has Ad Params in Query: {has_ad_params_in_query}")
        print(f"  Has Meta Pattern: {has_meta_pattern}")
        print(f"  From Social UTM: {from_social_utm}")
        
        result = from_social_domain or has_ad_params_in_referer or has_ad_params_in_query or has_meta_pattern or from_social_utm
        print(f"  Final Social Ad Detection: {result}")
        
        return result

    def get_ad_source(self, referer: Optional[str], query_params: Dict[str, str]) -> str:
        """Determina a fonte do anúncio, se aplicável"""
        # Verifica primeiro se não é de anúncio
        is_from_ad = self.is_from_social_ad(referer, query_params)
        if not is_from_ad:
            return 'orgânico'
            
        # Verifica origem com base no referer ou utm_source
        if referer:
            if 'instagram' in referer:
                return 'instagram_ads'
            if 'facebook' in referer or 'fb.com' in referer or 'fb.watch' in referer:
                return 'facebook_ads'
                
        # Verifica origem com base nos parâmetros UTM
        if 'utm_source' in query_params:
            utm_source = query_params['utm_source'].lower()
            if 'instagram' in utm_source or 'ig' in utm_source:
                return 'instagram_ads'
            if 'facebook' in utm_source or 'fb' in utm_source:
                return 'facebook_ads'
                
        # Verifica parâmetros específicos
        if 'fbclid' in query_params:
            return 'facebook_ads'
        if 'igshid' in query_params:
            return 'instagram_ads'
            
        # Se não foi possível determinar a fonte específica, mas sabemos que é de anúncio
        return 'social_ads'

    def uses_proxy(self, proxy_headers: Dict[str, Any]) -> bool:
        """Verifica se a requisição usa proxy com base nos cabeçalhos"""
        # Em ambiente de desenvolvimento, não queremos detectar proxies internos do Replit
        if os.environ.get('DEVELOPING', 'false').lower() == 'true':
            return False
            
        # Vamos considerar apenas se tiver mais de um cabeçalho de proxy
        # ou se o X-Forwarded-For contiver múltiplos IPs
        proxy_count = sum(1 for header in proxy_headers.values() if header is not None and header != '')
        
        # Se tiver X-Forwarded-For com múltiplos IPs
        if proxy_headers.get('x-forwarded-for'):
            forwarded_ips = proxy_headers['x-forwarded-for'].split(',')
            if len(forwarded_ips) > 1:
                return True
                
        # Se tiver mais de um cabeçalho de proxy preenchido
        return proxy_count > 1

    def is_scraper(self, user_agent: Optional[str]) -> bool:
        """Verifica se o user agent indica um scraper/bot"""
        return bool(user_agent and self.scraper_patterns.search(user_agent))

    def get_fingerprint(self, ip: Optional[str], user_agent: Optional[str], referer: Optional[str] = None) -> str:
        """Gera uma impressão digital baseada no IP, user agent e referer (opcional)"""
        referer_part = ""
        if referer:
            # Usar apenas o domínio do referer
            try:
                from urllib.parse import urlparse
                parsed = urlparse(referer)
                referer_part = f":{parsed.netloc}"
            except:
                referer_part = f":{referer.split('/')[2] if '/' in referer else referer[:20]}"
        
        return f"{ip or ''}:{(user_agent or '')[:50]}{referer_part}"

    def update_rate_limit(self, ip: str) -> bool:
        """
        Atualiza e verifica o limite de taxa para um IP
        Retorna True se o limite foi excedido
        """
        current_time = time.time()
        
        if ip not in self.request_store:
            self.request_store[ip] = {'count': 1, 'first_request': current_time}
            return False
        
        ip_data = self.request_store[ip]
        
        # Reinicia contador se a janela de tempo expirou
        if current_time - ip_data['first_request'] > self.config['rate_limit_window']:
            self.request_store[ip] = {'count': 1, 'first_request': current_time}
            return False
        
        # Incrementa contador dentro da janela
        ip_data['count'] += 1
        self.request_store[ip] = ip_data
        
        return ip_data['count'] > self.config['max_requests']

    def create_log_entry(self, req: Request, user_source: Dict[str, Any]) -> Dict[str, Any]:
        """Cria uma entrada de log com detalhes da requisição"""
        request_data = self.get_request_data(req)
        ip = request_data['ip']
        user_agent = request_data['user_agent']
        
        details = []
        if user_source['uses_proxy']:
            details.append('proxy detectado')
        if user_source['is_scraper']:
            details.append('scraper detectado')
        if self.update_rate_limit(ip or ''):
            details.append('rate limit excedido')
        if user_source['is_from_social_ad']:
            details.append(f"origem: {user_source['ad_source']}")
        if user_source['is_mobile']:
            details.append('dispositivo: mobile')
        
        return {
            'timestamp': datetime.now().isoformat(),
            'ip': ip or '',
            'route': req.path,
            'user_agent': user_agent or '',
            'fingerprint': user_source['fingerprint'],
            'details': details
        }

    def check_cache(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """Verifica se há uma análise em cache para o fingerprint"""
        if fingerprint not in self.cache:
            return None
        
        cached = self.cache[fingerprint]
        if time.time() - cached['timestamp'] < self.config['cache_ttl']:
            return cached
        
        # Remove o cache expirado
        del self.cache[fingerprint]
        return None

    def set_cache(self, fingerprint: str, user_source: Dict[str, Any], is_bot: bool) -> None:
        """Armazena a análise no cache"""
        self.cache[fingerprint] = {
            'user_source': user_source,
            'timestamp': time.time(),
            'is_bot': is_bot
        }

    def analyze_request(self, req: Request) -> Tuple[Dict[str, Any], bool]:
        """
        Analisa uma requisição e determina características do usuário
        Retorna (user_source, is_bot)
        """
        request_data = self.get_request_data(req)
        ip = request_data['ip']
        user_agent = request_data['user_agent']
        referer = request_data['referer']
        query_params = request_data['query_params']
        proxy_headers = request_data['proxy_headers']
        
        fingerprint = self.get_fingerprint(ip, user_agent, referer)
        
        # Imprimir dados para debug
        print(f"DEBUG - Request Info:")
        print(f"IP: {ip}")
        print(f"User-Agent: {user_agent}")
        print(f"Referer: {referer}")
        print(f"Query Params: {query_params}")
        print(f"Proxy Headers: {proxy_headers}")
        
        # Verifica cache
        cached_entry = self.check_cache(fingerprint)
        if cached_entry:
            print(f"DEBUG - Usando entrada em cache para fingerprint: {fingerprint}")
            return cached_entry['user_source'], cached_entry['is_bot']
        
        # Análise da requisição
        is_mobile_result = self.is_mobile(user_agent)
        is_from_social_ad_result = self.is_from_social_ad(referer, query_params)
        ad_source_result = self.get_ad_source(referer, query_params)
        uses_proxy_result = self.uses_proxy(proxy_headers)
        is_scraper_result = self.is_scraper(user_agent)
        
        # Print de debug para cada detecção
        print(f"DEBUG - Detection Results:")
        print(f"Is Mobile: {is_mobile_result}")
        print(f"Is From Social Ad: {is_from_social_ad_result}")
        print(f"Ad Source: {ad_source_result}")
        print(f"Uses Proxy: {uses_proxy_result}")
        print(f"Is Scraper: {is_scraper_result}")
        
        user_source = {
            'is_mobile': is_mobile_result,
            'is_from_social_ad': is_from_social_ad_result,
            'ad_source': ad_source_result,
            'referer': referer,
            'user_agent': user_agent,
            'uses_proxy': uses_proxy_result,
            'is_scraper': is_scraper_result,
            'fingerprint': fingerprint
        }
        
        # Verifica se tem DEVELOPING=true no ambiente (para modo de desenvolvimento)
        developing = os.environ.get('DEVELOPING', 'false').lower() == 'true'
        print(f"DEBUG - Development Mode: {developing}")
        
        # Em desenvolvimento, consideramos bot apenas se for detectado explicitamente como scraper
        if developing:
            is_bot = user_source['is_scraper']
        else:
            # Em produção: é bot se for scraper OU (não for móvel E não vier de anúncio social)
            is_bot = user_source['is_scraper'] or (not user_source['is_mobile'] and not user_source['is_from_social_ad'])
        
        print(f"DEBUG - Is Bot: {is_bot}")
        
        # Armazena no cache
        self.set_cache(fingerprint, user_source, is_bot)
        
        return user_source, is_bot

    def should_bypass(self, path: str) -> bool:
        """Verifica se o caminho deve ignorar a análise"""
        bypass_patterns = [
            '/api',
            '/webhook',
            '/static',
            '/fonts',
            '/rawline',
            '/js',
            '/assets',
            '/css',
            '/images',
            '/img',
            '/favicon.ico',
            '/manifest.json',
            '/service-worker.js',
            '/robots.txt'
        ]
        
        return any(path.startswith(pattern) for pattern in bypass_patterns)

    def middleware(self, f):
        """Middleware de análise de requisições para Flask"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Bypass para endpoints específicos
            if self.should_bypass(request.path):
                return f(*args, **kwargs)
            
            # Analisa requisição
            user_source, is_bot = self.analyze_request(request)
            
            # Armazena na requisição atual (g é o objeto global do Flask)
            g.user_source = user_source
            
            # Cria e loga entrada
            if self.config['log_all_requests'] or any(user_source.values()):
                log_entry = self.create_log_entry(request, user_source)
                if log_entry['details']:
                    self.logger.info(f"Request analyzed: {log_entry['route']} - {', '.join(log_entry['details'])}")

            # Verifica se estamos em desenvolvimento
            developing = os.environ.get('DEVELOPING', 'false').lower() == 'true'
            
            # Redireciona bots em produção
            if is_bot and not developing and not user_source['is_mobile']:
                self.logger.info(f"Bot redirecionado: {user_source['fingerprint']}")
                return redirect('https://g1.globo.com')
            
            return f(*args, **kwargs)
        
        return decorated_function

# Instância global do analisador de requisições
request_analyzer = RequestAnalyzer()

# Função auxiliar para registrar o middleware em uma aplicação Flask
def register_request_analyzer(app):
    """Registra o middleware de análise de requisições em uma aplicação Flask"""
    app.before_request(request_analyzer_handler)
    return app

def request_analyzer_handler():
    """Função que é executada antes de cada requisição"""
    # Bypass para endpoints específicos
    if request_analyzer.should_bypass(request.path):
        return None
    
    # Analisa requisição
    user_source, is_bot = request_analyzer.analyze_request(request)
    
    # Armazena na requisição atual
    g.user_source = user_source
    
    # Armazena individualmente para facilitar o acesso nas rotas
    g.is_mobile = user_source['is_mobile']
    g.is_from_social_ad = user_source['is_from_social_ad']
    g.ad_source = user_source['ad_source']
    g.is_bot = is_bot
    
    # Cria e loga entrada
    if request_analyzer.config['log_all_requests'] or any(user_source.values()):
        log_entry = request_analyzer.create_log_entry(request, user_source)
        if log_entry['details']:
            current_app.logger.info(f"Request analyzed: {log_entry['route']} - {', '.join(log_entry['details'])}")

    # Verifica se estamos em desenvolvimento
    developing = os.environ.get('DEVELOPING', 'false').lower() == 'true'
    
    # Redireciona bots em produção
    if is_bot and not developing and not user_source['is_mobile']:
        current_app.logger.info(f"Bot redirecionado: {user_source['fingerprint']}")
        return redirect('https://g1.globo.com')
    
    return None

# Função auxiliar para verificar se o acesso é de anúncio nas rotas
def is_from_social_ad():
    """Verifica se a requisição atual veio de um anúncio social"""
    if hasattr(g, 'is_from_social_ad'):
        return g.is_from_social_ad
    return False

# Função auxiliar para verificar se o acesso é mobile nas rotas
def is_mobile():
    """Verifica se a requisição atual veio de um dispositivo móvel"""
    if hasattr(g, 'is_mobile'):
        return g.is_mobile
    return False

# Função auxiliar para obter a origem do anúncio nas rotas
def get_ad_source():
    """Retorna a origem do anúncio para a requisição atual"""
    if hasattr(g, 'ad_source'):
        return g.ad_source
    return 'orgânico'