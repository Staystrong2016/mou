from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

from app import app
import anvisa_routes  # Importar rotas adicionais

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
