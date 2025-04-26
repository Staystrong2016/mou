from flask import render_template, request, jsonify
from app import app
from flask import current_app

@app.route('/anvisa')
@app.route('/anvisa/')
def anvisa():
    """Página principal do site da ANVISA sobre o produto Monjauros"""
    try:
        current_app.logger.info("[PROD] Acessando página da ANVISA")
        return render_template('anvisa.html')
    except Exception as e:
        current_app.logger.error(f"[PROD] Erro ao acessar página da ANVISA: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500
