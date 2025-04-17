import random
import requests
import time
import json
import string
from concurrent.futures import ThreadPoolExecutor

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# URL do servidor de teste (pode ser local ou remoto)
BASE_URL = "http://localhost:5000"

def generate_random_string(length=8):
    """Gera uma string aleatória de letras e dígitos"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_random_cpf():
    """Gera um CPF aleatório (apenas para testes, não um CPF válido)"""
    return ''.join(random.choices(string.digits, k=11))

def generate_random_phone():
    """Gera um número de telefone aleatório"""
    return f"55{random.randint(11, 99)}{random.randint(900000000, 999999999)}"

def create_payment(name, cpf, phone=None):
    """Tenta criar um pagamento usando a API"""
    payment_data = {
        "nome": name,  # Adaptado para os nomes de campos esperados pela rota comprar-livro
        "cpf": cpf,
        "telefone": phone if phone else generate_random_phone()
    }
    
    try:
        # Tentar fazer pagamento diretamente (para testes locais, podemos ignorar a autenticação)
        response = requests.post(
            f"{BASE_URL}/comprar-livro",  # Usamos esta rota que também chama o rastreador de transações
            json=payment_data,
            headers={
                "Content-Type": "application/json", 
                "Referer": BASE_URL
            }
        )
        return response
    except Exception as e:
        print(f"Erro ao criar pagamento: {str(e)}")
        return None

def test_name_limit():
    """
    Testa se o sistema bloqueia após 20 transações com o mesmo nome,
    mesmo usando CPFs diferentes
    """
    print(f"\n{Colors.HEADER}Teste de limite por nome (20 transações){Colors.ENDC}")
    
    # Usar um nome único para este teste
    unique_name = f"João Teste {generate_random_string()}"
    print(f"Usando nome: {unique_name}")
    
    success_count = 0
    blocked_count = 0
    
    for i in range(22):  # Tentamos 22 vezes (apenas 2 além do limite)
        # Gerar um CPF aleatório para cada tentativa
        random_cpf = generate_random_cpf()
        
        response = create_payment(unique_name, random_cpf)
        
        if not response:
            print(f"Falha na requisição {i+1}")
            continue
            
        if response.status_code == 200:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] Pagamento criado com sucesso{Colors.ENDC}")
        elif response.status_code == 429:  # Código esperado para rate limiting
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] Bloqueado: {response.json().get('error', 'Erro desconhecido')}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}[{i+1}] Erro: {response.status_code} - {response.text}{Colors.ENDC}")
            
        # Pausa maior para evitar ser pego pelo rate limiting global
        time.sleep(0.5)
    
    print(f"\nResultado do teste de limite por nome:")
    print(f"Transações bem-sucedidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 2 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está bloqueando corretamente após ~20 transações.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está bloqueando corretamente após 20 transações.{Colors.ENDC}")
        return False

def test_cpf_limit():
    """
    Testa se o sistema bloqueia após 20 transações com o mesmo CPF,
    mesmo usando nomes diferentes
    """
    print(f"\n{Colors.HEADER}Teste de limite por CPF (20 transações){Colors.ENDC}")
    
    # Usar um CPF único para este teste
    unique_cpf = generate_random_cpf()
    print(f"Usando CPF: {unique_cpf}")
    
    success_count = 0
    blocked_count = 0
    
    for i in range(22):  # Tentamos 22 vezes (apenas 2 além do limite)
        # Gerar um nome aleatório para cada tentativa
        random_name = f"Teste {generate_random_string()}"
        
        response = create_payment(random_name, unique_cpf)
        
        if not response:
            print(f"Falha na requisição {i+1}")
            continue
            
        if response.status_code == 200:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] Pagamento criado com sucesso{Colors.ENDC}")
        elif response.status_code == 429:  # Código esperado para rate limiting
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] Bloqueado: {response.json().get('error', 'Erro desconhecido')}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}[{i+1}] Erro: {response.status_code} - {response.text}{Colors.ENDC}")
            
        # Pausa maior para evitar ser pego pelo rate limiting global
        time.sleep(0.5)
    
    print(f"\nResultado do teste de limite por CPF:")
    print(f"Transações bem-sucedidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 2 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está bloqueando corretamente após ~20 transações.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está bloqueando corretamente após 20 transações.{Colors.ENDC}")
        return False

def test_phone_limit():
    """
    Testa se o sistema bloqueia após 20 transações com o mesmo telefone,
    mesmo usando nomes e CPFs diferentes
    """
    print(f"\n{Colors.HEADER}Teste de limite por telefone (20 transações){Colors.ENDC}")
    
    # Usar um telefone único para este teste
    unique_phone = generate_random_phone()
    print(f"Usando telefone: {unique_phone}")
    
    success_count = 0
    blocked_count = 0
    
    for i in range(22):  # Tentamos 22 vezes (apenas 2 além do limite)
        # Gerar um nome e CPF aleatórios para cada tentativa
        random_name = f"Teste {generate_random_string()}"
        random_cpf = generate_random_cpf()
        
        response = create_payment(random_name, random_cpf, unique_phone)
        
        if not response:
            print(f"Falha na requisição {i+1}")
            continue
            
        if response.status_code == 200:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] Pagamento criado com sucesso{Colors.ENDC}")
        elif response.status_code == 429:  # Código esperado para rate limiting
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] Bloqueado: {response.json().get('error', 'Erro desconhecido')}{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}[{i+1}] Erro: {response.status_code} - {response.text}{Colors.ENDC}")
            
        # Pausa maior para evitar ser pego pelo rate limiting global
        time.sleep(0.5)
    
    print(f"\nResultado do teste de limite por telefone:")
    print(f"Transações bem-sucedidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 2 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está bloqueando corretamente após ~20 transações.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está bloqueando corretamente após 20 transações.{Colors.ENDC}")
        return False

def run_all_tests():
    """Executa todos os testes em sequência"""
    print(f"{Colors.BOLD}{Colors.HEADER}Iniciando testes de limite de transações por cliente{Colors.ENDC}")
    
    tests_passed = 0
    tests_failed = 0
    
    # Teste de limite por nome
    if test_name_limit():
        tests_passed += 1
    else:
        tests_failed += 1
    
    # Teste de limite por CPF
    if test_cpf_limit():
        tests_passed += 1
    else:
        tests_failed += 1
    
    # Teste de limite por telefone
    if test_phone_limit():
        tests_passed += 1
    else:
        tests_failed += 1
    
    # Resumo final
    print(f"\n{Colors.BOLD}Resultado Final:{Colors.ENDC}")
    print(f"Testes passados: {tests_passed}/3")
    print(f"Testes falhos: {tests_failed}/3")
    
    if tests_failed == 0:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ Todos os testes passaram! O sistema está configurado corretamente.{Colors.ENDC}")
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}✗ Alguns testes falharam. Revise a implementação dos limites.{Colors.ENDC}")

if __name__ == "__main__":
    run_all_tests()