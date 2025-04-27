# Request Analyzer Middleware

Este middleware foi criado para analisar requisições e detectar características dos usuários, como:

- Se estão usando dispositivos móveis
- Se vieram de anúncios de redes sociais (Instagram, Facebook, etc.)
- Se são bots ou scrapers
- Se estão usando proxies

## Recursos Principais

- Detecção de dispositivos móveis
- Detecção de referências de redes sociais
- Identificação de origem de anúncios
- Detecção de bots/scrapers
- Bloqueio de bots (redirecionando para g1.globo.com em produção)
- Limitação de taxa por IP
- Cache de análises para melhorar performance

## Como usar

### 1. Configuração Inicial

O middleware já está integrado à aplicação através do arquivo `main.py`. Não é necessária nenhuma configuração adicional.

### 2. Acessando Informações nas Rotas

Você pode acessar as informações detectadas pelo middleware de duas maneiras:

#### Método 1: Usando funções auxiliares

```python
from request_analyzer import is_from_social_ad, is_mobile, get_ad_source

@app.route('/minha-rota')
def minha_rota():
    # Verifica se veio de anúncio social
    if is_from_social_ad():
        # Código específico para usuários de anúncios
        ad_source = get_ad_source()  # instagram_ads, facebook_ads, etc.
        pass
        
    # Verifica se é mobile
    if is_mobile():
        # Código específico para mobile
        pass
        
    return render_template('template.html')
```

#### Método 2: Acessando diretamente o objeto global 'g'

```python
from flask import g

@app.route('/outra-rota')
def outra_rota():
    # Todas as informações estão disponíveis no objeto g
    is_mobile = g.is_mobile if hasattr(g, 'is_mobile') else False
    is_from_ad = g.is_from_social_ad if hasattr(g, 'is_from_social_ad') else False
    ad_source = g.ad_source if hasattr(g, 'ad_source') else 'orgânico'
    is_bot = g.is_bot if hasattr(g, 'is_bot') else False
    
    # Acesso aos dados completos
    user_source = g.user_source if hasattr(g, 'user_source') else {}
    
    return render_template('template.html', 
                          is_mobile=is_mobile,
                          is_from_ad=is_from_ad,
                          ad_source=ad_source)
```

### 3. Desenvolvimento vs Produção

O middleware se comporta de forma diferente em ambientes de desenvolvimento e produção:

- Em **desenvolvimento** (DEVELOPING=true no .env):
  - Bots não são redirecionados
  - Proxies não são detectados (para evitar falsos positivos com a infraestrutura do Replit)

- Em **produção**:
  - Bots são redirecionados para g1.globo.com
  - Proxies são detectados usando múltiplos cabeçalhos

## Personalizando o Middleware

As configurações do middleware estão definidas no objeto `config` da classe `RequestAnalyzer`:

```python
self.config = {
    'detect_mobile': True,
    'detect_social_ads': True,
    'log_all_requests': False,
    'rate_limit_window': 60,  # segundos
    'max_requests': 100,
    'cache_ttl': 15 * 60  # 15 minutos em segundos
}
```

Para modificar estas configurações, você pode editar diretamente o arquivo `request_analyzer.py`.

## Exemplo de Uso

Consulte o arquivo `middleware_example.py` para exemplos de como usar o middleware em suas rotas.