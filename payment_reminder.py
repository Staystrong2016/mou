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
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER][ASYNC] Cannot send initial SMS - no phone number for {transaction_id}")
        return
    
    # Get first name only
    first_name = customer_name.split(' ')[0] if customer_name else ''
    
    # Formatação do número de telefone para formato internacional
    # Garantir que comece com 55 para Brasil
    if not phone_number.startswith('55'):
        phone_number = '55' + phone_number.lstrip('+')
    
    try:
        # Message template for new PIX generation
        message = f"ANVISA INFORMA: Seu Pedido MOUNJARO (1 CAIXA COM 4 UNIDADES) foi gerado com sucesso. Finalize o pagamento do QRcode PIX e confirme a sua compra antes que expire"
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] Sending initial SMS to {phone_number} for transaction {transaction_id}")
        
        # Prepare request data with additional parameters as per API docs
        request_data = {
            'phone': phone_number,
            'message': message,
            'enableVoiceCall': True,
            'campaignName': "Mounjaro - Pagamento Gerado",
            'shortenableLink': "https://anvisadobrasil.org"
        }
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
        message = f"ANVISA: {first_name}, seu PIX para o Mounjaro esta pronto! Ultimas 200 unidades, reserva expira em pouco tempo. Pague agora: https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}"
        
        logger.info(f"[PAYMENT_TRACKER][ASYNC] Sending reminder SMS to {phone_number} for transaction {transaction_id}")
        
        # Prepare request data with additional parameters as per API docs
        request_data = {
            'phone': phone_number,
            'message': message,
            'enableVoiceCall': True,
            'campaignName': "Lembrete de pagamento",
            'shortenableLink': "https://anvisadobrasil.org",
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
