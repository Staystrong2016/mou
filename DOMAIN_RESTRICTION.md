# Restrição de Domínio e Proteção de Links de Ofertas

Esta documentação descreve a implementação do sistema de proteção de links de ofertas e restrição de domínio no aplicativo web.

## Objetivo

O sistema visa proteger links de ofertas para que:

1. Apenas acessos autorizados (com `adsetid` válido) possam acessar as páginas de oferta
2. Após a validação, o usuário possa navegar livremente no site sem precisar fornecer o `adsetid` novamente
3. O parâmetro `adsetid` seja removido da URL após a validação por questões de segurança
4. Acessos não autorizados sejam redirecionados para um URL externo definido

## Implementação

A proteção é implementada através do decorador `confirm_genuity` no arquivo `request_analyzer.py`. Este decorador:

1. Verifica se o valor de `adsetid` na URL corresponde ao valor da variável de ambiente `OFFER_SECRET`
2. Se corresponder:
   - Remove o parâmetro `adsetid` da URL
   - Define um cookie chamado `verified_offer` (configurável)
   - Redireciona para a versão limpa da URL
3. Em visitas subsequentes:
   - Verifica a presença do cookie de verificação
   - Permite o acesso se o cookie for válido, mesmo sem o parâmetro `adsetid`
4. Se não corresponder ou não estiver presente:
   - Redireciona para um URL externo definido

## Uso

Para proteger uma rota:

```python
from request_analyzer import confirm_genuity

@app.route('/rota-protegida')
@confirm_genuity()
def rota_protegida():
    # Código da rota
    return render_template('template.html')
```

### Parâmetros Configuráveis

O decorador `confirm_genuity` aceita os seguintes parâmetros:

- `redirect_url` (opcional): URL para redirecionar usuários não autorizados. Padrão: URL do blog de notícias.
- `cookie_name` (opcional): Nome do cookie de verificação. Padrão: "verified_offer".
- `cookie_max_age` (opcional): Duração do cookie em segundos. Padrão: 30 dias.

## Ambiente de Desenvolvimento

Em ambiente de desenvolvimento (quando a variável `DEVELOPING` estiver definida como `true`), o sistema permite o acesso mesmo sem o `adsetid` válido para facilitar os testes.

## Configuração

Certifique-se de definir a variável de ambiente `OFFER_SECRET` com o valor do `adsetid` válido:

```
OFFER_SECRET=seu_valor_secreto_aqui
```

## Considerações de Segurança

1. O valor de `OFFER_SECRET` deve ser mantido em sigilo e nunca compartilhado publicamente
2. O cookie tem duração de 30 dias por padrão, o que significa que a validação do usuário expira após esse período
3. O cookie é configurado com as flags `httponly` e `samesite=Lax` para proteção adicional