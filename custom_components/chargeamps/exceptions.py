class APIError(Exception):
    """Base exception for API-related errors"""
    pass

class NoChargepointsError(APIError):
    """No Chargepoints was returned by the API"""
    pass