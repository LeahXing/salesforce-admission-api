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

    customer_data = {
        key: value
        for key, value in customer_data.items()
        if value is not None
    }

    result = sf.Customer.create(customer_data)

    return result["id"]