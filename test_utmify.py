"""
Script para testar a integração com a Utmify diretamente.
Este script testa o envio de uma venda fictícia e a atualização de seu status.
"""
import json
import random
import time
from datetime import datetime

from utmify_integration import send_order_to_utmify, update_order_status_in_utmify

def generate_test_order():
    """Gera dados de teste para uma venda"""
    transaction_id = f"TEST-{int(time.time())}-{random.randint(1000, 9999)}"
    
    return {
        'transaction_id': transaction_id,
        'customer_name': 'Cliente Teste',
        'customer_email': 'cliente.teste@example.com',
        'customer_document': '12345678909',  # CPF fictício
        'product_name': 'Mounjaro (Tirzepatida) 5mg - Teste',
        'product_price_cents': 19790,  # R$ 197,90 em centavos
        'utm_params': {
            'utm_source': 'facebook',
            'utm_campaign': 'campanha_teste|123456',
            'utm_medium': 'cpc|789012',
            'utm_content': 'ad_teste|345678',
            'utm_term': 'feed'
        }
    }

def test_utmify_integration():
    """Testa o fluxo completo da integração com a Utmify"""
    print("\n===== TESTE DE INTEGRAÇÃO COM UTMIFY =====\n")
    
    # 1. Gerar dados de teste
    test_data = generate_test_order()
    print(f"Dados de teste gerados: {json.dumps(test_data, indent=2)}")
    
    # 2. Enviar venda para a Utmify
    print("\n----- Enviando venda para Utmify -----")
    order_result = send_order_to_utmify(
        transaction_id=test_data['transaction_id'],
        customer_name=test_data['customer_name'],
        customer_email=test_data['customer_email'],
        customer_document=test_data['customer_document'],
        product_name=test_data['product_name'],
        product_price_cents=test_data['product_price_cents'],
        utm_params=test_data['utm_params']
    )
    
    print(f"Resultado do envio: {json.dumps(order_result, indent=2)}")
    
    if not order_result['success']:
        print("❌ Erro ao enviar venda para Utmify")
        return
    
    print("✅ Venda enviada com sucesso para Utmify")
    
    # 3. Simular uma pausa para demonstrar o fluxo do processo
    print("\nAguardando 2 segundos para simular o tempo de processamento...\n")
    time.sleep(2)
    
    # 4. Atualizar status da venda para "pago"
    print("----- Atualizando status para 'pago' -----")
    approved_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    update_result = update_order_status_in_utmify(
        transaction_id=test_data['transaction_id'],
        status='paid',
        approved_date=approved_date
    )
    
    print(f"Resultado da atualização: {json.dumps(update_result, indent=2)}")
    
    if not update_result['success']:
        print("❌ Erro ao atualizar status da venda na Utmify")
        return
    
    print("✅ Status da venda atualizado com sucesso para 'pago'")
    
    # 5. Simular outra pausa para demonstrar o fluxo do processo
    print("\nAguardando 2 segundos para simular o tempo de processamento...\n")
    time.sleep(2)
    
    # 6. Atualizar status da venda para "cancelado" (apenas para teste)
    print("----- Atualizando status para 'cancelado' (apenas para teste) -----")
    
    cancel_result = update_order_status_in_utmify(
        transaction_id=test_data['transaction_id'],
        status='cancelled'
    )
    
    print(f"Resultado do cancelamento: {json.dumps(cancel_result, indent=2)}")
    
    if not cancel_result['success']:
        print("❌ Erro ao cancelar venda na Utmify")
        return
    
    print("✅ Status da venda atualizado com sucesso para 'cancelado'")
    
    print("\n===== TESTE COMPLETO =====")

if __name__ == "__main__":
    test_utmify_integration()