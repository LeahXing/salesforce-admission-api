import os
from dotenv import load_dotenv

load_dotenv()

# Salesforce Configuration
SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
SALESFORCE_DOMAIN = os.getenv("SALESFORCE_DOMAIN", "")
SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL", "")
