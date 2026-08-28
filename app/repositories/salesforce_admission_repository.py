from app.core.salesforce import get_salesforce


# ==========================================
# Get All Admission Applications
# ==========================================

def get_all_admissions():
    sf = get_salesforce()

    result = sf.query("""
        SELECT
            Id,
            Application_No__c,
            Student_ID__c,
            First_Name__c,
            Last_Name__c,
            Email__c,
            Phone__c,
            City__c,
            Gender__c,
            Course__c,
            Major__c,
            Advising_College__c,
            Intake__c,
            Semester__c,
            Residency__c,
            Admission_Status__c,
            Approved_By__c,
            Offer_Status__c,
            Offer_Sent_At__c,
            Sentiment__c,
            University_ID__c,
            Remarks__c,
            Created_At__c,
            Updated_At__c,
            Testing_Record__c
        FROM Customer
        ORDER BY CreatedDate DESC
    """)

    return result["records"]


# ==========================================
# Get Admission Application by Salesforce ID
# ==========================================

def get_admission_by_id(application_id):
    sf = get_salesforce()

    return sf.Customer.get(application_id)


# ==========================================
# Create Admission Application
# ==========================================

def create_admission(admission_data):
    sf = get_salesforce()

    application_no = admission_data["Application_No__c"]

    customer_data = admission_data.copy()

    # Salesforce Customer Name is required
    customer_data["Name"] = application_no

    result = sf.Customer.create(customer_data)

    return result


# ==========================================
# Update Admission Application
# ==========================================

def update_admission(application_id, admission_data):
    sf = get_salesforce()

    result = sf.Customer.update(
        application_id,
        admission_data,
    )

    return result


# ==========================================
# Delete Admission Application
# ==========================================

def delete_admission(application_id):
    sf = get_salesforce()

    result = sf.Customer.delete(application_id)

    return result
