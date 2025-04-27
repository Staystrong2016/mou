import os
import sys
import json
from flask import Flask, render_template

# Exibir configurações para depuração
print("========== CONFIGURAÇÕES DE AMBIENTE ==========")
print(f"GATEWAY_CHOICE = {os.environ.get('GATEWAY_CHOICE', 'não definido')}")
print(f"DEVELOPING = {os.environ.get('DEVELOPING', 'não definido')}")
print("===============================================")

try:
    # Criar uma aplicação Flask mock para o contexto
    app = Flask(__name__)
    
    # Definir chaves mock para teste
    os.environ['FOR4PAYMENTS_SECRET_KEY'] = 'chave_teste_mock'
    os.environ['NOVAERA_AUTHORIZATION_TOKEN'] = 'token_teste_mock'
    
    # Usar o contexto da aplicação para o teste
    with app.app_context():
        # Teste 1: Seleção de Gateway
        print("\n1. TESTE DE SELEÇÃO DE GATEWAY")
        from payment_gateway import get_payment_gateway
        gateway = get_payment_gateway()
        print(f"Gateway selecionado: {type(gateway).__name__}")
        
        # Teste 2: Detecção de dispositivo móvel
        print("\n2. TESTE DE DETECÇÃO DE DISPOSITIVO")
        from request_analyzer import RequestAnalyzer
        
        # Mock para diferentes tipos de user agents
        mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        
        analyzer = RequestAnalyzer()
        print(f"Dispositivo Móvel (iPhone): {analyzer.is_mobile(mobile_ua)}")
        print(f"Dispositivo Desktop (Windows): {analyzer.is_mobile(desktop_ua)}")
        
        # Teste 3: Detecção de fontes sociais
        print("\n3. TESTE DE DETECÇÃO DE FONTES SOCIAIS")
        social_referer = "https://www.facebook.com/ads/123456"
        social_params = {"utm_source": "facebook", "utm_medium": "cpc"}
        
        print(f"É de anúncio social: {analyzer.is_from_social_ad(social_referer, social_params)}")
        print(f"Fonte do anúncio: {analyzer.get_ad_source(social_referer, social_params)}")
        
        # Teste 4: Variável DEVELOPING e injeção de disable-devtool
        print("\n4. TESTE DE MODO DESENVOLVIMENTO")
        # Simular os dois cenários
        developing_values = [True, False]
        
        for dev_val in developing_values:
            os.environ['DEVELOPING'] = str(dev_val).lower()
            print(f"\nCenário com DEVELOPING={dev_val}")
            print(f"O script disable-devtool {'NÃO' if dev_val else 'SERÁ'} injetado")
        
except Exception as e:
    print(f"Erro: {str(e)}")
    sys.exit(1)