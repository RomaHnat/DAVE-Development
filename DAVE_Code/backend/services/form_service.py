import re
from typing import Any, Dict, List, Optional

def evaluate_condition(form_data: Dict[str, Any], condition: Dict[str, Any]) -> bool:

    if not condition:
        return True
    field = condition.get("field")
    operator = condition.get("operator", "eq")
    value = condition.get("value")
    form_value = form_data.get(field)

    if operator == "eq":
        return form_value == value
    if operator == "ne":
        return form_value != value
    if operator == "in":
        return form_value in (value or [])
    if operator == "not_in":
        return form_value not in (value or [])
    if operator == "exists":
        return form_value is not None and str(form_value).strip() != ""
    if operator == "not_exists":
        return form_value is None or str(form_value).strip() == ""
    return True

def validate_form_data(
    form_data: Dict[str, Any],
    form_fields: List[Dict[str, Any]],
) -> List[str]:

    errors: List[str] = []

    for field_def in form_fields:
        field_name: str = field_def.get("field_name", "")
        label: str = field_def.get("label", field_name)
        is_required: bool = field_def.get("is_required", False)
        field_type: str = field_def.get("field_type", "text")
        validation: Dict[str, Any] = field_def.get("validation") or {}
        options: List[str] = field_def.get("options") or []
        conditional = field_def.get("conditional_display")

        # Skip fields whose display condition is not met
        if conditional and not evaluate_condition(form_data, conditional):
            continue

        value = form_data.get(field_name)
        is_empty = value is None or str(value).strip() == ""

        if is_required and is_empty:
            errors.append(f"'{label}' is required")
            continue

        if is_empty:
            continue  # Optional field with no value – skip further checks

        str_val = str(value).strip()

        # Type-specific validation
        if field_type == "email":
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str_val):
                errors.append(f"'{label}' must be a valid email address")

        elif field_type == "phone":
            if not re.match(r"^\+?[\d\s\-()\\.]{7,25}$", str_val):
                errors.append(f"'{label}' must be a valid phone number")

        elif field_type == "number":
            try:
                num = float(str_val)
                if "min_value" in validation and num < float(validation["min_value"]):
                    errors.append(f"'{label}' must be at least {validation['min_value']}")
                if "max_value" in validation and num > float(validation["max_value"]):
                    errors.append(f"'{label}' must be at most {validation['max_value']}")
            except ValueError:
                errors.append(f"'{label}' must be a number")

        elif field_type == "date":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str_val):
                errors.append(f"'{label}' must be a date in YYYY-MM-DD format")

        elif field_type in ("dropdown", "radio"):
            if options and str_val not in options:
                errors.append(f"'{label}' must be one of: {', '.join(options)}")

        elif field_type == "checkbox":
            if str_val.lower() not in ("true", "false", "1", "0", "yes", "no"):
                errors.append(f"'{label}' must be a boolean value")

        # Length constraints
        if "min_length" in validation and len(str_val) < int(validation["min_length"]):
            errors.append(
                f"'{label}' must be at least {validation['min_length']} characters"
            )
        if "max_length" in validation and len(str_val) > int(validation["max_length"]):
            errors.append(
                f"'{label}' must be at most {validation['max_length']} characters"
            )

        # Regex pattern constraint
        if "pattern" in validation:
            if not re.match(validation["pattern"], str_val):
                errors.append(f"'{label}' has an invalid format")

    return errors


def get_visible_fields(
    form_fields: List[Dict[str, Any]],
    form_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        f for f in form_fields
        if not f.get("conditional_display")
        or evaluate_condition(form_data, f["conditional_display"])
    ]


def get_required_documents(
    required_documents: List[Dict[str, Any]],
    form_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        doc for doc in required_documents
        if not doc.get("conditional_requirement")
        or evaluate_condition(form_data, doc["conditional_requirement"])
    ]


def calculate_validation_score(
    form_data: Dict[str, Any],
    form_fields: List[Dict[str, Any]],
) -> float:
    visible = get_visible_fields(form_fields, form_data)
    required = [f for f in visible if f.get("is_required", False)]
    if not required:
        return 100.0
    filled = sum(
        1 for f in required
        if form_data.get(f["field_name"]) is not None
        and str(form_data[f["field_name"]]).strip() != ""
    )
    return round(filled / len(required) * 100, 1)
