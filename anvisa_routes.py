from app import app
from flask import render_template, jsonify, redirect, url_for, request, session
import random
import json
from datetime import datetime
import logging
from for4payments import create_payment_api

@app.route('/compra')
def compra():
    """Página de detalhes do produto e confirmação de compra"""
    try:
        app.logger.info("[PROD] Acessando página de compra")
        # Aqui você pode adicionar lógica para carregar benefícios personalizados
        # com base nas respostas do questionário que estão na sessão
        return render_template('compra.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de compra: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/pagamento_pix')
def pagamento_pix():
    """Página de pagamento via PIX"""
    try:
        app.logger.info("[PROD] Acessando página de pagamento PIX")
        return render_template('pagamento_pix.html')
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de pagamento PIX: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/processar_pagamento_mounjaro', methods=['POST'])
def processar_pagamento_mounjaro():
    """
    Processa um pagamento PIX para o produto Mounjaro
    """
    try:
        # Registrar a tentativa
        app.logger.info("[PROD] Processando pagamento para Mounjaro")
        
        # Obter dados do formulário
        payment_data = request.json
        app.logger.info(f"[PROD] Dados de pagamento recebidos: {payment_data}")
        
        # Validar dados mínimos
        required_fields = ['name', 'amount']
        for field in required_fields:
            if field not in payment_data or not payment_data[field]:
                app.logger.warning(f"[PROD] Campo obrigatório ausente: {field}")
                return jsonify({'success': False, 'message': f'Campo obrigatório ausente: {field}'}), 400
        
        # Criar instância da API de pagamento
        try:
            payment_api = create_payment_api()
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao criar instância da API de pagamento: {str(e)}")
            return jsonify({'success': False, 'message': 'Erro de configuração do serviço de pagamento'}), 500
        
        # Obter e processar os dados necessários
        nome = payment_data.get('name') or session.get('nome', 'Cliente Anvisa')
        cpf = payment_data.get('cpf') or session.get('cpf', '')
        phone = payment_data.get('phone', '')
        email = payment_data.get('email', '')
        
        # Limpar o CPF para ter apenas números
        cpf = ''.join(c for c in cpf if c.isdigit())
        
        # Se o e-mail estiver vazio, criar um a partir do CPF
        if not email and cpf:
            email = f"{cpf}@gmail.com"
            app.logger.info(f"[PROD] Email gerado automaticamente: {email}")
        
        # Garantir que o telefone está no formato correto
        phone = ''.join(c for c in phone if c.isdigit())
        if phone.startswith('55') and len(phone) > 11:
            phone = phone[2:]
        
        # Log de validação
        app.logger.info(f"[PROD] Dados processados para pagamento: {nome}, CPF: {cpf[:3]}...{cpf[-2:]}, Phone: {phone}, Email: {email}")
        
        # Formatar os dados para a API For4Payments
        pix_data = {
            'name': nome,
            'email': email,
            'cpf': cpf,
            'phone': phone,
            'amount': float(payment_data['amount']),
            'items': [{
                'title': 'Mounjaro (Tirzepatida) 2,5mg - 4 Canetas',
                'quantity': 1,
                'unitPrice': float(payment_data['amount']) * 100,
                'tangible': True
            }]
        }
        
        # Criar o pagamento PIX
        try:
            payment_result = payment_api.create_pix_payment(pix_data)
            app.logger.info(f"[PROD] Pagamento criado com sucesso: {payment_result}")
            
            # Armazenar o ID da transação na sessão para verificação posterior
            session['mounjaro_transaction_id'] = payment_result['id']
            
            # Retornar os dados do pagamento
            return jsonify({
                'success': True,
                'transaction_id': payment_result['id'],
                'pix_code': payment_result['pixCode'],
                'pix_qrcode': payment_result['pixQrCode'],
                'amount': payment_data['amount']
            })
            
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao criar pagamento PIX: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
        
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao processar pagamento: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro interno do servidor'}), 500

@app.route('/verificar_pagamento_mounjaro')
def verificar_pagamento_mounjaro():
    """
    Verifica o status de um pagamento PIX para o produto Mounjaro
    """
    try:
        # Obter o ID da transação
        transaction_id = request.args.get('transaction_id')
        if not transaction_id:
            app.logger.warning("[PROD] ID de transação não fornecido para verificação")
            return jsonify({'success': False, 'status': 'error', 'message': 'ID de transação não fornecido'}), 400
        
        app.logger.info(f"[PROD] Verificando status do pagamento: {transaction_id}")
        
        # Criar instância da API de pagamento
        try:
            payment_api = create_payment_api()
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao criar instância da API de pagamento: {str(e)}")
            return jsonify({'success': False, 'status': 'error', 'message': 'Erro de configuração do serviço de pagamento'}), 500
        
        # Verificar o status do pagamento
        try:
            payment_status = payment_api.check_payment_status(transaction_id)
            app.logger.info(f"[PROD] Status do pagamento: {payment_status}")
            
            # Verificar se o pagamento foi confirmado
            status = payment_status.get('status', '').lower()
            
            # Mapear os possíveis status de pagamento
            if status in ['paid', 'confirmed', 'approved', 'completed']:
                return jsonify({'success': True, 'status': 'paid', 'message': 'Pagamento confirmado'})
            elif status in ['pending', 'waiting', 'processing']:
                return jsonify({'success': True, 'status': 'pending', 'message': 'Aguardando pagamento'})
            elif status in ['cancelled', 'canceled', 'failed', 'rejected']:
                return jsonify({'success': False, 'status': 'cancelled', 'message': 'Pagamento cancelado ou rejeitado'})
            else:
                return jsonify({'success': False, 'status': 'unknown', 'message': f'Status desconhecido: {status}'})
                
        except Exception as e:
            app.logger.error(f"[PROD] Erro ao verificar status do pagamento: {str(e)}")
            return jsonify({'success': False, 'status': 'error', 'message': str(e)}), 500
            
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao verificar pagamento: {str(e)}")
        return jsonify({'success': False, 'status': 'error', 'message': 'Erro interno do servidor'}), 500

@app.route('/compra_sucesso')
def compra_sucesso():
    """Página de confirmação de compra bem-sucedida"""
    try:
        app.logger.info("[PROD] Acessando página de confirmação de compra")
        
        # Gerar número de pedido aleatório
        order_number = f"ANV-{random.randint(10000000, 99999999)}"
        
        # Obter a data atual
        order_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        return render_template('compra_sucesso.html', 
                              order_number=order_number, 
                              order_date=order_date)
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao acessar página de confirmação de compra: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500