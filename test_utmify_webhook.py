"""
Script para testar o webhook da Utmify.
Este script simula o recebimento de um pagamento confirmado e envia para o endpoint /utmify-webhook.
"""
import json
import requests
import time
import random
from datetime import datetime, timedelta

# URL base do servidor no Replit
BASE_URL = "https://8dd09415-4474-4643-9048-f5e50eeca860-00-2etefm45q69jz.kirk.replit.dev"

def generate_test_payment_webhook():
    """Gera dados de teste simulando um pagamento confirmado"""
    order_id = f"TEST-{int(time.time())}-{random.randint(1000, 9999)}"
    now = datetime.now()
    # Garantir que a data seja atual, pois a API rejeita datas antigas
    five_min_ago = now - timedelta(minutes=5)
    
    return {
        "orderId": order_id,
        "status": "PAID",
        "createdAt": five_min_ago.strftime("%Y-%m-%d %H:%M:%S"),
        "paidAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "customer": {
            "name": "Cliente Teste Webhook",
            "email": "cliente.webhook@example.com",
            "document": {
                "type": "CPF",
                "number": "12345678909"
            }
        },
        "items": [
            {
                "id": f"item_{order_id}",
                "title": "Mounjaro (Tirzepatida) 5mg - 4 Canetas",
                "quantity": 1,
                "unitPrice": 19790
            }
        ],
        "amount": 19790,
        "fee": {
            "fixedAmount": 250,
            "netAmount": 19540
        },
        "trackingParameters": {
            "utm_source": "facebook",
            "utm_campaign": "campanha_teste|123456",
            "utm_medium": "cpc|789012",
            "utm_content": "ad_teste|345678",
            "utm_term": "feed"
        }
    }

def test_webhook():
    """Testa o webhook enviando uma requisição para o endpoint"""
    print("\n===== TESTE DO WEBHOOK UTMIFY =====\n")
    
    # Gerar dados de teste
    webhook_data = generate_test_payment_webhook()
    print(f"Dados do webhook gerados: {json.dumps(webhook_data, indent=2)}")
    
    # Enviar para o endpoint de webhook
    webhook_url = f"{BASE_URL}/utmify-webhook"
    print(f"\nEnviando requisição para: {webhook_url}")
    
    try:
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            webhook_url,
            headers=headers,
            json=webhook_data
        )
        
        print(f"\nResposta do servidor (status code: {response.status_code}):")
        
        try:
            response_json = response.json()
            print(json.dumps(response_json, indent=2))
        except:
            print(response.text)
        
        if response.status_code == 200:
            print("\n✅ Teste do webhook concluído com sucesso!")
        else:
            print("\n❌ Erro no teste do webhook.")
            
    except Exception as e:
        print(f"\n❌ Erro ao enviar requisição: {str(e)}")
    
    print("\n===== FIM DO TESTE =====")

if __name__ == "__main__":
    test_webhook()