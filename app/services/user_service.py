import uuid

from app.repositories.salesforce_user_repository import (
    find_user,
    create_user,
    get_user_by_id,
    update_user_status,
    delete_user as delete_user_repository,
)

# ==========================================
# Split Full Name
# ==========================================

def split_name(name: str):
    parts = name.strip().split()

    if len(parts) == 1:
        return parts[0], ""

    first_name = parts[0]
    last_name = " ".join(parts[1:])

    return first_name, last_name


# ==========================================
# Generate Application Number
# ==========================================

def generate_application_no():
    return f"APP-{uuid.uuid4().hex[:10].upper()}"


# ==========================================
# Format Salesforce User for API Response
# ==========================================

def format_user_response(user):
    first_name = user.get("First_Name__c") or ""
    last_name = user.get("Last_Name__c") or ""

    full_name = f"{first_name} {last_name}".strip()

    return {
        "userId": user["Id"],
        "name": full_name,
        "email": user.get("Email__c"),
        "phoneNumber": user.get("Phone__c"),
        "course": user.get("Course__c"),
        "conversationId": user.get("Conversation_ID__c"),
        "sentiment": user.get("Sentiment__c"),
        "offerLetterReleased": user.get(
            "Offer_Letter_Released__c",
            False,
        ),
        "offerLetterAccepted": user.get(
            "Offer_Letter_Accepted__c"
        ),
    }


# ==========================================
# Lookup Existing User or Create New User
# ==========================================

def lookup_or_create_user(data):
    existing_user = find_user(
        email=data.email,
        phone_number=data.phoneNumber,
    )

    # ------------------------------------------
    # Existing user found
    # ------------------------------------------
    if existing_user:
        return format_user_response(existing_user)

    # ------------------------------------------
    # User not found -> create one new user
    # ------------------------------------------
    first_name, last_name = split_name(data.name)

    application_no = generate_application_no()

    user_id = create_user(
        application_no=application_no,
        first_name=first_name,
        last_name=last_name,
        email=data.email,
        phone_number=data.phoneNumber,
        conversation_id=data.conversationId,
        course=data.course,
    )

    new_user = get_user_by_id(user_id)

    return format_user_response(new_user)


# ==========================================
# Update User Status
# ==========================================

def update_user(data, user_id: str):
    existing_user = get_user_by_id(user_id)

    if existing_user is None:
        raise ValueError("User not found.")

    updated_user = update_user_status(
        user_id=user_id,
        sentiment=data.sentiment,
        offer_letter_released=data.offerLetterReleased,
        offer_letter_accepted=data.offerLetterAccepted,
    )

    return format_user_response(updated_user)

# ==========================================
# Delete User
# ==========================================

def delete_user(user_id: str):
    existing_user = get_user_by_id(user_id)

    if existing_user is None:
        raise ValueError("User not found.")

    delete_user_repository(user_id)

    return {
        "message": "User deleted successfully.",
        "userId": user_id,
    }