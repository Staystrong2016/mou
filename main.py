from dotenv import load_dotenv
import os
import logging
from app import app
from request_analyzer import register_request_analyzer

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()



# Registrar middleware de análise de requisições
register_request_analyzer(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
