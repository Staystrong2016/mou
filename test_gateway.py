import os
import sys
from flask import Flask

print(f"GATEWAY_CHOICE = {os.environ.get('GATEWAY_CHOICE', 'não definido')}")

try:
    # Criar uma aplicação Flask mock para o contexto
    app = Flask(__name__)
    
    # Definir uma chave mock para teste
    os.environ['FOR4PAYMENTS_SECRET_KEY'] = 'chave_teste_mock'
    os.environ['NOVAERA_AUTHORIZATION_TOKEN'] = 'token_teste_mock'
    
    # Usar o contexto da aplicação para o teste
    with app.app_context():
        from payment_gateway import get_payment_gateway
        gateway = get_payment_gateway()
        print(f"Gateway selecionado: {type(gateway).__name__}")
except Exception as e:
    print(f"Erro: {str(e)}")
    if "FOR4PAYMENTS_SECRET_KEY não configurada" in str(e):
        print("Necessário configurar FOR4PAYMENTS_SECRET_KEY")
    sys.exit(1)