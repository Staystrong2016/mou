# Sistema de Proteção contra Ataques de Transação

Este documento descreve o sistema implementado para proteger a API de pagamento For4Payments contra ataques automatizados que tentam gerar múltiplas transações com os mesmos dados.

## Visão Geral

O sistema implementa múltiplas camadas de proteção para evitar que bots ou usuários mal-intencionados abusem da API de pagamento, garantindo a integridade e disponibilidade dos serviços.

## Principais Recursos

1. **Limite por Nome, CPF e Telefone**: Impede que o mesmo cliente (identificado por nome, CPF ou telefone) gere mais de 20 transações em um período de 24 horas.

2. **Limite por IP**: Bloqueia um endereço IP após 5 tentativas de criar transações com os mesmos dados em um período de 24 horas.

3. **Detecção de Ataques com Múltiplos IPs**: Identifica quando um mesmo cliente tenta contornar os limites por IP usando múltiplos endereços IP (proxies).

4. **Banimento Temporário**: IPs detectados como abusivos são banidos por 24 horas.

5. **Limpeza Automática**: Dados de rastreamento expirados são removidos automaticamente para evitar crescimento indefinido das estruturas de dados.

## Estruturas de Dados

- `TRANSACTION_ATTEMPTS`: Rastreia tentativas de transação por IP e hash de dados
- `CLIENT_DATA_TRACKING`: Rastreia clientes globalmente para detectar uso de múltiplos IPs
- `NAME_TRANSACTION_COUNT`: Conta transações por nome
- `CPF_TRANSACTION_COUNT`: Conta transações por CPF
- `PHONE_TRANSACTION_COUNT`: Conta transações por telefone
- `BANNED_IPS`: Armazena IPs banidos temporariamente

## Limites Configurados

- Máximo de 20 transações com o mesmo nome
- Máximo de 20 transações com o mesmo CPF
- Máximo de 20 transações com o mesmo telefone
- Máximo de 5 tentativas do mesmo IP com os mesmos dados
- Máximo de 20 tentativas do mesmo cliente usando múltiplos IPs

## Funcionamento

1. Quando uma nova tentativa de transação é recebida, o sistema:
   - Extrai e normaliza os dados do cliente (nome, CPF, telefone)
   - Verifica se o IP está banido
   - Verifica se o cliente excedeu limites por nome, CPF ou telefone
   - Verifica se os mesmos dados estão sendo usados por múltiplos IPs
   - Verifica se este IP específico excedeu o limite de tentativas com os mesmos dados

2. Se qualquer limite for excedido, a transação é bloqueada e uma mensagem apropriada é retornada.

3. A função `cleanup_transaction_tracking()` é executada periodicamente para remover dados expirados.

## Ferramentas de Monitoramento

- **validate_implementation.py**: Verifica se a implementação atende aos requisitos
- **monitor_security.py**: Mostra informações detalhadas sobre o estado atual das estruturas de segurança
- **test_transaction_limit.py**: Testa automaticamente os limites de transação (requer contexto Flask)

## Como Usar o Monitoramento

Para monitorar o estado atual do sistema de proteção:

```bash
python3 monitor_security.py
```

Para validar a implementação:

```bash
python3 validate_implementation.py
```

## Código Relevante

Os principais componentes do sistema estão em:

- `transaction_tracker.py`: Implementa toda a lógica de rastreamento e bloqueio
- `api_security.py`: Implementa camadas adicionais de segurança (CSRF, rate limiting, etc.)
- `app.py`: Integra o sistema de proteção nas rotas de pagamento

## Configuração

Os limites podem ser ajustados alterando as constantes em `transaction_tracker.py`:

```python
MAX_TRANSACTION_ATTEMPTS = 5       # Limite por IP
MAX_GLOBAL_CLIENT_ATTEMPTS = 20    # Limite global por cliente
MAX_TRANSACTIONS_PER_NAME = 20     # Limite por nome
MAX_TRANSACTIONS_PER_CPF = 20      # Limite por CPF
MAX_TRANSACTIONS_PER_PHONE = 20    # Limite por telefone
IP_BAN_DURATION = timedelta(hours=24)  # Duração do banimento
```
