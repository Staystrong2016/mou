from dotenv import load_dotenv
import os
import logging
import sys
from app import app
from request_analyzer import register_request_analyzer
from facebook_conversion_api import register_facebook_conversion_events

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Se DEVE forçar todas as verificações para permitir mais acessos ao site
force_allow_all = os.environ.get('FORCE_ALLOW_ALL', 'false').lower() == 'true'
if force_allow_all:
    print("!!! ATENÇÃO: Modo de acesso permissivo ativado - todos os acessos serão permitidos !!!")
    os.environ['FORCE_ALLOW_ALL'] = 'true'

# Log para verificar o ambiente
environment = 'PRODUÇÃO' if os.environ.get('DYNO') else 'DESENVOLVIMENTO'
print(f"Iniciando aplicação em ambiente: {environment}")
print(f"Python version: {sys.version}")
print(f"Caminho da aplicação: {os.path.dirname(os.path.abspath(__file__))}")

# Registrar middleware de análise de requisições
register_request_analyzer(app)
print("Middleware de análise de requisições registrado com sucesso!")

# Registrar eventos de conversão do Facebook
register_facebook_conversion_events(app)
print("Eventos de conversão do Facebook registrados com sucesso!")

# Log para debug
app.logger.info("Aplicação inicializada com middleware de Request Analyzer e Eventos de Conversão Facebook")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
