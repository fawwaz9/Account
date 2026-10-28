"""Shared error messages, OpenAPI response descriptions and the category-weight limits.

Services raise with these strings and routes map them to status codes, so a message
a client tests against lives in one place.
"""

error_course = {
    "not_found": "Course not found",
    "already_exists": "Course code already exists",
    "invalid_average": "Invalid course average."
}
"""Course error messages by key."""

error_grade = {
    "not_found": "Grade not found",
    "invalid_data": "Invalid grade data."
}
"""Grade error messages by key."""

error_user = {
    "not_found": "User not found",
    "already_exists": "User email already exists",
    "invalid_data": "Invalid user data."
}
"""User error messages by key."""

error_auth = {
    # Deliberately identical for "no such account", "Google-only account", and
    # "wrong password" — a distinct message for each would turn the login
    # endpoint into an account-enumeration oracle.
    "invalid_credentials": "Invalid email or password",
    # Registration inherently reveals that an address is taken, so naming the
    # provider costs no extra information and saves the user a dead end.
    "use_google": (
        "This email is already registered with Google. Sign in with Google, "
        "then add a password from your account settings."
    ),
    # Says what is true without saying who is on the list. "Not invited" would
    # be the honest short version and is also a probe: it tells an attacker
    # which addresses the owner knows. This declines without confirming or
    # denying anything about any particular address.
    "not_invited": (
        "This app is invitation only. Ask the person who runs it to add your "
        "email address."
    ),
    "wrong_current_password": "Current password is incorrect",
    "current_password_required": "Current password is required to change an existing password",
}
"""Authentication error messages by key.

`invalid_credentials` is the same for every login failure, so login never reveals
whether an account exists.
"""

responses = {
    "course_404": {404: {"description": error_course["not_found"]}},
    "course_400": {400: {"description": error_course["already_exists"]}},
    "grade_404": {404: {"description": error_grade["not_found"]}},
    "grade_400": {400: {"description": error_grade["invalid_data"]}},
    "user_404": {404: {"description": error_user["not_found"]}},
    "user_400": {400: {"description": error_user["invalid_data"]}},
    "course_both" : {404: {"description": error_course["not_found"]}, 400: {"description": error_course["already_exists"]}},
    "grade_both": {404: {"description": error_grade["not_found"]}, 400: {"description": error_grade["invalid_data"]}},
    "user_both": {404: {"description": error_user["not_found"]}, 400: {"description": error_user["invalid_data"]}},
    "auth_401": {401: {"description": error_auth["invalid_credentials"]}},
    "auth_409": {400: {"description": error_user["already_exists"]}},
    "auth_password": {400: {"description": error_auth["wrong_current_password"]}}
}
"""Reusable `responses=` entries for route decorators, documenting error statuses."""

# Totals above 100 are legitimate: a course can be marked out of 101%, or carry
# an explicit bonus category, and the extra acts as bonus rather than inflating
# the denominator. Only nonsense totals are rejected.
MAX_TOTAL_WEIGHT = 200.0

weight_error = {
    "invalid_weights": f"Invalid category weights. The sum of weights cannot exceed {MAX_TOTAL_WEIGHT:g}.",
    "invalid_weight_value": "Invalid weight value. Each weight must be between 0 and 100."
}
"""Messages for a rejected category weight or weight total."""
