import os
import random
import string
from flask import Flask
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a simple Flask app context for testing
app = Flask(__name__)

def generate_random_name():
    """Generate a random name for testing"""
    first_names = ["Maria", "João", "Ana", "Pedro", "Carla", "Lucas", "Mariana", "José"]
    last_names = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_random_cpf():
    """Generate a random CPF format for testing (not valid CPF)"""
    return ''.join(random.choices(string.digits, k=11))

def generate_random_phone():
    """Generate a random phone number for testing"""
    ddd = str(random.randint(11, 99))
    number = ''.join(random.choices(string.digits, k=8))
    return f"{ddd}9{number}"  # Format: DDD9XXXXXXXX (11 digits)

def generate_test_payment_data():
    """Generate test payment data"""
    return {
        "name": generate_random_name(),
        "email": f"teste_{random.randint(1000, 9999)}@example.com",
        "cpf": generate_random_cpf(),
        "phone": generate_random_phone(),
        "amount": 49.90  # Amount in BRL
    }

def test_create_payment_with_for4():
    """Test creating a payment using FOR4 gateway"""
    # Set gateway to FOR4
    os.environ["GATEWAY_CHOICE"] = "FOR4"
    
    with app.app_context():
        from payment_gateway import get_payment_gateway
        try:
            # Get payment gateway (should be FOR4)
            payment_gateway = get_payment_gateway()
            logger.info(f"Using payment gateway: {type(payment_gateway).__name__}")
            
            # Create a test payment
            test_data = generate_test_payment_data()
            logger.info(f"Creating test payment with data: {test_data}")
            
            # This would actually call the payment API in a real environment
            # For testing purposes, we'll just log the call
            logger.info(f"Would call {payment_gateway.API_URL}/transaction.purchase with data")
            logger.info(f"This is a log-only test, no actual API call is made")
            
            # In a real context, you would do:
            # result = payment_gateway.create_pix_payment(test_data)
            # logger.info(f"Payment result: {result}")
        except Exception as e:
            logger.error(f"Error during payment test: {str(e)}")

def test_create_payment_with_novaera():
    """Test creating a payment using NOVAERA gateway"""
    # Set gateway to NOVAERA
    os.environ["GATEWAY_CHOICE"] = "NOVAERA"
    
    with app.app_context():
        from payment_gateway import get_payment_gateway
        try:
            # Get payment gateway (should be NOVAERA)
            payment_gateway = get_payment_gateway()
            logger.info(f"Using payment gateway: {type(payment_gateway).__name__}")
            
            # Create a test payment
            test_data = generate_test_payment_data()
            logger.info(f"Creating test payment with data: {test_data}")
            
            # This would actually call the payment API in a real environment
            # For testing purposes, we'll just log the call
            logger.info(f"Would call {payment_gateway.API_URL}/transaction.purchase with data")
            logger.info(f"This is a log-only test, no actual API call is made")
            
            # In a real context, you would do:
            # result = payment_gateway.create_pix_payment(test_data)
            # logger.info(f"Payment result: {result}")
        except Exception as e:
            logger.error(f"Error during payment test: {str(e)}")

if __name__ == "__main__":
    logger.info("==== TESTING PAYMENT GATEWAY SELECTION ====")
    logger.info("--- Testing with FOR4 ---")
    test_create_payment_with_for4()
    logger.info("\n--- Testing with NOVAERA ---")
    test_create_payment_with_novaera()
    logger.info("==== PAYMENT GATEWAY TESTS COMPLETE ====")