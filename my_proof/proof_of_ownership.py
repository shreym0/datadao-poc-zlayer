import requests
import logging

def generate_jwt_token(wallet_address: str, secret_key: str, expiration_time: int) -> str:
    """Generate a JWT token for a given wallet address."""
    from jwt import encode as jwt_encode
    from datetime import datetime, timedelta, timezone

    # Set the expiration time to 10 minutes from now
    exp = datetime.now(timezone.utc) + timedelta(seconds=expiration_time)

    payload = {
        'exp': exp,
        'walletAddress': wallet_address  # Send wallet address to the payload
    }
    
    # Encode the JWT
    token = jwt_encode(payload, secret_key, algorithm='HS256')
    return token

def calculate_ownership_score(jwt_token: str, data: dict, validator_url: str) -> float:
    """Calculate ownership score by verifying data against an external API."""
    if not jwt_token or not isinstance(jwt_token, str):
        raise ValueError('JWT token is required and must be a string')
    if not data.get('walletAddress'):
        raise ValueError('Invalid data format. Ensure walletAddress is a non-empty string and type is a non-empty array.')

    try:
        headers = {
            'Authorization': f'Bearer {jwt_token}',  # Attach JWT token in the Authorization header
        }

        endpoint = "/api/datavalidation"
        url = f"{validator_url.rstrip('/')}{endpoint}"

        response = requests.post(url, json=data, headers=headers)

        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        return 1.0 if response.status_code == 200 else 0.0
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during API request: {e}")
        return 0.0

    except requests.exceptions.HTTPError as error:
        logging.error(f"API call failed: {error}")
        if error.response.status_code == 400:
            return 0.0
        raise ValueError(f'API call failed: {error.response.json().get("error", str(error))}')
