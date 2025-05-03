import logging
from flask import request, jsonify
import os
from models import PixPayment, db
from payment_reminder import mark_payment_completed

def handle_novaera_webhook(app):
    """
    Webhook para receber notificações de pagamento da NovaEra
    
    Formato esperado: 
    {
        "id": webhook_id,
        "url": webhook_url,
        "data": {
            "id": transaction_id,
            "status": "paid"|"pending"|"cancelled",
            "pix": {
                "qrcode": "qrcode_data"
            },
            "amount": 5000,
            "paidAt": "timestamp",
            "customer": {
                "name": "Cliente Nome",
                "email": "cliente@email.com",
                "phone": "telefone",
                "document": {
                    "type": "cpf",
                    "number": "12345678900"
                }
            }
        },
        "type": "transaction"
    }
    """
    try:
        # Obter dados da requisição JSON
        webhook_data = request.get_json()
        
        if not webhook_data:
            app.logger.error("[WEBHOOK] Nenhum dado JSON recebido no webhook")
            return jsonify({"success": False, "message": "Nenhum dado recebido"}), 400
        
        app.logger.info(f"[WEBHOOK] Dados recebidos no webhook: {webhook_data}")
        
        # Verificar se é uma notificação de transação
        if webhook_data.get('type') != 'transaction':
            app.logger.warning(f"[WEBHOOK] Tipo de notificação não suportado: {webhook_data.get('type')}")
            return jsonify({"success": True, "message": "Tipo de notificação não processado"}), 200
        
        # Extrair dados da transação
        transaction_data = webhook_data.get('data', {})
        transaction_id = str(transaction_data.get('id'))
        status = transaction_data.get('status', '').lower()
        
        if not transaction_id:
            app.logger.error("[WEBHOOK] ID da transação não encontrado nos dados do webhook")
            return jsonify({"success": False, "message": "ID da transação não encontrado"}), 400
            
        app.logger.info(f"[WEBHOOK] Processando notificação para transação {transaction_id}, status: {status}")
        
        # Extrair dados de PIX se disponíveis
        pix_data = transaction_data.get('pix', {})
        qr_code = pix_data.get('qrcode', None)
        
        # Extrair dados do cliente
        customer_data = transaction_data.get('customer', {})
        customer_name = customer_data.get('name', '')
        customer_email = customer_data.get('email', '')
        customer_phone = customer_data.get('phone', '')
        
        # Extrair CPF do cliente
        document = customer_data.get('document', {})
        customer_cpf = document.get('number', '') if document.get('type') == 'cpf' else ''
        
        # Extrair valor da transação (converter de centavos para reais se necessário)
        amount_raw = transaction_data.get('amount', 0)
        amount = float(amount_raw) / 100 if amount_raw > 1000 else float(amount_raw)
        
        # Buscar pagamento existente ou criar novo
        pix_payment = PixPayment.query.filter_by(transaction_id=transaction_id).first()
        
        if pix_payment:
            app.logger.info(f"[WEBHOOK] Atualizando pagamento existente para transação {transaction_id}")
            # Atualizar status do pagamento existente
            pix_payment.status = status
            
            # Atualizar QR code se disponível e ainda não estiver armazenado
            if qr_code and not pix_payment.qr_code_image:
                pix_payment.qr_code_image = qr_code
                
            # Atualizar dados do cliente se estiverem disponíveis e ainda não armazenados
            if customer_name and not pix_payment.customer_name:
                pix_payment.customer_name = customer_name
            if customer_email and not pix_payment.customer_email:
                pix_payment.customer_email = customer_email
            if customer_phone and not pix_payment.customer_phone:
                pix_payment.customer_phone = customer_phone
            if customer_cpf and not pix_payment.customer_cpf:
                pix_payment.customer_cpf = customer_cpf
        else:
            app.logger.info(f"[WEBHOOK] Criando novo registro de pagamento para transação {transaction_id}")
            # Criar novo registro de pagamento
            pix_payment = PixPayment(
                transaction_id=transaction_id,
                gateway='NOVAERA',
                qr_code_image=qr_code,
                pix_copy_paste=None,  # Não disponível na notificação webhook
                amount=amount,
                status=status,
                customer_name=customer_name,
                customer_cpf=customer_cpf,
                customer_phone=customer_phone,
                customer_email=customer_email
            )
            db.session.add(pix_payment)
        
        # Salvar alterações no banco de dados
        db.session.commit()
        
        # Se o pagamento foi confirmado, marcar como concluído no sistema de lembretes
        if status == 'paid':
            try:
                mark_payment_completed(transaction_id)
                app.logger.info(f"[WEBHOOK] Pagamento {transaction_id} marcado como completo no sistema de lembretes")
                
                # Lógica para enviar SMS caso necessário
                if customer_phone and hasattr(app, 'send_payment_confirmation_sms'):
                    thank_you_url = request.url_root.rstrip('/') + f"/remarketing/{transaction_id}"
                    # Função definida em app.py - não chamamos diretamente para evitar import circular
                    sms_sent = app.send_payment_confirmation_sms(
                        phone_number=customer_phone,
                        nome=customer_name,
                        cpf=customer_cpf,
                        thank_you_url=thank_you_url
                    )
                    
                    if sms_sent:
                        app.logger.info(f"[WEBHOOK] SMS de confirmação enviado para {customer_phone}")
                    else:
                        app.logger.warning(f"[WEBHOOK] Falha ao enviar SMS de confirmação para {customer_phone}")
            except Exception as sms_error:
                app.logger.error(f"[WEBHOOK] Erro ao marcar pagamento como completo no sistema de lembretes: {str(sms_error)}")
        
        # Retornar resposta de sucesso
        return jsonify({
            "success": True, 
            "message": f"Notificação processada com sucesso para transação {transaction_id}",
            "transaction_id": transaction_id,
            "status": status
        }), 200
        
    except Exception as e:
        app.logger.error(f"[WEBHOOK] Erro ao processar notificação webhook: {str(e)}")
        return jsonify({"success": False, "message": f"Erro: {str(e)}"}), 500

def register_novaera_webhook(app):
    """
    Registra a rota de webhook para a NovaEra Payment Gateway
    """
    @app.route('/novaera/webhook', methods=['POST'])
    def novaera_webhook():
        return handle_novaera_webhook(app)
