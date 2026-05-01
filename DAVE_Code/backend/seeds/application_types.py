"""
Seed data for DAVE.

Run via:  python -m backend.seeds.application_types
Or call seed_all() from init_db.py after index creation.
"""
import asyncio
from datetime import datetime, timezone

from backend.auth.security import hash_password
from backend.database import close_mongo_connection, connect_to_mongo, db

SUSI_GRANT = {
    "type_name": "SUSI Grant Application",
    "description": (
        "Student Universal Support Ireland (SUSI) grant for eligible "
        "full-time students in approved courses."
    ),
    "form_fields": [
        {"field_name": "full_name",       "label": "Full Name",         "field_type": "text",     "is_required": True,  "order": 1, "validation": {"min_length": 2, "max_length": 100}},
        {"field_name": "student_id",      "label": "Student ID",        "field_type": "text",     "is_required": True,  "order": 2, "validation": {"pattern": r"^\d{7,10}$"}, "help_text": "Your college student number"},
        {"field_name": "email",           "label": "Email Address",     "field_type": "email",    "is_required": True,  "order": 3},
        {"field_name": "phone",           "label": "Phone Number",      "field_type": "phone",    "is_required": False, "order": 4},
        {"field_name": "marital_status",  "label": "Marital Status",    "field_type": "dropdown", "is_required": True,  "order": 5, "options": ["Single", "Married", "Separated", "Divorced", "Widowed"]},
        {"field_name": "dependents",      "label": "Number of Dependents", "field_type": "number", "is_required": False, "order": 6, "validation": {"min_value": 0, "max_value": 20}},
        {"field_name": "income_range",    "label": "Annual Household Income Range", "field_type": "dropdown", "is_required": True, "order": 7, "options": ["Under €20,000", "€20,001–€40,000", "€40,001–€60,000", "Over €60,000"]},
        {"field_name": "course_name",     "label": "Course Name",       "field_type": "text",     "is_required": True,  "order": 8},
        {"field_name": "year_of_study",   "label": "Year of Study",     "field_type": "dropdown", "is_required": True,  "order": 9, "options": ["1", "2", "3", "4", "5"]},
        {
            "field_name": "spouse_name", "label": "Spouse / Partner Full Name", "field_type": "text",
            "is_required": True, "order": 10,
            "conditional_display": {"field": "marital_status", "operator": "eq", "value": "Married"},
            "help_text": "Required for married applicants",
        },
    ],
    "required_documents": [
        {"document_type": "ID Card",              "is_mandatory": True,  "has_expiry": True,  "description": "National ID card or passport", "acceptable_formats": ["PDF", "JPG", "PNG"]},
        {"document_type": "Proof of Income",      "is_mandatory": True,  "has_expiry": False, "description": "P60 or most recent tax assessment", "acceptable_formats": ["PDF"]},
        {"document_type": "Enrollment Certificate", "is_mandatory": True, "has_expiry": False, "description": "Current academic year enrollment letter", "acceptable_formats": ["PDF"]},
        {
            "document_type": "Marriage Certificate", "is_mandatory": True, "has_expiry": False,
            "description": "Required for married applicants only",
            "acceptable_formats": ["PDF", "JPG", "PNG"],
            "conditional_requirement": {"field": "marital_status", "operator": "eq", "value": "Married"},
        },
    ],
    "validation_rules": [],
}

UNIVERSITY_ADMISSIONS = {
    "type_name": "University Admissions",
    "description": "Application for undergraduate or postgraduate admission to university.",
    "form_fields": [
        {"field_name": "full_name",          "label": "Full Name",              "field_type": "text",     "is_required": True,  "order": 1, "validation": {"min_length": 2, "max_length": 100}},
        {"field_name": "email",              "label": "Email Address",          "field_type": "email",    "is_required": True,  "order": 2},
        {"field_name": "phone",              "label": "Phone Number",           "field_type": "phone",    "is_required": True,  "order": 3},
        {"field_name": "date_of_birth",      "label": "Date of Birth",          "field_type": "date",     "is_required": True,  "order": 4},
        {"field_name": "address",            "label": "Home Address",           "field_type": "text",     "is_required": True,  "order": 5, "validation": {"min_length": 10}},
        {"field_name": "previous_education", "label": "Highest Qualification",  "field_type": "dropdown", "is_required": True,  "order": 6, "options": ["Leaving Certificate", "A-Levels", "Bachelor's Degree", "Master's Degree", "Other"]},
        {"field_name": "course_preference",  "label": "Preferred Course / Programme", "field_type": "text", "is_required": True, "order": 7},
        {"field_name": "level",              "label": "Level Applying For",     "field_type": "dropdown", "is_required": True,  "order": 8, "options": ["Undergraduate", "Postgraduate"]},
    ],
    "required_documents": [
        {"document_type": "Passport or ID",          "is_mandatory": True,  "has_expiry": True,  "description": "Valid passport or national ID card"},
        {"document_type": "Educational Certificates", "is_mandatory": True,  "has_expiry": False, "description": "Transcripts and certificates for highest qualification obtained"},
        {"document_type": "Personal Statement",       "is_mandatory": True,  "has_expiry": False, "description": "PDF of your personal statement (max 1,000 words)", "acceptable_formats": ["PDF"]},
        {"document_type": "Reference Letter",         "is_mandatory": False, "has_expiry": False, "description": "Academic or professional reference letter", "acceptable_formats": ["PDF"]},
    ],
    "validation_rules": [],
}

