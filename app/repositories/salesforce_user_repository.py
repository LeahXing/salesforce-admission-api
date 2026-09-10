from app.core.salesforce import get_salesforce


# ==========================================
# Find User by Email or Phone
# ==========================================

def find_user(email: str, phone_number: str):
    sf = get_salesforce()

    query = f"""
        SELECT
            Id,
            Application_No__c,
            First_Name__c,
            Last_Name__c,
            Email__c,
            Phone__c,
            Course__c,
            Conversation_ID__c,
            Sentiment__c,
            Offer_Letter_Released__c,
            Offer_Letter_Accepted__c
        FROM Customer
        WHERE Email__c = '{email}'
           OR Phone__c = '{phone_number}'
        LIMIT 1
    """

    result = sf.query(query)

    if result["totalSize"] == 0:
        return None

    return result["records"][0]


# ==========================================
# Create New User
# ==========================================

def create_user(
    application_no: str,
    first_name: str,
    last_name: str,
    email: str,
    phone_number: str,
    conversation_id: str,
    course: str | None = None,
):
    sf = get_salesforce()

    customer_data = {
        "Name": application_no,
        "Application_No__c": application_no,
        "First_Name__c": first_name,
        "Last_Name__c": last_name,
        "Email__c": email,
        "Phone__c": phone_number,
        "Conversation_ID__c": conversation_id,
        "Course__c": course,
        "Offer_Letter_Released__c": False,
    }

    # Remove fields with None values
    customer_data = {
        key: value
        for key, value in customer_data.items()
        if value is not None
    }

    result = sf.Customer.create(customer_data)

    return result["id"]


# ==========================================
# Get User by Salesforce Customer ID
# ==========================================

def get_user_by_id(user_id: str):
    sf = get_salesforce()

    try:
        return sf.Customer.get(user_id)

    except Exception:
        return None


# ==========================================
# Update User Status
# ==========================================

def update_user_status(
    user_id: str,
    sentiment: str | None = None,
    offer_letter_released: bool | None = None,
    offer_letter_accepted: str | None = None,
):
    sf = get_salesforce()

    update_data = {}

    if sentiment is not None:
        update_data["Sentiment__c"] = sentiment

    if offer_letter_released is not None:
        update_data["Offer_Letter_Released__c"] = offer_letter_released

    if offer_letter_accepted is not None:
        update_data["Offer_Letter_Accepted__c"] = offer_letter_accepted

    if not update_data:
        return get_user_by_id(user_id)

    sf.Customer.update(
        user_id,
        update_data,
    )

    return get_user_by_id(user_id)