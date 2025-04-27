"""
Script para testar o envio de eventos à API de Conversão do Facebook em todas as etapas do funil.
Verifica se os parâmetros UTM são corretamente capturados e incluídos nos eventos enviados.
"""
import unittest
import json
import logging
import time
from unittest.mock import patch, MagicMock
from flask import session, url_for
from urllib.parse import urlparse, parse_qs

from app import app
import facebook_conversion_api

# Configurar logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Parâmetros UTM de teste
TEST_UTM_PARAMS = {
    'utm_source': 'facebook',
    'utm_campaign': 'campaign123|12345',
    'utm_medium': 'adset123|67890',
    'utm_content': 'ad123|54321',
    'utm_term': 'newsfeed',
    'fbclid': '1234567890'
}

# Lista de rotas do funil de conversão
FUNNEL_ROUTES = [
    '/anvisa',
    '/cadastro',
    '/validar-dados',
    '/validacao-em-andamento',
    '/questionario-saude',
    '/endereco',
    '/compra',
    '/pagamento_pix',
    '/compra_sucesso'
]

# Mapeamento entre rotas e eventos esperados
ROUTE_TO_EVENT = {
    '/anvisa': 'PageView',
    '/cadastro': 'ViewContent',
    '/validar-dados': 'ViewContent',
    '/validacao-em-andamento': 'ViewContent',
    '/questionario-saude': 'ViewContent',
    '/endereco': 'Lead',
    '/compra': 'AddPaymentInfo',
    '/pagamento_pix': 'InitiateCheckout',
    '/compra_sucesso': 'Purchase'
}

