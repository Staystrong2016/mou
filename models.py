from datetime import datetime
from app import db

class Purchase(db.Model):
    """
    Modelo para armazenar informações de compras concluídas
    para uso em campanhas de remarketing
    """
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(64), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=True)
    customer_cpf = db.Column(db.String(14), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)
    customer_email = db.Column(db.String(120), nullable=True)
    product_name = db.Column(db.String(120), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='completed')
    
    # Campos para rastreamento de marketing
    utm_source = db.Column(db.String(64), nullable=True)
    utm_medium = db.Column(db.String(64), nullable=True)
    utm_campaign = db.Column(db.String(128), nullable=True)
    utm_content = db.Column(db.String(128), nullable=True)
    utm_term = db.Column(db.String(128), nullable=True)
    
    # Outros identificadores de tracking
    fbclid = db.Column(db.String(128), nullable=True)
    gclid = db.Column(db.String(128), nullable=True)
    
    # Informações sobre o dispositivo
    device_type = db.Column(db.String(20), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Purchase {self.transaction_id}>'
    
    def to_dict(self):
        """Converte o modelo em um dicionário para API/templates"""
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'customer_name': self.customer_name,
            'customer_cpf': self.customer_cpf,
            'customer_phone': self.customer_phone,
            'customer_email': self.customer_email,
            'product_name': self.product_name,
            'amount': self.amount,
            'status': self.status,
            'utm_source': self.utm_source,
            'utm_medium': self.utm_medium,
            'utm_campaign': self.utm_campaign,
            'utm_content': self.utm_content,
            'utm_term': self.utm_term,
            'fbclid': self.fbclid,
            'gclid': self.gclid,
            'device_type': self.device_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }