"""
Script para monitorar o estado atual das estruturas de dados de segurança.
Útil para administradores verificarem o estado do sistema e diagnosticar problemas.
"""

import json
from datetime import datetime
from transaction_tracker import (
    TRANSACTION_ATTEMPTS, 
    CLIENT_DATA_TRACKING, 
    NAME_TRANSACTION_COUNT,
    CPF_TRANSACTION_COUNT,
    PHONE_TRANSACTION_COUNT,
    BANNED_IPS,
    BLOCKED_NAMES,
    cleanup_transaction_tracking
)

def format_datetime(dt):
    """Format datetime object for display"""
    if not isinstance(dt, datetime):
        return str(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def dict_to_json(d):
    """Convert dict with datetime values to JSON-friendly format"""
    return json.dumps(d, default=format_datetime, indent=2)

def show_ips_summary():
    """Show summary of IP tracking"""
    print("\n===== IPs Banidos =====")
    if not BANNED_IPS:
        print("Nenhum IP banido no momento.")
    else:
        print(f"Total de IPs banidos: {len(BANNED_IPS)}")
        for ip, ban_until in BANNED_IPS.items():
            print(f"  IP: {ip} - Banido até: {format_datetime(ban_until)}")
    
    print("\n===== Tentativas de Transação por IP =====")
    if not TRANSACTION_ATTEMPTS:
        print("Nenhuma transação sendo rastreada no momento.")
    else:
        print(f"Total de IPs rastreados: {len(TRANSACTION_ATTEMPTS)}")
        for ip, transactions in TRANSACTION_ATTEMPTS.items():
            print(f"  IP: {ip} - {len(transactions)} transações diferentes")
            for tx_hash, tx_data in list(transactions.items())[:5]:  # Mostrar apenas as 5 primeiras
                print(f"    Hash: {tx_hash[:8]}... - Tentativas: {tx_data['attempts']} - Última: {format_datetime(tx_data['last_attempt'])}")
            if len(transactions) > 5:
                print(f"    ... e mais {len(transactions) - 5} transações")

def show_client_data_summary():
    """Show summary of client data tracking"""
    print("\n===== Rastreamento Global de Clientes =====")
    if not CLIENT_DATA_TRACKING:
        print("Nenhum cliente sendo rastreado globalmente no momento.")
    else:
        print(f"Total de clientes rastreados: {len(CLIENT_DATA_TRACKING)}")
        for client_hash, client_data in CLIENT_DATA_TRACKING.items():
            ip_count = len(client_data['ips'])
            print(f"  Cliente: {client_data.get('first_name', 'Desconhecido')} - Hash: {client_hash[:8]}...")
            print(f"    IPs usados: {ip_count} - Tentativas: {client_data['attempts']} - Última: {format_datetime(client_data['last_attempt'])}")

def show_name_tracking():
    """Show summary of name tracking"""
    print("\n===== Contagem de Transações por Nome =====")
    if not NAME_TRANSACTION_COUNT:
        print("Nenhum nome sendo rastreado no momento.")
    else:
        print(f"Total de nomes rastreados: {len(NAME_TRANSACTION_COUNT)}")
        # Ordenar por contagem (decrescente)
        sorted_names = sorted(NAME_TRANSACTION_COUNT.items(), key=lambda x: x[1]['count'], reverse=True)
        for name, data in sorted_names[:10]:  # Mostrar apenas os 10 primeiros
            print(f"  Nome: {name} - Transações: {data['count']} - Última: {format_datetime(data['last_attempt'])}")
        if len(NAME_TRANSACTION_COUNT) > 10:
            print(f"  ... e mais {len(NAME_TRANSACTION_COUNT) - 10} nomes")

def show_cpf_tracking():
    """Show summary of CPF tracking"""
    print("\n===== Contagem de Transações por CPF =====")
    if not CPF_TRANSACTION_COUNT:
        print("Nenhum CPF sendo rastreado no momento.")
    else:
        print(f"Total de CPFs rastreados: {len(CPF_TRANSACTION_COUNT)}")
        # Ordenar por contagem (decrescente)
        sorted_cpfs = sorted(CPF_TRANSACTION_COUNT.items(), key=lambda x: x[1]['count'], reverse=True)
        for cpf, data in sorted_cpfs[:10]:  # Mostrar apenas os 10 primeiros
            # Mascarar o CPF por segurança
            masked_cpf = cpf[:3] + "*****" + cpf[-2:] if len(cpf) >= 5 else cpf
            print(f"  CPF: {masked_cpf} - Transações: {data['count']} - Última: {format_datetime(data['last_attempt'])}")
        if len(CPF_TRANSACTION_COUNT) > 10:
            print(f"  ... e mais {len(CPF_TRANSACTION_COUNT) - 10} CPFs")

def show_phone_tracking():
    """Show summary of phone tracking"""
    print("\n===== Contagem de Transações por Telefone =====")
    if not PHONE_TRANSACTION_COUNT:
        print("Nenhum telefone sendo rastreado no momento.")
    else:
        print(f"Total de telefones rastreados: {len(PHONE_TRANSACTION_COUNT)}")
        # Ordenar por contagem (decrescente)
        sorted_phones = sorted(PHONE_TRANSACTION_COUNT.items(), key=lambda x: x[1]['count'], reverse=True)
        for phone, data in sorted_phones[:10]:  # Mostrar apenas os 10 primeiros
            # Mascarar o telefone por segurança
            masked_phone = phone[:3] + "*****" + phone[-2:] if len(phone) >= 5 else phone
            print(f"  Telefone: {masked_phone} - Transações: {data['count']} - Última: {format_datetime(data['last_attempt'])}")
        if len(PHONE_TRANSACTION_COUNT) > 10:
            print(f"  ... e mais {len(PHONE_TRANSACTION_COUNT) - 10} telefones")

def show_blocked_names():
    """Show list of blocked names"""
    print("\n===== Nomes Bloqueados =====")
    if not BLOCKED_NAMES:
        print("Nenhum nome na lista de bloqueio.")
    else:
        print(f"Total de nomes bloqueados: {len(BLOCKED_NAMES)}")
        for name in BLOCKED_NAMES:
            print(f"  • {name}")

def show_recommended_actions():
    """Show recommended actions based on current state"""
    print("\n===== Ações Recomendadas =====")
    
    # Verificar IPs banidos
    if BANNED_IPS:
        print("✓ Sistema tem IPs banidos. Monitore para verificar a eficácia das proteções.")
    else:
        print("ℹ️ Nenhum IP banido. O sistema está funcionando normalmente ou ainda não detectou abusos.")
    
    # Verificar contagens próximas do limite
    name_near_limit = [name for name, data in NAME_TRANSACTION_COUNT.items() if data['count'] >= 15]
    cpf_near_limit = [cpf for cpf, data in CPF_TRANSACTION_COUNT.items() if data['count'] >= 15]
    phone_near_limit = [phone for phone, data in PHONE_TRANSACTION_COUNT.items() if data['count'] >= 15]
    
    if name_near_limit or cpf_near_limit or phone_near_limit:
        print("⚠️ Alguns usuários estão próximos do limite de transações:")
        if name_near_limit:
            print(f"  - {len(name_near_limit)} nomes com 15+ transações")
        if cpf_near_limit:
            print(f"  - {len(cpf_near_limit)} CPFs com 15+ transações")
        if phone_near_limit:
            print(f"  - {len(phone_near_limit)} telefones com 15+ transações")
    else:
        print("✓ Nenhum usuário próximo dos limites de transação.")
    
    # Verificar possíveis ataques com múltiplos IPs
    multi_ip_clients = [client for client, data in CLIENT_DATA_TRACKING.items() if len(data['ips']) >= 3]
    if multi_ip_clients:
        print(f"⚠️ Detectados {len(multi_ip_clients)} clientes utilizando 3 ou mais IPs diferentes.")
        print("   Isso pode indicar tentativa de ataque usando múltiplos proxies.")
    else:
        print("✓ Nenhum cliente usando múltiplos IPs de forma suspeita.")

def show_cleanup_stats():
    """Run cleanup and show stats before/after"""
    print("\n===== Limpeza de Dados Expirados =====")
    print("Estado atual:")
    print(f"  IPs banidos: {len(BANNED_IPS)}")
    print(f"  IPs rastreados: {len(TRANSACTION_ATTEMPTS)}")
    print(f"  Clientes rastreados: {len(CLIENT_DATA_TRACKING)}")
    print(f"  Nomes rastreados: {len(NAME_TRANSACTION_COUNT)}")
    print(f"  CPFs rastreados: {len(CPF_TRANSACTION_COUNT)}")
    print(f"  Telefones rastreados: {len(PHONE_TRANSACTION_COUNT)}")
    
    # Executar limpeza
    print("\nExecutando limpeza de dados expirados...")
    try:
        # Patch para execução fora do contexto Flask
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("app")
        
        # Criar mock de current_app para a função de limpeza
        class MockApp:
            def __init__(self):
                self.logger = logger
                
        import flask
        original_current_app = None
        if hasattr(flask, 'current_app'):
            original_current_app = flask.current_app
            
        flask.current_app = MockApp()
        
        # Executar limpeza
        cleanup_transaction_tracking()
        
        # Restaurar current_app
        if original_current_app is not None:
            flask.current_app = original_current_app
            
    except Exception as e:
        print(f"Erro ao executar limpeza: {str(e)}")
        print("Execute este script no contexto da aplicação Flask para executar a limpeza.")
    
    print("\nEstatísticas após tentativa de limpeza:")
    print(f"  IPs banidos: {len(BANNED_IPS)}")
    print(f"  IPs rastreados: {len(TRANSACTION_ATTEMPTS)}")
    print(f"  Clientes rastreados: {len(CLIENT_DATA_TRACKING)}")
    print(f"  Nomes rastreados: {len(NAME_TRANSACTION_COUNT)}")
    print(f"  CPFs rastreados: {len(CPF_TRANSACTION_COUNT)}")
    print(f"  Telefones rastreados: {len(PHONE_TRANSACTION_COUNT)}")

def main():
    """Main function to run the monitor"""
    print("===== MONITOR DE SEGURANÇA DO SISTEMA =====")
    print(f"Data e hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Mostrar resumo de cada estrutura de dados
    show_ips_summary()
    show_client_data_summary()
    show_name_tracking()
    show_cpf_tracking()
    show_phone_tracking()
    show_blocked_names()
    
    # Mostrar ações recomendadas
    show_recommended_actions()
    
    # Mostrar estatísticas de limpeza
    show_cleanup_stats()
    
    print("\n===== FIM DO RELATÓRIO =====")

if __name__ == "__main__":
    # Simular contexto da aplicação Flask
    try:
        import flask
        from app import app
        with app.app_context():
            main()
    except ImportError:
        print("AVISO: Executando fora do contexto Flask. Alguns recursos podem não funcionar corretamente.")
        try:
            main()
        except Exception as e:
            print(f"Erro ao executar o monitor: {str(e)}")
            print("Execute este script no contexto da aplicação Flask para funcionalidade completa.")