# Architecture Overview

## 1. Overview

This application is a Flask-based web system designed to provide a payment and purchase flow for products, with a focus on security, scalability, and monitoring. The system includes features for payment processing, transaction tracking, bot detection, domain restriction, and integration with external services such as payment gateways, Facebook conversion tracking, and SMS notifications.

The application appears to be primarily focused on handling payment flows for specific products, with security measures to protect against unauthorized access and fraudulent transactions. It includes comprehensive analytics and conversion tracking integrations.

## 2. System Architecture

### 2.1 Backend Architecture

The system is built using the Flask web framework with Python. The architecture follows a modular approach with the following key components:

- **Core Application** (`main.py`, `app.py`): Initializes the Flask application, loads environment variables, and sets up middleware.
- **Request Analysis** (`request_analyzer.py`): Middleware for analyzing incoming requests to detect mobile devices, social media referrals, and bots.
- **Security Modules** (`api_security.py`, `transaction_tracker.py`): Handles security concerns like CSRF protection, rate limiting, and transaction monitoring.
- **Payment Gateways** (`for4payments.py`, `novaerapayments.py`): Integrations with payment processing services.
- **Database Models** (`models.py`): SQLAlchemy models for storing application data.
- **Route Handlers**: Various route handlers for different parts of the application flow.

### 2.2 Frontend Architecture

The frontend is primarily template-based using Jinja2 templates with the following characteristics:

- HTML templates with TailwindCSS for styling
- Client-side validation using JavaScript
- Integration with Facebook Pixel for tracking events
- Mobile-responsive design
- Bot detection and access control based on device type

### 2.3 Database Architecture

The application uses SQLAlchemy with PostgreSQL as the database backend:

- **Database Models**: Defined in `models.py` using SQLAlchemy's declarative base
- **Tables**: 
  - `PixPayment`: Stores information about PIX payments
  - `Purchase`: Appears to store purchase information (code is incomplete)

### 2.4 Security Architecture

The application implements several security features:

- **Domain Restriction**: Controls access to pages based on referrer headers
- **Transaction Protection**: Limits transaction attempts to prevent attacks
- **CSRF Protection**: Token-based protection for form submissions
- **Rate Limiting**: IP-based request rate limiting for various endpoints
- **Bot Detection**: Identification and blocking of bot traffic

## 3. Key Components

### 3.1 Payment Processing

The system supports multiple payment gateways with a factory pattern for gateway selection:

- **For4Payments**: Integration with the For4Payments API for PIX payments
- **NovaEra Payments**: Alternative payment gateway integration
- **Gateway Factory**: Selects the appropriate payment gateway based on configuration

The payment flow includes:
1. Creation of payment requests
2. Transaction tracking and validation
3. Payment status monitoring
4. Storage of payment details for later reference

### 3.2 Request Analysis Middleware

The request analyzer middleware provides crucial information about requests:

- Detection of mobile devices
- Identification of social media advertising sources
- Tracking of UTM parameters
- Bot detection and blocking
- Referrer validation for security

### 3.3 Transaction Protection System

A comprehensive system for protecting against fraudulent transactions:

- Limits on transactions per name, CPF, and phone number
- IP-based tracking and limiting
- Detection of multiple-IP attacks
- Temporary IP banning for abusive behavior
- Automated cleanup of tracking data

### 3.4 Facebook Conversion API Integration

Server-side tracking for Facebook advertising:

- Event tracking throughout the user journey
- Integration with Facebook's Conversion API
- Preservation of UTM parameters
- Tracking of advertising effectiveness

### 3.5 Payment Reminder System

A background worker for sending payment reminders:

- SMS notifications for pending payments
- Tracking of payment status
- Configurable reminder intervals

### 3.6 Pharmacy API

An API for finding pharmacies near a given address, likely for prescription fulfillment:

- Geocoding of addresses
- Distance calculation
- Sorting of results by proximity

## 4. Data Flow

### 4.1 User Journey Flow

1. User arrives from an advertisement (with UTM parameters)
2. Request analyzer middleware validates and processes the request
3. User navigates through the product journey
4. User submits payment information
5. Transaction protection verifies legitimacy
6. Payment gateway processes payment
7. System stores payment information
8. Payment reminder worker monitors payment status
9. Facebook conversion events are tracked at each step

### 4.2 Security Flow

1. Request arrives at the application
2. Domain restriction validates the referrer
3. Request analyzer checks for bots or suspicious patterns
4. Rate limiter verifies request frequency
5. CSRF validation for form submissions
6. Transaction tracking checks for abuse patterns
7. IP ban check for known abusive sources

### 4.3 Payment Processing Flow

1. User submits payment form
2. Form data is validated
3. Transaction protection verifies legitimacy
4. Gateway factory selects appropriate payment provider
5. Payment request is sent to the provider
6. Payment details are stored locally
7. QR code or payment link is provided to user
8. Payment status is monitored for completion
9. Reminder system activated for pending payments

## 5. External Dependencies

### 5.1 Payment Gateways

- **For4Payments**: Primary payment gateway for PIX payments
- **NovaEra Payments**: Alternative payment gateway

### 5.2 Analytics and Tracking

- **Facebook Conversion API (CAPI)**: Server-side event tracking
- **Facebook Pixel**: Client-side event tracking
- **Utmify**: Integration for tracking UTM parameters and conversions
- **Microsoft Clarity**: Usage analytics tracking

### 5.3 Communication Services

- **Twilio**: Appears to be used for SMS notifications

### 5.4 External APIs

- **Google Maps API**: Used for geocoding in the pharmacy API

## 6. Deployment Strategy

### 6.1 Hosting Environment

The application is configured for deployment on Replit with the following characteristics:

- **Runtime**: Python 3.11
- **Database**: PostgreSQL 16
- **Web Server**: Gunicorn for production serving
- **Environment Variables**: Configuration via environment variables

### 6.2 Configuration Management

- **Environment Variables**: Used for all sensitive configuration
- **dotenv**: Loading environment variables from `.env` file in development
- **Procfile**: Defines process types for deployment

### 6.3 Security Measures in Production

- **Domain Access Control**: Only allows access from authorized domains
- **Bot Protection**: Redirects bots to external sites
- **DevTools Disabling**: Prevents browser developer tools in production
- **Specific Routing Rules**: Different behavior in production vs. development

### 6.4 Scaling Considerations

- **Database Connection Pooling**: Configured for efficient database connections
- **Gunicorn Workers**: Multiple workers for handling concurrent requests
- **Background Processing**: Separate thread for payment reminders
- **Connection Limits**: Rate limiting to prevent resource exhaustion

## 7. Security Considerations

### 7.1 Domain Restriction and Link Protection

A system to protect offer links ensuring:
- Only authorized access (with valid `adsetid`) can access offer pages
- Users can navigate freely after validation
- Security parameters are removed from URLs after validation
- Unauthorized access is redirected to external URLs

### 7.2 Transaction Protection

Comprehensive protection against automated transaction attacks:
- Limits per name, CPF, and phone number (20 transactions in 24 hours)
- IP-based limits (5 attempts with same data in 24 hours)
- Detection of attacks using multiple IPs
- Temporary banning of abusive IPs
- Automatic cleanup of tracking data

### 7.3 API Security

- JWT-based authentication
- CSRF token protection
- Rate limiting by route and IP
- Allowed domain validation