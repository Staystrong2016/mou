"""
Arquivo de exemplo de como utilizar o middleware RequestAnalyzer nas rotas do Flask.
Este arquivo serve apenas como documentação e não precisa ser importado.
"""

from flask import Flask, render_template, g
from request_analyzer import register_request_analyzer, is_from_social_ad, is_mobile, get_ad_source

# Exemplo de aplicação Flask com o middleware registrado
app = Flask(__name__)
register_request_analyzer(app)

# Exemplo de rota que usa as informações do middleware
@app.route('/exemplo')
def exemplo():
    # Verificar se veio de anúncio social
    if is_from_social_ad():
        # Tratamento especial para usuários vindos de anúncios
        ad_source = get_ad_source()  # instagram_ads, facebook_ads, etc.
        # Podemos registrar métricas, adicionar parâmetros ao template, etc.
        return render_template('exemplo.html', 
                              from_ad=True, 
                              ad_source=ad_source,
                              show_special_offer=True)

    # Verificar se é mobile
    if is_mobile():
        # Tratamento especial para usuários mobile
        return render_template('exemplo.html', 
                              is_mobile=True,
                              show_mobile_version=True)

    # Acesso regular (direto, não social, não mobile)
    return render_template('exemplo.html', 
                          from_ad=False,
                          is_mobile=False)

# Exemplo de rota que acessa diretamente o objeto g
@app.route('/advanced')
def advanced():
    # Todas as informações de análise estão disponíveis no objeto g
    context = {
        'is_mobile': g.is_mobile if hasattr(g, 'is_mobile') else False,
        'is_from_social_ad': g.is_from_social_ad if hasattr(g, 'is_from_social_ad') else False,
        'ad_source': g.ad_source if hasattr(g, 'ad_source') else 'orgânico',
        'is_bot': g.is_bot if hasattr(g, 'is_bot') else False,
        
        # Os dados completos também estão disponíveis
        'user_source': g.user_source if hasattr(g, 'user_source') else {},
    }
    
    return render_template('advanced.html', **context)

# Exemplo de como implementar uma rota específica para bot (apenas em desenvolvimento)
@app.route('/bot-test')
def bot_test():
    # Os bots normalmente seriam redirecionados para g1.globo.com pelo middleware
    # Mas em desenvolvimento (DEVELOPING=true) podemos testá-los
    is_bot = g.is_bot if hasattr(g, 'is_bot') else False
    
    if is_bot:
        return render_template('bot_detected.html')
    else:
        return render_template('human_detected.html')