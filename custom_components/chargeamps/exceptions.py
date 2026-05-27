class APIError(Exception):
    """Base exception for API-related errors."""

    pass


class NoChargepointsError(APIError):
    """No chargepoints were returned by the API for the given organisation ID."""

    pass
