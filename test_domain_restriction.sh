#!/bin/bash
# test_domain_restriction.sh
# Script para testar a funcionalidade de restrição de domínio e proteção de links de ofertas

# Cores para mensagens
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASE_URL="http://localhost:5000"
COOKIE_FILE="test_cookie.txt"
OFFER_SECRET=${OFFER_SECRET:-"ultrablastersecret"}

echo -e "${YELLOW}Iniciando testes de restrição de domínio...${NC}"
echo -e "${YELLOW}Usando OFFER_SECRET: ${OFFER_SECRET}${NC}"

# 1. Teste de acesso sem adsetid (deve redirecionar em produção ou permitir em desenvolvimento)
echo -e "\n${YELLOW}Teste 1: Acesso sem adsetid (deve redirecionar em produção ou permitir em desenvolvimento)${NC}"
RESP=$(curl -s -I "${BASE_URL}/anvisa" | grep -i location)
IS_DEV=$(env | grep -c "DEVELOPING=true")

if [[ $IS_DEV -gt 0 ]]; then
    if [[ -z "$RESP" ]]; then
        echo -e "${GREEN}SUCESSO: Acesso permitido em modo de desenvolvimento como esperado${NC}"
    else
        echo -e "${RED}FALHA: Redirecionamento ocorreu em modo de desenvolvimento${NC}"
        echo "$RESP"
    fi
else
    if [[ $RESP == *"revistaquem.globo.com"* ]]; then
        echo -e "${GREEN}SUCESSO: Redirecionamento ocorreu como esperado em produção${NC}"
        echo "$RESP"
    else
        echo -e "${RED}FALHA: Redirecionamento não ocorreu como esperado em produção${NC}"
        echo "$RESP"
    fi
fi

# 2. Teste com adsetid inválido (deve redirecionar)
echo -e "\n${YELLOW}Teste 2: Acesso com adsetid inválido (deve redirecionar)${NC}"
RESP=$(curl -s -I "${BASE_URL}/anvisa?adsetid=valor_invalido" | grep -i location)
if [[ $RESP == *"revistaquem.globo.com"* ]]; then
    echo -e "${GREEN}SUCESSO: Redirecionamento ocorreu como esperado${NC}"
    echo "$RESP"
else
    echo -e "${RED}FALHA: Redirecionamento não ocorreu como esperado${NC}"
    echo "$RESP"
fi

# 3. Teste com adsetid válido (deve permitir acesso e configurar cookie)
echo -e "\n${YELLOW}Teste 3: Acesso com adsetid válido (deve permitir acesso e configurar cookie)${NC}"
rm -f $COOKIE_FILE
RESP=$(curl -s -c $COOKIE_FILE "${BASE_URL}/anvisa?adsetid=${OFFER_SECRET}&utm_source=test" -v 2>&1 | grep -E "Location:|verified_offer")
HAS_COOKIE=$(grep -c "verified_offer" $COOKIE_FILE)
LOCATION_CHECK=$(echo "$RESP" | grep -c "Location:")

if [[ $LOCATION_CHECK -gt 0 && $HAS_COOKIE -gt 0 ]]; then
    echo -e "${GREEN}SUCESSO: Cookie configurado e redirecionamento para URL limpa${NC}"
    echo "Cookie:"
    cat $COOKIE_FILE | grep verified_offer
    echo "Resposta:"
    echo "$RESP" | grep -E "Location:|verified_offer"
else
    echo -e "${RED}FALHA: Cookie não configurado ou redirecionamento não ocorreu${NC}"
    echo "Cookie file ($COOKIE_FILE):"
    cat $COOKIE_FILE
    echo "Resposta:"
    echo "$RESP"
fi

# 4. Teste de acesso subsequente com cookie (deve permitir acesso)
echo -e "\n${YELLOW}Teste 4: Acesso subsequente com cookie (deve permitir acesso)${NC}"
RESP=$(curl -s -b $COOKIE_FILE "${BASE_URL}/anvisa" | grep -c "SECURITY")
if [[ $RESP -eq 0 ]]; then
    echo -e "${GREEN}SUCESSO: Acesso permitido com cookie${NC}"
    echo -e "Nota: O log de verificação não aparece no HTML, mas o acesso foi permitido"
else
    echo -e "${RED}FALHA: Acesso negado mesmo com cookie${NC}"
    echo "$RESP"
fi

# 5. Teste de preservação de parâmetros UTM
echo -e "\n${YELLOW}Teste 5: Preservação de parâmetros UTM${NC}"
rm -f $COOKIE_FILE
RESP=$(curl -s -c $COOKIE_FILE "${BASE_URL}/anvisa?adsetid=${OFFER_SECRET}&utm_source=facebook&utm_medium=cpc&utm_campaign=teste" -v 2>&1 | grep -E "Location:")
if [[ $RESP == *"utm_source=facebook"* && $RESP == *"utm_medium=cpc"* && $RESP == *"utm_campaign=teste"* && $RESP != *"adsetid"* ]]; then
    echo -e "${GREEN}SUCESSO: Parâmetros UTM preservados e adsetid removido${NC}"
    echo "$RESP"
else
    echo -e "${RED}FALHA: Parâmetros UTM não preservados ou adsetid não removido${NC}"
    echo "$RESP"
fi

# Limpar arquivo de cookie ao final
rm -f $COOKIE_FILE

echo -e "\n${YELLOW}Testes de restrição de domínio concluídos.${NC}"