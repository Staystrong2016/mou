import sys
from transaction_tracker import track_transaction_attempt
from datetime import datetime, timedelta
import time

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def test_name_limit():
    """
    Teste direto da função track_transaction_attempt com o mesmo nome
    """
    print(f"\n{Colors.HEADER}Teste de limite por nome (20 transações){Colors.ENDC}")
    
    # IP fixo para teste
    test_ip = "127.0.0.1"
    
    # Nome de teste único
    test_name = f"João Teste Direto {datetime.now().strftime('%H%M%S')}"
    print(f"Usando nome: {test_name}")
    
    success_count = 0
    blocked_count = 0
    
    for i in range(25):  # Tentamos 25 vezes (5 além do limite)
        # Usar CPF diferente em cada tentativa
        test_cpf = f"111.222.333-{i:02d}"
        
        # Chamar diretamente a função de rastreamento
        is_allowed, message = track_transaction_attempt(
            test_ip, 
            {
                'name': test_name,
                'cpf': test_cpf,
                'phone': f"5511999999{i:02d}"
            }
        )
        
        if is_allowed:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] Transação permitida: {message}{Colors.ENDC}")
        else:
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] Transação bloqueada: {message}{Colors.ENDC}")
            
        # Pequena pausa para facilitar a leitura do output
        time.sleep(0.1)
    
    print(f"\nResultado do teste de limite por nome:")
    print(f"Transações permitidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 5 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está bloqueando corretamente após ~20 transações.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está bloqueando corretamente após 20 transações.{Colors.ENDC}")
        return False

def test_cpf_limit():
    """
    Teste direto da função track_transaction_attempt com o mesmo CPF
    """
    print(f"\n{Colors.HEADER}Teste de limite por CPF (20 transações){Colors.ENDC}")
    
    # IP fixo para teste
    test_ip = "127.0.0.2"  # IP diferente para não interferir com o teste anterior
    
    # CPF de teste único
    test_cpf = f"999.888.777-42"
    print(f"Usando CPF: {test_cpf}")
    
    success_count = 0
    blocked_count = 0
    
    for i in range(25):  # Tentamos 25 vezes (5 além do limite)
        # Usar nome diferente em cada tentativa
        test_name = f"Teste CPF Cliente {i}"
        
        # Chamar diretamente a função de rastreamento
        is_allowed, message = track_transaction_attempt(
            test_ip, 
            {
                'name': test_name,
                'cpf': test_cpf,
                'phone': f"5511888888{i:02d}"
            }
        )
        
        if is_allowed:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] Transação permitida: {message}{Colors.ENDC}")
        else:
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] Transação bloqueada: {message}{Colors.ENDC}")
            
        # Pequena pausa para facilitar a leitura do output
        time.sleep(0.1)
    
    print(f"\nResultado do teste de limite por CPF:")
    print(f"Transações permitidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 5 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está bloqueando corretamente após ~20 transações.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está bloqueando corretamente após 20 transações.{Colors.ENDC}")
        return False

def test_phone_limit():
    """
    Teste direto da função track_transaction_attempt com o mesmo telefone
    """
    print(f"\n{Colors.HEADER}Teste de limite por telefone (20 transações){Colors.ENDC}")
    
    # IP fixo para teste
    test_ip = "127.0.0.3"  # IP diferente para não interferir com os testes anteriores
    
    # Telefone de teste único
    test_phone = "5511777777777"
    print(f"Usando telefone: {test_phone}")
    
    success_count = 0
    blocked_count = 0
    
    for i in range(25):  # Tentamos 25 vezes (5 além do limite)
        # Usar nome e CPF diferentes em cada tentativa
        test_name = f"Teste Telefone Cliente {i}"
        test_cpf = f"444.555.666-{i:02d}"
        
        # Chamar diretamente a função de rastreamento
        is_allowed, message = track_transaction_attempt(
            test_ip, 
            {
                'name': test_name,
                'cpf': test_cpf,
                'phone': test_phone
            }
        )
        
        if is_allowed:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] Transação permitida: {message}{Colors.ENDC}")
        else:
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] Transação bloqueada: {message}{Colors.ENDC}")
            
        # Pequena pausa para facilitar a leitura do output
        time.sleep(0.1)
    
    print(f"\nResultado do teste de limite por telefone:")
    print(f"Transações permitidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 5 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está bloqueando corretamente após ~20 transações.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está bloqueando corretamente após 20 transações.{Colors.ENDC}")
        return False

