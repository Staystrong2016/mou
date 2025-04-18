"""
Módulo para integração com a Utmify para rastreamento de vendas.
Baseado no código PHP fornecido.
"""
import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from flask import request

# Configurações da API Utmify
UTMIFY_API_URL = "https://api.utmify.com.br/api-credentials/orders"
UTMIFY_TOKEN = "u9DXHd26PMNTG6uRQScHcIHpc6jjS0WP8XcL"  # Token fornecido no exemplo

# Configuração de log
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('utmify')
logger.setLevel(logging.INFO)

# Handler para arquivo
log_file = os.path.join(LOG_DIR, f'utmify-pendente-{datetime.now().strftime("%Y-%m-%d")}.log')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(file_handler)

# Handler para console
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(console_handler)


def get_utm_params_from_session() -> Dict[str, Any]:
    """
    Recupera os parâmetros UTM armazenados na sessão.
    """
    from flask import session
    
    utm_params = {
        'utm_source': session.get('utm_source', None),
        'utm_campaign': session.get('utm_campaign', None),
        'utm_medium': session.get('utm_medium', None),
        'utm_content': session.get('utm_content', None),
        'utm_term': session.get('utm_term', None),
        'fbclid': session.get('fbclid', None),
        'gclid': session.get('gclid', None),
        'ttclid': session.get('ttclid', None),
        'src': session.get('src', None),
        'sck': session.get('sck', None),
        'xcod': session.get('xcod', None)
    }
    
    logger.info(f"UTM params recuperados da sessão: {utm_params}")
    return utm_params


def send_order_to_utmify(
    transaction_id: str,
    customer_name: str,
    customer_email: str,
    customer_document: str,
    product_name: str,
    product_price_cents: int,
    quantity: int = 1,
    utm_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Envia uma venda para a Utmify.
    
    Args:
        transaction_id: ID da transação (order_id)
        customer_name: Nome completo do cliente
        customer_email: Email do cliente
        customer_document: CPF do cliente (somente números)
        product_name: Nome do produto
        product_price_cents: Preço do produto em centavos
        quantity: Quantidade do produto (padrão: 1)
        utm_params: Parâmetros UTM (opcional)
    
    Returns:
        Dict contendo sucesso/falha e mensagem
    """
    if utm_params is None:
        utm_params = get_utm_params_from_session()
    
    # Formatação dos dados conforme esperado pela API da Utmify
    utmify_data = {
        'orderId': transaction_id,
        'platform': 'For4Payments',  # Adaptar conforme sua plataforma
        'paymentMethod': 'pix',
        'status': 'waiting_payment',
        'createdAt': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),  # UTC
        'approvedDate': None,
        'refundedAt': None,
        'customer': {
            'name': customer_name,
            'email': customer_email,
            'phone': None,  # Opcional
            'document': customer_document,
            'country': 'BR',
            'ip': request.remote_addr if request else None
        },
        'products': [
            {
                'id': f'prod_{transaction_id}',  # Identificador único para o produto
                'name': product_name,
                'planId': None,
                'planName': None,
                'quantity': quantity,
                'priceInCents': product_price_cents
            }
        ],
        'trackingParameters': {
            'src': utm_params.get('src'),
            'sck': utm_params.get('sck'),
            'utm_source': utm_params.get('utm_source'),
            'utm_campaign': utm_params.get('utm_campaign'),
            'utm_medium': utm_params.get('utm_medium'),
            'utm_content': utm_params.get('utm_content'),
            'utm_term': utm_params.get('utm_term'),
            'xcod': utm_params.get('xcod'),
            'fbclid': utm_params.get('fbclid'),
            'gclid': utm_params.get('gclid'),
            'ttclid': utm_params.get('ttclid')
        },
        'commission': {
            'totalPriceInCents': product_price_cents * quantity,
            'gatewayFeeInCents': 0,  # Opcional: taxa da gateway
            'userCommissionInCents': 0  # Opcional: comissão do usuário
        },
        'isTest': False
    }
    
    logger.info(f"📤 Dados formatados para Utmify: {json.dumps(utmify_data, indent=2)}")
    
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-token": UTMIFY_TOKEN
        }
        
        logger.info(f"📡 Enviando requisição para Utmify: {UTMIFY_API_URL}")
        
        response = requests.post(
            UTMIFY_API_URL,
            headers=headers,
            json=utmify_data
        )
        
        logger.info(f"✅ Resposta da API Utmify - Status: {response.status_code}, Resposta: {response.text}")
        
        if response.status_code == 200:
            return {
                'success': True,
                'message': 'Dados enviados com sucesso para Utmify'
            }
        else:
            logger.error(f"❌ Erro na API Utmify. HTTP Code: {response.status_code}, Resposta: {response.text}")
            return {
                'success': False,
                'message': f'Erro na API Utmify. HTTP Code: {response.status_code}'
            }
    
    except Exception as e:
        logger.error(f"❌ Erro ao enviar para Utmify: {str(e)}")
        return {
            'success': False,
            'message': f'Erro ao enviar dados para Utmify: {str(e)}'
        }


def update_order_status_in_utmify(
    transaction_id: str,
    status: str,
    approved_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atualiza o status de uma ordem na Utmify.
    
    Args:
        transaction_id: ID da transação
        status: Novo status ('paid', 'refunded', 'cancelled')
        approved_date: Data de aprovação (formato: 'YYYY-MM-DD HH:MM:SS') - UTC
        
    Returns:
        Dict contendo sucesso/falha e mensagem
    """
    # URL específica para atualização de status
    update_url = f"{UTMIFY_API_URL}/{transaction_id}/status"
    
    update_data = {
        'status': status,
    }
    
    if status == 'paid' and approved_date:
        update_data['approvedDate'] = approved_date
    
    logger.info(f"📤 Atualizando status na Utmify para {transaction_id}: {json.dumps(update_data, indent=2)}")
    
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-token": UTMIFY_TOKEN
        }
        
        response = requests.patch(
            update_url,
            headers=headers,
            json=update_data
        )
        
        logger.info(f"✅ Resposta da atualização - Status: {response.status_code}, Resposta: {response.text}")
        
        if response.status_code == 200:
            return {
                'success': True,
                'message': f'Status atualizado com sucesso para {status}'
            }
        else:
            logger.error(f"❌ Erro ao atualizar status. HTTP Code: {response.status_code}, Resposta: {response.text}")
            return {
                'success': False,
                'message': f'Erro ao atualizar status. HTTP Code: {response.status_code}'
            }
    
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar status: {str(e)}")
        return {
            'success': False,
            'message': f'Erro ao atualizar status: {str(e)}'
        }