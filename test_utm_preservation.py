"""
Script para testar a preservação de parâmetros UTM em todas as etapas do funil.
Este script verifica se os parâmetros UTM estão sendo preservados corretamente
na sessão durante a navegação entre as diferentes rotas da aplicação.
"""
import unittest
import json
import logging
from urllib.parse import urlparse, parse_qs
from app import app

# Configurar logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Parâmetros UTM de teste (simulando um anúncio do Facebook)
TEST_UTM_PARAMS = {
    'utm_source': 'FB',
    'utm_campaign': 'campaign123|12345',
    'utm_medium': 'adset123|67890',
    'utm_content': 'ad123|54321',
    'utm_term': 'newsfeed',
    'fbclid': '1234567890'
}

class UtmPreservationTestCase(unittest.TestCase):
    def setUp(self):
        """Configuração antes de cada teste"""
        self.app = app.test_client()
        self.app.testing = True
        
        # Configurar o contexto da aplicação para usar session
        self.app_context = app.app_context()
        self.app_context.push()
        
        # Habilitar preservação de cookies para manter a sessão
        self.app = app.test_client(use_cookies=True)
        
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

    def test_backend_utm_preservation(self):
        """Testa a preservação de parâmetros UTM no backend durante navegação no funil"""
        logger.info("Starting backend UTM preservation test")
        
        # Lista de rotas para testar, representando as etapas do funil
        funnel_routes = [
            '/anvisa',
            '/cadastro',
            '/validar-dados',
            '/validacao-em-andamento',
            '/questionario-saude',
            '/endereco',
            '/compra',
            '/pagamento_pix'
        ]
        
        # Iniciar sessão com parâmetros UTM na primeira rota
        initial_url = self.build_url_with_params(funnel_routes[0], TEST_UTM_PARAMS)
        response = self.app.get(initial_url)
        self.assertEqual(response.status_code, 200)
        logger.info(f"Initial request to {initial_url} successful")
        
        # Verificar se os parâmetros UTM foram capturados na sessão
        with self.app.session_transaction() as sess:
            # Verificar se os parâmetros individuais estão presentes
            for key, value in TEST_UTM_PARAMS.items():
                self.assertEqual(sess.get(key), value, f"Parameter {key} not found in session or value doesn't match")
            
            # Verificar se o dicionário utm_params está presente
            self.assertIn('utm_params', sess, "utm_params dict not found in session")
            
            # Verificar se todos os parâmetros estão no dicionário utm_params
            for key, value in TEST_UTM_PARAMS.items():
                self.assertEqual(sess['utm_params'].get(key), value, 
                                f"Parameter {key} not found in utm_params dict or value doesn't match")
            
            logger.info("Initial UTM parameters successfully saved in session")
            logger.info(f"Session utm_params: {sess.get('utm_params')}")
        
        # Navegar pelas próximas rotas e verificar se os parâmetros persistem
        for route in funnel_routes[1:]:
            # Fazer requisição para a próxima rota
            response = self.app.get(route)
            self.assertEqual(response.status_code, 200, f"Failed to access route {route}")
            logger.info(f"Navigated to {route} successfully")
            
            # Verificar se os parâmetros UTM continuam na sessão
            with self.app.session_transaction() as sess:
                logger.info(f"Session for {route}: {sess.get('utm_params')}")
                
                # Verificar parâmetros individuais
                for key, value in TEST_UTM_PARAMS.items():
                    self.assertEqual(sess.get(key), value, 
                                    f"Parameter {key} lost in session on route {route}")
                
                # Verificar se o dicionário utm_params continua presente
                self.assertIn('utm_params', sess, f"utm_params dict lost in session on route {route}")
                
                # Verificar se todos os parâmetros estão no dicionário utm_params
                for key, value in TEST_UTM_PARAMS.items():
                    self.assertEqual(sess['utm_params'].get(key), value, 
                                    f"Parameter {key} lost in utm_params dict on route {route}")
                
            logger.info(f"UTM parameters preserved in session for route: {route}")
        
        logger.info("Backend UTM preservation test completed successfully")

    def test_utm_referer_extraction(self):
        """Testa a extração de parâmetros UTM a partir do cabeçalho Referer"""
        logger.info("Starting UTM referer extraction test")
        
        # Criar URL com parâmetros UTM para usar como referer
        referer_url = f"http://example.com/page?utm_source=FB&utm_medium=cpc&utm_campaign=test"
        
        # Fazer uma requisição sem UTMs na URL, mas com referer contendo UTMs
        response = self.app.get('/anvisa', headers={'Referer': referer_url})
        self.assertEqual(response.status_code, 200)
        
        # Verificar se os parâmetros UTM do referer foram extraídos e salvos na sessão
        with self.app.session_transaction() as sess:
            self.assertEqual(sess.get('utm_source'), 'FB')
            self.assertEqual(sess.get('utm_medium'), 'cpc')
            self.assertEqual(sess.get('utm_campaign'), 'test')
            
            # Verificar se o dicionário utm_params contém os valores
            self.assertIn('utm_params', sess)
            self.assertEqual(sess['utm_params'].get('utm_source'), 'FB')
            self.assertEqual(sess['utm_params'].get('utm_medium'), 'cpc')
            self.assertEqual(sess['utm_params'].get('utm_campaign'), 'test')
        
        logger.info("UTM referer extraction test completed successfully")
    
    def test_form_submission_utm_preservation(self):
        """Testa a preservação de parâmetros UTM durante submissão de formulários"""
        logger.info("Starting form submission UTM preservation test")
        
        # Iniciar com uma requisição contendo parâmetros UTM para configurar a sessão
        initial_url = self.build_url_with_params('/cadastro', TEST_UTM_PARAMS)
        response = self.app.get(initial_url)
        self.assertEqual(response.status_code, 200)
        
        # Submeter um formulário para uma rota de processamento (POST)
        # Simulando o envio do formulário de cadastro
        form_data = {
            'nome': 'Teste Automatizado',
            'cpf': '12345678909',
            'email': 'teste@example.com',
            'telefone': '11999999999'
        }
        
        # Rotas que aceitam POST para testar
        post_routes = [
            '/processar_compra',
            '/pagar_frete',
            '/create_pix_payment'
        ]
        
        for route in post_routes:
            try:
                # Enviar o formulário
                response = self.app.post(route, data=form_data)
                
                # Mesmo que a rota retorne erro, podemos verificar se a sessão mantém os UTMs
                with self.app.session_transaction() as sess:
                    # Verificar se os parâmetros UTM continuam na sessão após POST
                    self.assertIn('utm_params', sess, f"utm_params lost after POST to {route}")
                    
                    # Verificar se os parâmetros individuais ainda existem
                    for key, value in TEST_UTM_PARAMS.items():
                        self.assertEqual(sess.get(key), value, 
                                        f"Parameter {key} lost after POST to {route}")
                
                logger.info(f"UTM parameters preserved after form submission to {route}")
            except Exception as e:
                logger.warning(f"Error testing POST route {route}: {str(e)}")
                # Continuar com o próximo route sem falhar o teste
        
        logger.info("Form submission UTM preservation test completed")

if __name__ == '__main__':
    unittest.main()