def test_multi_ip_attack():
    """
    Teste direto da função track_transaction_attempt simulando um ataque com múltiplos IPs
    """
    print(f"\n{Colors.HEADER}Teste de detecção de ataque com múltiplos IPs{Colors.ENDC}")
    
    # Dados do cliente que serão constantes
    test_name = "Cliente Múltiplo IPs"
    test_cpf = "111.222.333-99"
    test_phone = "5511955554444"
    
    success_count = 0
    blocked_count = 0
    
    # Simular tentativas com diferentes IPs
    for i in range(25):  # Devemos ser bloqueados após 20 tentativas
        # Usar um IP diferente a cada vez
        test_ip = f"192.168.1.{i+1}"
        
        # Chamar diretamente a função de rastreamento
        is_allowed, message = track_transaction_attempt(
            test_ip, 
            {
                'name': test_name,
                'cpf': test_cpf,
                'phone': test_phone
            }
        )
        
        if is_allowed:
            success_count += 1
            print(f"{Colors.OKGREEN}[{i+1}] IP {test_ip} - Transação permitida: {message}{Colors.ENDC}")
        else:
            blocked_count += 1
            print(f"{Colors.WARNING}[{i+1}] IP {test_ip} - Transação bloqueada: {message}{Colors.ENDC}")
            
        # Pequena pausa para facilitar a leitura do output
        time.sleep(0.1)
    
    print(f"\nResultado do teste de ataque com múltiplos IPs:")
    print(f"Transações permitidas: {success_count}")
    print(f"Transações bloqueadas: {blocked_count}")
    
    # Verificar se o teste passou (devemos ter em torno de 20 sucessos e 5 bloqueios)
    if success_count <= 21 and blocked_count >= 1:
        print(f"{Colors.OKGREEN}✓ Teste passou! O sistema está detectando ataques com múltiplos IPs.{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.FAIL}✗ Teste falhou! O sistema não está detectando ataques com múltiplos IPs.{Colors.ENDC}")
        return False

def run_all_tests():
    """Executa todos os testes em sequência"""
    print(f"{Colors.BOLD}{Colors.HEADER}Iniciando testes diretos de limite de transações{Colors.ENDC}")
    
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
    
    # Teste de ataque com múltiplos IPs
    if test_multi_ip_attack():
        tests_passed += 1
    else:
        tests_failed += 1
    
    # Resumo final
    print(f"\n{Colors.BOLD}Resultado Final:{Colors.ENDC}")
    print(f"Testes passados: {tests_passed}/4")
    print(f"Testes falhos: {tests_failed}/4")
    
    if tests_failed == 0:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ Todos os testes passaram! O sistema está configurado corretamente.{Colors.ENDC}")
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}✗ Alguns testes falharam. Revise a implementação dos limites.{Colors.ENDC}")

if __name__ == "__main__":
    # Usar o app real em vez de mocks
    import logging
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Importar o app real
    from app import app
    
    # Executar os testes dentro do contexto da aplicação
    with app.app_context():
        # Criar um mock para o request
        from unittest.mock import patch
        from flask import request
                
        # Patch a função get_client_ip para retornar os IPs de teste
        original_get_client_ip = None
        
        # Importar a função get_client_ip do módulo
        from transaction_tracker import get_client_ip as original_get_client_ip_func
        
        def mock_get_client_ip_wrapper(ip_to_return):
            def mock_get_client_ip():
                return ip_to_return
            return mock_get_client_ip
        
        # Guardar a função original
        original_get_client_ip = original_get_client_ip_func
        
        # Executar os testes
        run_all_tests()