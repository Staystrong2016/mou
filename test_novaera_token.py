#!/usr/bin/env python3
"""
Script para testar a codificação do token da NovaEra.
Verifica se o token está sendo codificado corretamente no formato base64(sk_xxx:x).
"""
from novaerapayments import test_token_encoding

if __name__ == "__main__":
    # Executar o teste de codificação
    encoded_token = test_token_encoding()