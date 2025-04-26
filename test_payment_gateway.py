import os
from flask import Flask
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a simple Flask app context for testing
app = Flask(__name__)

def test_gateway_selection():
    """Test the gateway selection logic with different GATEWAY_CHOICE values"""
    
    # Test with FOR4
    os.environ["GATEWAY_CHOICE"] = "FOR4"
    with app.app_context():
        from payment_gateway import get_payment_gateway
        gateway = get_payment_gateway()
        logger.info(f"Gateway type with GATEWAY_CHOICE=FOR4: {type(gateway).__name__}")
        logger.info(f"Gateway API URL: {gateway.API_URL}")
    
    # Test with NOVAERA
    os.environ["GATEWAY_CHOICE"] = "NOVAERA"
    with app.app_context():
        from payment_gateway import get_payment_gateway
        gateway = get_payment_gateway()
        logger.info(f"Gateway type with GATEWAY_CHOICE=NOVAERA: {type(gateway).__name__}")
        logger.info(f"Gateway API URL: {gateway.API_URL}")

if __name__ == "__main__":
    logger.info("Testing payment gateway selection...")
    test_gateway_selection()
    logger.info("Payment gateway test completed")