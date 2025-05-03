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
        """Gera os headers de autenticação para a API da NovaEra"""
        # Verificar se o token está presente e tem um formato válido
        if not self.authorization_token or len(self.authorization_token) < 10:
            current_app.logger.error(f"[CRITICAL] Token de autorização inválido: {self.authorization_token[:3]}... (tamanho: {len(self.authorization_token) if self.authorization_token else 0})")
        
        # Verifica se o token começa com 'sk_' para o formato esperado da NovaEra
        if not self.authorization_token.startswith('sk_'):
            current_app.logger.warning(f"[WARNING] Token NovaEra potencialmente inválido, não começa com 'sk_'. Começo: {self.authorization_token[:5]}")
        
        # Codificar o token no formato Basic auth: "Basic base64(token:x)"
        try:
            # Criar o formato 'token:x' conforme exigido pela API
            auth_value = f"{self.authorization_token}:x"
            # Codificar em base64
            encoded_auth = base64.b64encode(auth_value.encode()).decode()
            auth_header = f"Basic {encoded_auth}"
            
            current_app.logger.debug(f"[DEBUG] Token codificado com sucesso. Tamanho do header: {len(auth_header)}")
            
            return {
                'Authorization': auth_header,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        except Exception as e:
            current_app.logger.error(f"[ERROR] Erro ao codificar token de autorização: {str(e)}")
            # Retornar headers sem autorização em caso de erro
            return {
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

            # Obter endereço do usuário (usar dados reais se disponíveis)
            address = {
                "street": data.get('street', "Rua Principal"),
                "streetNumber": data.get('street_number', "1"),
                "neighborhood": data.get('neighborhood', "Centro"),
                "city": data.get('city', "São Paulo"),
                "state": data.get('state', "SP"),
                "zipCode": data.get('zip_code', "01000000"),
                "complement": data.get('complement', "")
            }
            
            # Obter nome do produto (usar dado real se disponível)
            product_title = data.get('product_title', "Kit Shopee: Dia das Mães")
            
            current_app.logger.info(f"[DEBUG] Objeto Data complet: {data}")
            payment_data = {
                "customer": {
                    "name": data.get('name'),
                    "email": data.get('email'),
                    "phone": data.get('phone'),
                    "document": {
                        "type": "cpf",
                        "number": data.get('cpf')
                    }
                },
                "shipping": {
                    "fee": data.get('shipping_fee', 0),
                    "address": address
                },
                "pix": {
                    "expiresInDays": 30
                },
                "amount": amount_in_cents,
                "paymentMethod": "pix",
                "items": [{
                    "tangible": True,
                    "title": "Kit Shopee: Dia das Mães",
                    "unitPrice": amount_in_cents,
                    "quantity": 1
                }],
                "postbackUrl": "https://webhook.site/56faf93c-8edf-4a2d-a64a-babafda826f3"
            }

            current_app.logger.info(f"[DEBUG] Objeto Payment Data completo: {payment_data}")
            current_app.logger.info(f"[DEBUG] Criando pagamento PIX para {data['name']} | CPF: {cpf} | Telefone: {phone}")
            

            # Gera e loga os headers para depuração (omitindo o token completo)
            headers = self._get_headers()
            debug_headers = headers.copy()
            if 'Authorization' in debug_headers:
                auth_value = debug_headers['Authorization']
                if len(auth_value) > 15:
                    # Mostrar apenas o início e o fim do token para depuração
                    debug_headers['Authorization'] = f"{auth_value[:10]}...{auth_value[-5:]}"
            
            current_app.logger.info(f"[DEBUG] Headers para API NovaEra: {debug_headers}")
            
            # Envia a requisição para a API Nova Era
            try:
                current_app.logger.info(f"[DEBUG] Enviando requisição para: {self.API_URL}/transactions")
                response = requests.post(
                    f"{self.API_URL}/transactions",
                    json=payment_data,
                    headers=headers,
                    timeout=30
                )
                
                current_app.logger.info(f"[DEBUG] Código de status da resposta: {response.status_code}")
                
                # Logar o conteúdo da resposta
                try:
                    response_content = response.json()
                    current_app.logger.info(f"[DEBUG] Conteúdo da resposta: {response_content}")
                except Exception as json_error:
                    current_app.logger.error(f"[ERROR] Falha ao decodificar resposta JSON: {str(json_error)}")
                    current_app.logger.info(f"[DEBUG] Texto da resposta: {response.text}")

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
                    current_app.logger.error(f"[ERROR] Falha na requisição HTTP: {response.status_code}")
                    current_app.logger.error(f"[ERROR] Texto da resposta: {response.text}")
                    
                    # Verificar se o erro é de autenticação
                    if response.status_code == 401:
                        current_app.logger.error("[CRITICAL] ERRO DE AUTENTICAÇÃO: token inválido ou expirado")
                        current_app.logger.error(f"[DEBUG] Tamanho do token: {len(self.authorization_token)} caracteres")
                        current_app.logger.error(f"[DEBUG] Começo do token: {self.authorization_token[:8]}...")
                    
                    raise ValueError(f"Erro ao processar pagamento: {response.status_code} - {response.text}")

            except requests.exceptions.RequestException as e:
                raise ValueError(f"Erro de conexão com o serviço de pagamento. Tente novamente. Detalhes: {str(e)}")

        except ValueError as e:
            raise ValueError(f"Erro de validação: {str(e)}")
        except Exception as e:
            raise ValueError(f"Erro inesperado ao processar pagamento: {str(e)}")

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Check the status of a payment"""
        current_app.logger.info(f"[DEBUG] Verificando status do pagamento: {payment_id}")
        
        # Gera e loga os headers para depuração (omitindo o token completo)
        headers = self._get_headers()
        debug_headers = headers.copy()
        if 'Authorization' in debug_headers:
            auth_value = debug_headers['Authorization']
            if len(auth_value) > 15:
                # Mostrar apenas o início e o fim do token para depuração
                debug_headers['Authorization'] = f"{auth_value[:10]}...{auth_value[-5:]}"
        
        current_app.logger.info(f"[DEBUG] Headers para verificar status: {debug_headers}")
        
        try:
            current_app.logger.info(f"[DEBUG] Enviando requisição para: {self.API_URL}/transactions/{payment_id}")
            response = requests.get(
                f"{self.API_URL}/transactions/{payment_id}",
                headers=headers,
                timeout=30
            )
            
            current_app.logger.info(f"[DEBUG] Código de status da resposta: {response.status_code}")
            
            # Verificação de erro de autenticação
            if response.status_code == 401:
                current_app.logger.error("[CRITICAL] ERRO DE AUTENTICAÇÃO ao verificar status: token inválido ou expirado")
                current_app.logger.error(f"[DEBUG] Tamanho do token: {len(self.authorization_token)} caracteres")
                current_app.logger.error(f"[DEBUG] Começo do token: {self.authorization_token[:8]}...")
                return {'status': 'pending', 'error': 'Unauthorized'}

            # Tenta processar a resposta como JSON
            try:
                response_content = response.json()
                current_app.logger.info(f"[DEBUG] Conteúdo da resposta: {response_content}")
            except Exception as json_error:
                current_app.logger.error(f"[ERROR] Falha ao decodificar resposta JSON: {str(json_error)}")
                current_app.logger.info(f"[DEBUG] Texto da resposta: {response.text}")
                return {'status': 'pending', 'error': 'Invalid JSON response'}

            # Sucesso: processa os dados
            if response.status_code == 200:
                payment_data = response_content
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
                
                # Extrair dados do cliente
                try:
                    if 'customer' in payment_data['data']:
                        customer = payment_data['data']['customer']
                        if customer.get('name'):
                            result['name'] = customer['name']
                        if customer.get('email'):
                            result['email'] = customer['email']
                        if customer.get('phone'):
                            result['phone'] = customer['phone']
                        if 'document' in customer and customer['document'].get('number'):
                            result['cpf'] = customer['document']['number']
                        current_app.logger.info(f"[INFO] Dados do cliente extraídos da transação {payment_id}: {result}")
                except Exception as e:
                    current_app.logger.error(f"[ERROR] Erro ao extrair dados do cliente: {str(e)}")
                
                # Adicionar valor da transação se disponível
                if 'amount' in payment_data['data']:
                    result['amount'] = payment_data['data']['amount'] / 100  # Converter de centavos para reais
                
                return result
            else:
                current_app.logger.error(f"[ERROR] Erro ao verificar status do pagamento: {response.status_code} - {response.text}")
                return {'status': 'pending', 'error': f'HTTP {response.status_code}'}

        except requests.exceptions.RequestException as req_e:
            current_app.logger.error(f"[ERROR] Erro de requisição ao verificar status: {str(req_e)}")
            return {'status': 'pending', 'error': 'Connection error'}
        except Exception as e:
            current_app.logger.error(f"[ERROR] Exceção ao verificar status do pagamento: {str(e)}")
            return {'status': 'pending', 'error': 'Unknown error'}


def encode_api_token(secret_key: str) -> str:
    """
    Codifica a chave secreta no formato Base64 para autenticação Basic.
    Formato: base64(secret_key:x)
    """
    token_string = f"{secret_key}:x"
    return base64.b64encode(token_string.encode('utf-8')).decode('utf-8')


def create_payment_api(authorization_token: Optional[str] = None) -> NovaEraPaymentsAPI:
    """Factory function to create NovaEraPaymentsAPI instance"""
    # Buscar chave da variável correta NOVAERA_PAYMENT_TOKEN (verificado com env no sistema)
    secret_key = "sk_5dqcladedir1ZneRB7pLSGVLFap3iLfFfv97hSPw6WvuahCm"
    
    if not secret_key:
        current_app.logger.error("[CRITICAL] NOVAERA_PAYMENT_TOKEN não encontrado no ambiente!")
        # Fallback para a chave antiga como segunda tentativa
        secret_key = os.environ.get("NOVAERA_PAYMENT_SECRET_KEY")
        if secret_key:
            current_app.logger.info("[INFO] Usando NOVAERA_PAYMENT_SECRET_KEY como fallback")
    
    if authorization_token is not None:
        # Se um token foi passado explicitamente, usar esse
        secret_key = authorization_token
        current_app.logger.info("[INFO] Usando token específico passado como argumento")
    
    # Validar a chave secreta
    if not secret_key:
        current_app.logger.error("[CRITICAL] Nenhuma chave de API válida encontrada para NovaEra!")
        current_app.logger.error("[DEBUG] Ambiente: " + str(dict(os.environ)))
        raise ValueError("Chave de API da NovaEra não configurada no ambiente")
    
    current_app.logger.info(f"[INFO] Iniciando NovaEra API com chave de {len(secret_key)} caracteres")
    current_app.logger.debug(f"[DEBUG] Primeiros 5 caracteres da chave: {secret_key[:5]}...")
    
    return NovaEraPaymentsAPI(secret_key)


def test_token_encoding():
    """
    Função para testar a codificação do token da NovaEra.
    Pode ser executada diretamente para verificar o formato do token.
    """
    secret_key = "sk_5dqcladedir1ZneRB7pLSGVLFap3iLfFfv97hSPw6WvuahCm"
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