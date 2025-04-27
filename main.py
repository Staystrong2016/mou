from dotenv import load_dotenv
import os
import logging
import sys
from app import app
from request_analyzer import register_request_analyzer

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Log para verificar o ambiente
print(f"Iniciando aplicação em ambiente: {'PRODUÇÃO' if os.environ.get('DYNO') else 'DESENVOLVIMENTO'}")
print(f"Python version: {sys.version}")
print(f"Caminho da aplicação: {os.path.dirname(os.path.abspath(__file__))}")

# Registrar middleware de análise de requisições
register_request_analyzer(app)
print("Middleware de análise de requisições registrado com sucesso!")

# Log para debug
app.logger.info("Aplicação inicializada com middleware de Request Analyzer")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
