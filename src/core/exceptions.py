"""
Domain-specific exceptions for business logic.

These exceptions represent domain errors and should be caught by
HTTP middleware to convert to appropriate HTTP responses.
"""


class DomainException(Exception):
    """Base exception for all domain-level errors."""
    
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class UnauthorizedException(DomainException):
    """Raised when authentication fails or token is invalid."""
    pass


class ResourceNotFoundException(DomainException):
    """Raised when a requested resource does not exist."""
    
    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} not found: {resource_id}"
        super().__init__(message, {"resource_type": resource_type, "resource_id": resource_id})


class PatientAccessDeniedException(UnauthorizedException):
    """Raised when user attempts to access patient data without permission."""
    
    def __init__(self, requester_id: str, patient_id: str):
        message = f"User {requester_id} does not have access to patient {patient_id} data"
        super().__init__(message, {"requester_id": requester_id, "patient_id": patient_id})


class InvalidPairingCodeException(DomainException):
    """Raised when pairing code is invalid, expired, or already used."""
    pass


class ExpiredSessionException(UnauthorizedException):
    """Raised when user session has expired."""
    pass


class ValidationException(DomainException):
    """Raised when input fails validation rules."""
    pass


class DuplicateResourceException(DomainException):
    """Raised when attempting to create a resource that already exists."""
    
    def __init__(self, resource_type: str, unique_field: str, value: str):
        message = f"{resource_type} already exists with {unique_field}={value}"
        super().__init__(
            message, 
            {"resource_type": resource_type, "unique_field": unique_field, "value": value}
        )


class BusinessRuleException(DomainException):
    """Raised when a business rule is violated."""
    pass