class FacebookConversionEventsTestCase(unittest.TestCase):
    def setUp(self):
        """Configuração antes de cada teste"""
        # Configurar cliente de teste
        self.app = app.test_client()
        self.app.testing = True
        
        # Configurar o contexto da aplicação para usar session
        self.app_context = app.app_context()
        self.app_context.push()
        
        # Habilitar preservação de cookies para manter a sessão
        self.app = app.test_client(use_cookies=True)
        
        # Log de início do teste
        logger.info("Test environment setup complete")

    def tearDown(self):
        """Limpeza após cada teste"""
        self.app_context.pop()
        logger.info("Test environment teardown complete")

    def build_url_with_params(self, route, params=None):
        """Constrói uma URL com os parâmetros UTM"""
        query_string = ""
        if params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            query_string = f"?{query_string}"
        return f"{route}{query_string}"

    @patch('facebook_conversion_api.send_event')
    def test_event_parameters_in_funnel(self, mock_send_event):
        """Testa se os eventos do funil incluem os parâmetros UTM corretamente"""
        logger.info("Iniciando teste de eventos com parâmetros UTM no funil")
        
        # Mock para simular o retorno da função send_event
        mock_send_event.return_value = {
            'success': True,
            'message': 'Event sent successfully',
            'response': {'events_received': 1, 'fbtrace_id': '123456789'}
        }
        
        # Acessar a primeira rota com parâmetros UTM para iniciar a sessão
        initial_url = self.build_url_with_params(FUNNEL_ROUTES[0], TEST_UTM_PARAMS)
        response = self.app.get(initial_url)
        self.assertEqual(response.status_code, 200)
        logger.info(f"Acesso à rota inicial {FUNNEL_ROUTES[0]} com UTMs: {TEST_UTM_PARAMS}")
        
        # Verificar se o evento correto foi enviado para a primeira rota
        event_name = ROUTE_TO_EVENT[FUNNEL_ROUTES[0]]
        self.assertTrue(mock_send_event.called)
        
        # Resetar mock para contagem limpa na próxima chamada
        mock_send_event.reset_mock()
        
        # Percorrer o restante do funil
        for route in FUNNEL_ROUTES[1:]:
            # Acessar a rota sem parâmetros UTM (devem ser mantidos da sessão)
            response = self.app.get(route)
            self.assertEqual(response.status_code, 200)
            logger.info(f"Acesso à rota {route}")
            
            # Verificar se o evento foi enviado
            self.assertTrue(mock_send_event.called)
            
            # Verificar o nome do evento enviado
            expected_event = ROUTE_TO_EVENT[route]
            args, kwargs = mock_send_event.call_args
            
            # Log detalhado dos argumentos passados para send_event
            logger.info(f"Argumentos passados para send_event na rota {route}: {kwargs}")
            
            # O primeiro argumento deve ser o ID do pixel, o segundo o nome do evento
            self.assertEqual(kwargs.get('event_name'), expected_event)
            
            # Resetar mock para contagem limpa na próxima chamada
            mock_send_event.reset_mock()
        
        logger.info("Teste de eventos com parâmetros UTM no funil concluído com sucesso")

    @patch('facebook_conversion_api.send_event')
    def test_utm_parameters_included_in_events(self, mock_send_event):
        """
        Testa se os parâmetros UTM são corretamente incluídos nos dados customizados
        dos eventos enviados para o Facebook
        """
        logger.info("Iniciando teste de inclusão de parâmetros UTM nos eventos")
        
        # Mock para simular o retorno da função send_event
        mock_send_event.return_value = {
            'success': True,
            'message': 'Event sent successfully',
            'response': {'events_received': 1, 'fbtrace_id': '987654321'}
        }
        
        # Acesso à rota de teste com parâmetros UTM
        test_route = '/endereco'  # Rota que envia evento Lead
        test_url = self.build_url_with_params(test_route, TEST_UTM_PARAMS)
        response = self.app.get(test_url)
        self.assertEqual(response.status_code, 200)
        
        # Verificar se o evento foi enviado
        self.assertTrue(mock_send_event.called)
        
        # Extrair argumentos passados para a função send_event
        args, kwargs = mock_send_event.call_args
        logger.info(f"Argumentos detalhados para send_event: {kwargs}")
        
        # Verificar se os dados customizados incluem os parâmetros UTM
        custom_data = kwargs.get('custom_data', {})
        self.assertIsNotNone(custom_data)
        
        # Verificar presença de parâmetros UTM nos dados customizados
        utm_fields = ['utm_source', 'utm_campaign', 'utm_medium', 'utm_content', 'utm_term', 'fbclid']
        for field in utm_fields:
            if field in TEST_UTM_PARAMS:
                self.assertEqual(custom_data.get(field), TEST_UTM_PARAMS[field])
        
        logger.info("Teste de inclusão de parâmetros UTM nos eventos concluído com sucesso")

    @patch('facebook_conversion_api.send_event')
    def test_form_submission_with_utm_parameters(self, mock_send_event):
        """
        Testa se os parâmetros UTM são preservados e incluídos nos eventos
        após o envio de formulários
        """
        logger.info("Iniciando teste de envio de formulário com parâmetros UTM")
        
        # Mock para simular o retorno da função send_event
        mock_send_event.return_value = {
            'success': True,
            'message': 'Event sent successfully',
            'response': {'events_received': 1, 'fbtrace_id': 'abcdef123456'}
        }
        
        # Acesso à rota com formulário com parâmetros UTM
        form_route = '/endereco'
        form_url = self.build_url_with_params(form_route, TEST_UTM_PARAMS)
        response = self.app.get(form_url)
        self.assertEqual(response.status_code, 200)
        
        # Simular envio do formulário para uma rota de processamento (POST)
        form_data = {
            'nome': 'Teste Automatizado',
            'cpf': '12345678909',
            'email': 'teste@example.com',
            'telefone': '11999999999',
            'endereco': 'Rua de Teste, 123',
            'cidade': 'São Paulo',
            'estado': 'SP'
        }
        
        # Adicionar parâmetros UTM como hidden fields (simulando formulário real)
        for key, value in TEST_UTM_PARAMS.items():
            form_data[key] = value
        
        # Enviar formulário para Facebook Lead Event
        response = self.app.post('/facebook_lead_event', data=json.dumps(form_data), 
                               content_type='application/json')
        
        # Verificar se o evento de Lead foi enviado
        self.assertTrue(mock_send_event.called)
        
        # Verificar detalhes do evento enviado
        args, kwargs = mock_send_event.call_args
        logger.info(f"Argumentos de send_event após POST: {kwargs}")
        
        # Verificar nome do evento
        self.assertEqual(kwargs.get('event_name'), 'Lead')
        
        # Verificar presença de parâmetros UTM nos dados customizados
        custom_data = kwargs.get('custom_data', {})
        for field in ['utm_source', 'utm_campaign', 'utm_medium']:
            if field in TEST_UTM_PARAMS:
                self.assertEqual(custom_data.get(field), TEST_UTM_PARAMS[field])
        
        logger.info("Teste de envio de formulário com parâmetros UTM concluído com sucesso")

    @patch('facebook_conversion_api.send_event')
    def test_events_with_referer_utm_parameters(self, mock_send_event):
        """
        Testa se os parâmetros UTM são extraídos do cabeçalho Referer
        e incluídos nos eventos enviados
        """
        logger.info("Iniciando teste de extração de UTMs do Referer")
        
        # Mock para simular o retorno da função send_event
        mock_send_event.return_value = {
            'success': True,
            'message': 'Event sent successfully',
            'response': {'events_received': 1, 'fbtrace_id': 'xyz123456'}
        }
        
        # Criar URL com parâmetros UTM para usar como referer
        referer_url = f"http://example.com/page?utm_source=facebook&utm_medium=cpc&utm_campaign=test"
        
        # Fazer uma requisição sem UTMs na URL, mas com referer contendo UTMs
        response = self.app.get('/anvisa', headers={'Referer': referer_url})
        self.assertEqual(response.status_code, 200)
        
        # Verificar se o evento foi enviado
        self.assertTrue(mock_send_event.called)
        
        # Verificar detalhes do evento enviado
        args, kwargs = mock_send_event.call_args
        logger.info(f"Argumentos de send_event com Referer: {kwargs}")
        
        # Verificar nome do evento
        self.assertEqual(kwargs.get('event_name'), 'PageView')
        
        # Verificar presença de parâmetros UTM nos dados customizados
        custom_data = kwargs.get('custom_data', {})
        self.assertEqual(custom_data.get('utm_source'), 'facebook')
        self.assertEqual(custom_data.get('utm_medium'), 'cpc')
        self.assertEqual(custom_data.get('utm_campaign'), 'test')
        
        logger.info("Teste de extração de UTMs do Referer concluído com sucesso")

