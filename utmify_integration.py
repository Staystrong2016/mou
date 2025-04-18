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
UTMIFY_X_API_KEY = "mSv9bhkTG2MtZ5Gj4OczV1KdQpHUYiGXnSGE"  # X-API-KEY fornecida

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


def process_payment_webhook(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa um webhook de pagamento confirmado e envia os dados para a Utmify.
    
    Baseado no código PHP fornecido.
    
    Args:
        payment_data: Dados do pagamento confirmado
        
    Returns:
        Dict contendo sucesso/falha e mensagem
    """
    logger.info(f"📥 Dados recebidos para processamento: {json.dumps(payment_data, indent=2)}")
    
    # Verificar se o status é de pagamento confirmado (ignorar outros status)
    status = payment_data.get('status', '').lower()
    if status not in ['paid', 'approved', 'completed', 'confirmed']:
        logger.info(f"⏭️ Status ignorado: {status}")
        return {
            'success': True,
            'message': f'Status ignorado: {status}'
        }
    
    # Obter os dados necessários do payment_data
    try:
        # Dados básicos da transação
        transaction_id = payment_data.get('orderId') or payment_data.get('id')
        if not transaction_id:
            raise ValueError("ID da transação não encontrado nos dados")
        
        # Verificar se temos as datas
        created_at = payment_data.get('createdAt')
        paid_at = payment_data.get('paidAt') or payment_data.get('approvedDate') or datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        # Dados do cliente
        customer = payment_data.get('customer', {})
        customer_name = customer.get('name', '')
        customer_email = customer.get('email', '')
        
        # Tentar obter o CPF de diferentes locais possíveis na estrutura
        customer_document = ''
        if 'document' in customer:
            if isinstance(customer['document'], dict):
                customer_document = customer['document'].get('number', '')
            else:
                customer_document = customer.get('document', '')
        
        # Produtos/itens
        items = payment_data.get('items', [])
        products = []
        
        if items:
            for item in items:
                product = {
                    'id': item.get('id', f'prod_{transaction_id}_{len(products)}'),
                    'name': item.get('title', item.get('name', 'Produto')),
                    'planId': None,
                    'planName': None,
                    'quantity': item.get('quantity', 1),
                    'priceInCents': item.get('unitPrice', 0)
                }
                products.append(product)
        else:
            # Se não houver itens, criar um produto padrão
            product_name = payment_data.get('productName', 'Mounjaro (Tirzepatida) 5mg')
            product_price = payment_data.get('amount', 0)
            if isinstance(product_price, str):
                try:
                    product_price = int(float(product_price) * 100)
                except:
                    product_price = 0
            
            products.append({
                'id': f'prod_{transaction_id}',
                'name': product_name,
                'planId': None,
                'planName': None,
                'quantity': 1,
                'priceInCents': product_price
            })
        
        # Parâmetros de rastreamento (UTM)
        utm_params = payment_data.get('trackingParameters', {})
        
        # Informações de comissão/taxas
        amount = payment_data.get('amount', 0)
        if isinstance(amount, str):
            try:
                amount = int(float(amount) * 100)
            except:
                amount = 0
        
        fees = payment_data.get('fee', {})
        fixed_fee = fees.get('fixedAmount', 0)
        net_amount = fees.get('netAmount', amount)
        
        # Preparar os dados para envio à Utmify
        utmify_data = {
            'orderId': transaction_id,
            'platform': 'For4Payments',
            'paymentMethod': 'pix',
            'status': 'paid',
            'createdAt': created_at,
            'approvedDate': paid_at,
            'refundedAt': None,
            'customer': {
                'name': customer_name,
                'email': customer_email,
                'phone': None,
                'document': customer_document,
                'country': 'BR',
                'ip': request.remote_addr if request else None
            },
            'products': products,
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
                'totalPriceInCents': amount,
                'gatewayFeeInCents': fixed_fee,
                'userCommissionInCents': net_amount
            },
            'isTest': False
        }
        
        logger.info(f"📤 Dados formatados para Utmify: {json.dumps(utmify_data, indent=2)}")
        
        # Enviar para a Utmify
        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-token": UTMIFY_TOKEN,
                "x-api-key": UTMIFY_X_API_KEY
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
                error_msg = f"Erro na API Utmify. HTTP Code: {response.status_code}"
                logger.error(f"❌ {error_msg}, Resposta: {response.text}")
                return {
                    'success': False,
                    'message': error_msg
                }
        
        except Exception as e:
            error_msg = f"Erro ao enviar para Utmify: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'message': error_msg
            }
    
    except Exception as e:
        error_msg = f"Erro ao processar dados de pagamento: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {
            'success': False,
            'message': error_msg
        }