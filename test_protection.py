import os
import requests
import time
import json
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List

# URL base da aplicação
BASE_URL = "http://localhost:5000"  # Altere para o seu URL de produção

# Cabeçalhos comuns para requisições HTTP
COMMON_HEADERS = {
    "Referer": "http://localhost:5000/",
    "Origin": "http://localhost:5000"
}

# Cores para saída formatada
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Buscar token CSRF
def get_csrf_token():
    """Solicita um novo token CSRF do servidor"""
    try:
        response = requests.get(
            f"{BASE_URL}/csrf-token",
            headers=COMMON_HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('csrf_token')
        else:
            print(f"{Colors.FAIL}Erro ao obter token CSRF: {response.status_code}{Colors.ENDC}")
            print(f"Resposta: {response.text}")
            return None
    except Exception as e:
        print(f"{Colors.FAIL}Erro ao solicitar token CSRF: {str(e)}{Colors.ENDC}")
        return None

# Dados de pagamento de teste
TEST_PAYMENT_DATA = {
    "name": "Usuário Teste",
    "cpf": "12345678900",
    "amount": 49.90,
    "email": "teste@email.com",
    "phone": "11987654321"
}

def create_payment():
    """Tenta criar um novo pagamento PIX"""
    try:
        # Obter token CSRF primeiro
        csrf_token = get_csrf_token()
        if not csrf_token:
            return 500, "Falha ao obter token CSRF"
            
        # Preparar cabeçalhos para o token de pagamento
        token_headers = {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf_token,
            **COMMON_HEADERS
        }
            
        # Obter token de pagamento
        token_response = requests.post(
            f"{BASE_URL}/get-payment-token",
            headers=token_headers,
            timeout=5
        )
        
        if token_response.status_code != 200:
            return token_response.status_code, token_response.text
            
        token_data = token_response.json()
        auth_token = token_data.get('auth_token')
        
        # Preparar cabeçalhos para a criação do pagamento
        payment_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}",
            "X-CSRF-Token": csrf_token,
            **COMMON_HEADERS
        }
        
        # Criar pagamento usando os tokens
        response = requests.post(
            f"{BASE_URL}/create-pix-payment", 
            json=TEST_PAYMENT_DATA,
            headers=payment_headers,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Resposta: {response.text}")
        
        return response.status_code, response.text
    except Exception as e:
        print(f"Erro: {str(e)}")
        return 500, str(e)

def test_single_payment():
    """Testa a criação de um único pagamento"""
    print("\n=== Teste Único ===")
    status, response = create_payment()
    
    if status == 200:
        print("✅ Pagamento criado com sucesso!")
    else:
        print(f"❌ Falha ao criar pagamento: {response}")

def test_rate_limiting():
    """Testa o limite de taxa enviando muitas requisições em sequência"""
    print("\n=== Teste de Limite de Taxa ===")
    results = []
    
    for i in range(20):
        print(f"Tentativa {i+1}/20...")
        status, response = create_payment()
        results.append((status, response))
        
        # Pausa curta para não sobrecarregar
        time.sleep(0.5)
    
    # Analisa os resultados
    success = sum(1 for status, _ in results if status == 200)
    rate_limited = sum(1 for status, _ in results if status == 429)
    other_errors = sum(1 for status, _ in results if status not in [200, 429])
    
    print(f"\nResultados:")
    print(f"✅ Sucessos: {success}")
    print(f"🚫 Limitados por taxa: {rate_limited}")
    print(f"❌ Outros erros: {other_errors}")

def test_same_data_blocking():
    """Testa o bloqueio por dados repetidos"""
    print("\n=== Teste de Bloqueio por Dados Repetidos ===")
    
    # Cria várias tentativas com os mesmos dados
    for i in range(10):
        print(f"Tentativa {i+1}/10 com os mesmos dados...")
        status, response = create_payment()
        
        # Se for bloqueado, mostrar a mensagem
        if status != 200:
            try:
                error_data = json.loads(response)
                if 'error' in error_data:
                    print(f"Mensagem: {error_data['error']}")
            except:
                print(f"Resposta: {response}")
                
        time.sleep(1)  # Pausa entre tentativas

def test_concurrent_requests():
    """Testa envio concorrente de muitas requisições"""
    print("\n=== Teste de Requisições Concorrentes ===")
    
    # Número de requisições concorrentes
    num_requests = 10
    
    # Usar ThreadPoolExecutor para enviar requisições em paralelo
    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [executor.submit(create_payment) for _ in range(num_requests)]
        
    # Aguardar todas as requisições terminarem
    results = [future.result() for future in futures]
    
    # Analisa os resultados
    success = sum(1 for status, _ in results if status == 200)
    rate_limited = sum(1 for status, _ in results if status == 429)
    other_errors = sum(1 for status, _ in results if status not in [200, 429])
    
    print(f"\nResultados:")
    print(f"✅ Sucessos: {success}")
    print(f"🚫 Limitados por taxa: {rate_limited}")
    print(f"❌ Outros erros: {other_errors}")

# Gerar dados de cliente aleatórios para simular múltiplos usuários
def generate_random_user() -> Dict[str, Any]:
    """Gera dados aleatórios de usuário para testes"""
    # Lista de nomes para teste
    nomes = ["Maria", "João", "Ana", "Pedro", "Juliana", "Carlos", "Fernanda", "Lucas"]
    sobrenomes = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Costa", "Rodrigues", "Almeida"]
    
    # Gera um CPF aleatório (apenas para testes)
    cpf = ''.join([str(random.randint(0, 9)) for _ in range(11)])
    
    # Gera um email com base no nome
    nome = random.choice(nomes)
    sobrenome = random.choice(sobrenomes)
    email = f"{nome.lower()}.{sobrenome.lower()}{random.randint(1, 999)}@email.com"
    
    # Gera um telefone aleatório
    telefone = f"{random.randint(11, 99)}{random.randint(10000000, 99999999)}"
    
    # Gera um valor aleatório entre 30 e 200 reais
    valor = round(random.uniform(30, 200), 2)
    
    return {
        "name": f"{nome} {sobrenome}",
        "cpf": cpf,
        "email": email,
        "phone": telefone,
        "amount": valor
    }

def test_multi_ip_detection():
    """
    Testa a detecção de ataques usando múltiplos IPs
    
    Este teste simula um cenário onde o mesmo cliente (mesmos dados)
    tenta criar transações a partir de diferentes IPs (proxy attack)
    """
    print(f"\n{Colors.HEADER}=== Teste de Detecção de Ataque Multi-IP ==={Colors.ENDC}")
    
    # Gera um usuário que será usado em todas as solicitações
    fixed_user = generate_random_user()
    print(f"{Colors.BOLD}Usuário de teste:{Colors.ENDC} {fixed_user['name']} (CPF: {fixed_user['cpf']})")
    
    # Lista para armazenar cabeçalhos simulando diferentes IPs
    ip_headers = []
    
    # Gera 5 IPs aleatórios para simular um ataque
    for i in range(5):
        ip = f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
        ip_headers.append({"X-Forwarded-For": ip})
        print(f"IP simulado #{i+1}: {ip}")
    
    # Para cada IP, fazer várias tentativas
    results = []
    block_detected = False
    
    for i, headers in enumerate(ip_headers):
        print(f"\n{Colors.BOLD}Testando com IP #{i+1}{Colors.ENDC}")
        
        # Faz 3 tentativas por IP (total 15 tentativas)
        for attempt in range(3):
            # Obter token CSRF
            csrf_token = get_csrf_token()
            if not csrf_token:
                results.append((500, "Falha ao obter token CSRF"))
                continue
                
            # Obter token de pagamento
            try:
                # Mesclar cabeçalhos simulados com os cabeçalhos comuns
                sim_headers = {
                    **COMMON_HEADERS,
                    **headers  # IP simulados
                }
                
                token_response = requests.post(
                    f"{BASE_URL}/get-payment-token",
                    headers={
                        "Content-Type": "application/json",
                        "X-CSRF-Token": csrf_token,
                        **sim_headers  # Incluir referer e IP simulado
                    },
                    timeout=5
                )
                
                if token_response.status_code != 200:
                    results.append((token_response.status_code, token_response.text))
                    continue
                    
                token_data = token_response.json()
                auth_token = token_data.get('auth_token')
                
                # Criar pagamento usando os tokens e os mesmos dados de usuário
                response = requests.post(
                    f"{BASE_URL}/create-pix-payment", 
                    json=fixed_user,  # Mesmo usuário em todas as tentativas
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {auth_token}",
                        "X-CSRF-Token": csrf_token,
                        **sim_headers  # Incluir referer e IP simulado
                    },
                    timeout=10
                )
                
                status_code = response.status_code
                response_text = response.text
                
                print(f"Tentativa {attempt+1}/3 com IP #{i+1}: {status_code}")
                
                # Verificar se detectou o bloqueio multi-IP
                if status_code != 200:
                    try:
                        response_data = json.loads(response_text)
                        error_msg = response_data.get('error', '')
                        if 'múltiplos IPs' in error_msg or 'múltiplos IP' in error_msg:
                            print(f"{Colors.OKGREEN}✅ Detecção de ataque multi-IP confirmada!{Colors.ENDC}")
                            print(f"   Mensagem: {error_msg}")
                            block_detected = True
                    except:
                        pass
                
                results.append((status_code, response_text))
                
                # Se já detectou o bloqueio, não precisa continuar
                if block_detected:
                    break
                
                # Pequena pausa entre tentativas
                time.sleep(1)
                
            except Exception as e:
                print(f"{Colors.FAIL}Erro: {str(e)}{Colors.ENDC}")
                results.append((500, str(e)))
        
        # Se já detectou o bloqueio, não precisa testar mais IPs
        if block_detected:
            break
    
    # Resumo dos resultados
    success = sum(1 for status, _ in results if status == 200)
    blocked = sum(1 for status, _ in results if status != 200)
    
    print(f"\n{Colors.BOLD}Resultados:{Colors.ENDC}")
    print(f"✅ Transações bem-sucedidas: {success}")
    print(f"🚫 Transações bloqueadas: {blocked}")
    
    if block_detected:
        print(f"{Colors.OKGREEN}✅ TESTE PASSOU: Sistema detectou e bloqueou ataque com múltiplos IPs{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}⚠️ TESTE FALHOU: Sistema não detectou ataque com múltiplos IPs{Colors.ENDC}")

def run_all_tests():
    """Executa todos os testes em sequência"""
    print(f"{Colors.HEADER}🚀 Iniciando testes de proteção anti-bot...{Colors.ENDC}")
    
    # Teste de pagamento único
    test_single_payment()
    
    # Teste de limite de taxa
    test_rate_limiting()
    
    # Teste de bloqueio por dados repetidos
    test_same_data_blocking()
    
    # Teste de requisições concorrentes
    test_concurrent_requests()
    
    # Teste de detecção de ataques multi-IP
    test_multi_ip_detection()
    
    print(f"\n{Colors.OKGREEN}✅ Testes concluídos!{Colors.ENDC}")

if __name__ == "__main__":
    run_all_tests()