class FacebookConversionAPIIntegrationTestCase(unittest.TestCase):
    """
    Testes de integração direta com a API do Facebook sem mocks.
    Estes testes podem consumir o limite de eventos da API, use com moderação.
    """
    
    def setUp(self):
        """Configuração antes de cada teste"""
        # Evitar executar estes testes por padrão, pois consomem o limite da API
        self.should_run = False
        
        # Verificar se o ambiente está configurado para enviar eventos reais
        if facebook_conversion_api.PIXEL_ID and facebook_conversion_api.ACCESS_TOKEN:
            self.should_run = True
        
        # Log de início do teste
        logger.info(f"Test environment setup complete. Should run real API tests: {self.should_run}")

    def test_real_pixel_api_integration(self):
        """
        Testa o envio real de um evento para a API de Conversão do Facebook.
        Este teste só será executado se houver configuração de PIXEL_ID e ACCESS_TOKEN.
        """
        if not self.should_run:
            logger.info("Pulando teste de integração real com API - faltam credenciais")
            return
        
        logger.info("Iniciando teste de integração real com a API do Facebook")
        
        # Preparar dados para teste real
        test_event_name = 'PageView'
        test_user_data = facebook_conversion_api.prepare_user_data(
            email='test@example.com',
            phone='5511999999999',
            first_name='Teste',
            last_name='Automatizado'
        )
        test_custom_data = {
            'utm_source': 'facebook',
            'utm_medium': 'testing',
            'utm_campaign': 'integration_test'
        }
        
        # Enviar evento diretamente para a API
        result = facebook_conversion_api.send_event(
            pixel_id=facebook_conversion_api.PIXEL_ID,
            event_name=test_event_name,
            user_data=test_user_data,
            custom_data=test_custom_data,
            event_source_url='https://example.com/test'
        )
        
        # Verificar resultado do envio
        self.assertTrue(result['success'])
        self.assertIn('events_received', result['response'])
        self.assertEqual(result['response']['events_received'], 1)
        
        # Log detalhado da resposta
        logger.info(f"Resposta da API do Facebook: {result}")
        
        # Aguardar para evitar rate limiting 
        time.sleep(1)
        
        logger.info("Teste de integração real com a API do Facebook concluído com sucesso")

def add_frontend_debug_logs():
    """
    Adiciona script de JavaScript para registrar informações de depuração
    sobre o envio de eventos do Facebook no frontend
    """
    debug_script = """
    <!-- Facebook Conversion API Debug Script -->
    <script>
    // Função original do Facebook
    var originalFbq = window.fbq;
    
    // Sobrescrever fbq para incluir logs
    window.fbq = function() {
        var args = Array.prototype.slice.call(arguments);
        
        // Log detalhado do evento sendo enviado
        console.log("[FB PIXEL DEBUG] Sending event:", {
            args: args,
            utmParams: getUtmParams(),
            timestamp: new Date().toISOString()
        });
        
        // Verificar resposta
        try {
            var originalResult = originalFbq.apply(this, args);
            console.log("[FB PIXEL DEBUG] Event sent successfully");
            return originalResult;
        } catch (error) {
            console.error("[FB PIXEL DEBUG] Error sending event:", error);
            throw error;
        }
    };
    
    // Manter funcionalidades originais
    for (var prop in originalFbq) {
        window.fbq[prop] = originalFbq[prop];
    }
    
    // Função para obter parâmetros UTM
    function getUtmParams() {
        var params = {};
        var searchParams = new URLSearchParams(window.location.search);
        ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid'].forEach(function(param) {
            if (searchParams.has(param)) {
                params[param] = searchParams.get(param);
            }
        });
        return params;
    }
    
    // Log quando a página carrega
    document.addEventListener('DOMContentLoaded', function() {
        console.log("[FB PIXEL DEBUG] Page loaded with UTM params:", getUtmParams());
        
        // Verificar se o pixel do Facebook está carregado
        console.log("[FB PIXEL DEBUG] Facebook Pixel status:", window.fbq ? "Loaded" : "Not loaded");
    });
    </script>
    """
    
    return debug_script

if __name__ == '__main__':
    unittest.main()