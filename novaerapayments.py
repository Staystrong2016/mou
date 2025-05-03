import os
import requests
import base64
from typing import Dict, Any, Optional
from datetime import datetime
import random
import string
from flask import current_app


class NovaEraPaymentsAPI:
    API_URL = "https://api.novaera-pagamentos.com/api/v1"

    def __init__(self, authorization_token: str):
        self.authorization_token = authorization_token

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f"Basic {base64.b64encode(f'{self.authorization_token}:x'.encode()).decode()}",
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
        if not self.authorization_token or len(self.authorization_token) < 10:
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
                "customer": {
                    "name": data['name'],
                    "email": email,
                    "phone": phone,
                    "document": {
                        "type": "cpf",
                        "number": cpf
                    }
                },
                "shipping": {
                    "fee": 0,
                    "address": {
                        "street": "Rua Ângelo Pessotti",
                        "streetNumber": "1",
                        "neighborhood": "Segato",
                        "city": "Aracruz",
                        "state": "ES",
                        "zipCode": "70655054",
                        "complement": "32"
                    }
                },
                "pix": {
                    "expiresInDays": 30
                },
                "amount": amount_in_cents,
                "paymentMethod": "pix",
                "items": [{
                    "tangible": True,
                    "title": "Limpa Nome",
                    "unitPrice": amount_in_cents,
                    "quantity": 1
                }]
            }

            # Envia a requisição para a API Nova Era
            try:
                response = requests.post(
                    f"{self.API_URL}/transactions",
                    json=payment_data,
                    headers=self._get_headers(),
                    timeout=30
                )

                # A API Nova Era retorna 201 para criação bem-sucedida
                if response.status_code in [200, 201]:
                    response_data = response.json()
                    current_app.logger.info(f"[DEBUG] Resposta completa da API NovaEra (criar pagamento): {response_data}")
                    
                    # Montar resposta no formato esperado pela aplicação
                    # Incluir também os dados do cliente para garantir que estejam disponíveis posteriormente
                    return {
                        'id': response_data['data']['id'],
                        'status': response_data['data']['status'],
                        'amount': response_data['data']['amount'],
                        'pix_qr_code': f"https://api.qrserver.com/v1/create-qr-code/?data={response_data['data']['pix']['qrcode']}&size=300x300",
                        'pix_code': response_data['data']['pix']['qrcode'],
                        'expires_at': response_data['data']['pix']['expirationDate'],
                        'secure_url': response_data['data']['secureUrl'],
                        # Adicionar os dados do cliente para uso posterior
                        'name': data['name'],
                        'email': email,
                        'cpf': cpf,
                        'phone': phone
                    }
                else:
                    raise ValueError(f"Erro ao processar pagamento: {response.status_code} - {response.text}")

            except requests.exceptions.RequestException as e:
                raise ValueError(f"Erro de conexão com o serviço de pagamento. Tente novamente. Detalhes: {str(e)}")

        except ValueError as e:
            raise ValueError(f"Erro de validação: {str(e)}")
        except Exception as e:
            raise ValueError(f"Erro inesperado ao processar pagamento: {str(e)}")

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Check the status of a payment"""
        try:
            response = requests.get(
                f"{self.API_URL}/transactions/{payment_id}",
                headers=self._get_headers(),
                timeout=30
            )

            if response.status_code == 200:
                payment_data = response.json()
                current_app.logger.info(f"[DEBUG] Resposta completa da API NovaEra: {payment_data}")
                
                # Constrói a resposta padrão
                result = {
                    'status': payment_data['data']['status']
                }

                # Adiciona campos adicionais, se disponíveis
                try:
                    if 'pix' in payment_data['data'] and 'qrcode' in payment_data['data']['pix']:
                        result['pix_qr_code'] = payment_data['data']['pix']['qrcode']
                        result['pix_code'] = payment_data['data']['pix']['qrcode']
                except Exception as e:
                    current_app.logger.error(f"[ERROR] Erro ao acessar campos de PIX: {str(e)}")
                
                # Se o status for 'paid', retornar essa informação explicitamente para compatibilidade
                # Para compatibilidade com a estrutura esperada pelo frontend
                if payment_data['data']['status'] == 'paid':
                    result['status'] = 'paid'
                    current_app.logger.info(f"[INFO] Pagamento com ID {payment_id} confirmado como PAGO")
                
                return result
            else:
                current_app.logger.error(f"[ERROR] Erro ao verificar status do pagamento: {response.status_code} - {response.text}")
                return {'status': 'pending'}

        except Exception as e:
            current_app.logger.error(f"[ERROR] Exceção ao verificar status do pagamento: {str(e)}")
            return {'status': 'pending'}


def encode_api_token(secret_key: str) -> str:
    """
    Codifica a chave secreta no formato Base64 para autenticação Basic.
    Formato: base64(secret_key:x)
    """
    token_string = f"{secret_key}:x"
    return base64.b64encode(token_string.encode('utf-8')).decode('utf-8')


def create_payment_api(authorization_token: Optional[str] = None) -> NovaEraPaymentsAPI:
    """Factory function to create NovaEraPaymentsAPI instance"""
    secret_key = os.environ.get("NOVAERA_PAYMENT_SECRET_KEY", "sk_5phdh9CE2WiBbzoEp0aGiK4X-KNeWCDhqfiB-sP2GCuCc5p6")
    if authorization_token is None:        
        if not secret_key:
            raise ValueError("NOVAERA_PAYMENT_SECRET_KEY não configurado no ambiente")

    return NovaEraPaymentsAPI(secret_key)


def test_token_encoding():
    """
    Função para testar a codificação do token da NovaEra.
    Pode ser executada diretamente para verificar o formato do token.
    """
    secret_key = "sk_5phdh9CE2WiBbzoEp0aGiK4X-KNeWCDhqfiB-sP2GCuCc5p6"
    encoded_token = encode_api_token(secret_key)
    
    print("\n===== TESTE DE CODIFICAÇÃO DO TOKEN NOVAERA =====")
    print(f"Secret Key: {secret_key}")
    print(f"Token Codificado: {encoded_token}")
    print("====================================================\n")
    
    # Teste de decodificação para verificar o formato
    decoded = base64.b64decode(encoded_token).decode('utf-8')
    print(f"Token Decodificado: {decoded}")
    print(f"Formato correto? {'sim' if decoded == f'{secret_key}:x' else 'não'}")
    print("====================================================\n")
    
    return encoded_token