VISA_APPLICATION = {
    "type_name": "Visa Application",
    "description": "Application for a short-stay or student visa.",
    "form_fields": [
        {"field_name": "full_name",        "label": "Full Name (as on passport)", "field_type": "text",     "is_required": True,  "order": 1, "validation": {"min_length": 2, "max_length": 100}},
        {"field_name": "passport_number",  "label": "Passport Number",            "field_type": "text",     "is_required": True,  "order": 2},
        {"field_name": "nationality",      "label": "Nationality",                "field_type": "text",     "is_required": True,  "order": 3},
        {"field_name": "date_of_birth",    "label": "Date of Birth",              "field_type": "date",     "is_required": True,  "order": 4},
        {"field_name": "purpose",          "label": "Purpose of Visit",           "field_type": "dropdown", "is_required": True,  "order": 5, "options": ["Tourism", "Study", "Work", "Family Visit", "Medical", "Other"]},
        {"field_name": "duration_days",    "label": "Intended Stay (days)",       "field_type": "number",   "is_required": True,  "order": 6, "validation": {"min_value": 1, "max_value": 365}},
        {"field_name": "home_address",     "label": "Home Country Address",       "field_type": "text",     "is_required": True,  "order": 7, "validation": {"min_length": 10}},
        {"field_name": "destination_address", "label": "Address in Ireland",      "field_type": "text",     "is_required": True,  "order": 8},
    ],
    "required_documents": [
        {"document_type": "Passport",          "is_mandatory": True,  "has_expiry": True,  "description": "Valid passport (must be valid for 6 months beyond stay)"},
        {"document_type": "Passport Photo",    "is_mandatory": True,  "has_expiry": False, "description": "Recent passport-style photograph", "acceptable_formats": ["JPG", "PNG"]},
        {"document_type": "Bank Statement",    "is_mandatory": True,  "has_expiry": False, "description": "Last 3 months' bank statements showing sufficient funds", "acceptable_formats": ["PDF"]},
        {"document_type": "Travel Insurance",  "is_mandatory": True,  "has_expiry": True,  "description": "Travel insurance policy covering the full duration of stay"},
    ],
    "validation_rules": [],
}

DEFAULT_APPLICATION_TYPES = [SUSI_GRANT, UNIVERSITY_ADMISSIONS, VISA_APPLICATION]

DEFAULT_ADMIN = {
    "email": "admin@dave.ie",
    "password": "Admin@1234",  # Change immediately after first login!
    "full_name": "DAVE Super Admin",
    "role": "super_admin",
}

async def seed_application_types(system_user_id) -> None:
    now = datetime.now(timezone.utc)
    for atype in DEFAULT_APPLICATION_TYPES:
        existing = await db.application_types.find_one({"type_name": atype["type_name"]})
        if existing:
            print(f"  [skip] Application type '{atype['type_name']}' already exists")
            continue
        doc = {
            **atype,
            "status": "active",
            "created_by": system_user_id,
            "created_at": now,
            "updated_at": now,
        }
        await db.application_types.insert_one(doc)
        print(f"  [created] Application type: {atype['type_name']}")


async def seed_admin_user() -> None:
    existing_admin = await db.users.find_one(
        {"role": {"$in": ["admin", "super_admin"]}}
    )
    if existing_admin:
        print(f"  [skip] Admin user already exists: {existing_admin['email']}")
        return

    now = datetime.now(timezone.utc)
    result = await db.users.insert_one({
        "email": DEFAULT_ADMIN["email"],
        "password_hash": hash_password(DEFAULT_ADMIN["password"]),
        "full_name": DEFAULT_ADMIN["full_name"],
        "phone": None,
        "role": DEFAULT_ADMIN["role"],
        "is_active": True,
        "is_verified": True,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
        "failed_login_attempts": 0,
        "locked_until": None,
        "notification_preferences": {},
        "settings": {"language": "en", "timezone": "UTC", "date_format": "DD/MM/YYYY"},
    })
    print(f"  [created] Admin user: {DEFAULT_ADMIN['email']} (password: {DEFAULT_ADMIN['password']})")
    return result.inserted_id


async def seed_all() -> None:
    print("Seeding database...")
    # Ensure admin exists first, use their id as creator for app types
    admin_id = await seed_admin_user()
    if admin_id is None:
        # Admin already existed – fetch their id
        admin_doc = await db.users.find_one({"role": {"$in": ["admin", "super_admin"]}})
        admin_id = admin_doc["_id"]
    await seed_application_types(system_user_id=admin_id)
    print("Seeding complete.")
    
async def _main():
    await connect_to_mongo()
    await seed_all()
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(_main())
