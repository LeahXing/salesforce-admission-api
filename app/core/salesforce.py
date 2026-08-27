import requests
from simple_salesforce import Salesforce

from app.core.config import (
    SALESFORCE_CLIENT_ID,
    SALESFORCE_CLIENT_SECRET,
    SALESFORCE_DOMAIN,
)


# ==========================================
# Get Salesforce Access Token
# ==========================================

def get_salesforce_token():
    """Get Salesforce OAuth access token."""

    token_url = f"{SALESFORCE_DOMAIN}/services/oauth2/token"

    response = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": SALESFORCE_CLIENT_ID,
            "client_secret": SALESFORCE_CLIENT_SECRET,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


# ==========================================
# Create Salesforce Connection
# ==========================================

def get_salesforce():
    """Create and return an authenticated Salesforce client."""

    token_data = get_salesforce_token()

    sf = Salesforce(
        instance_url=token_data["instance_url"],
        session_id=token_data["access_token"],
    )

    return sf
