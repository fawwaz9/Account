
error_course = {
    "not_found": "Course not found",
    "already_exists": "Course code already exists",
    "invalid_average": "Invalid course average."
}

error_grade = {
    "not_found": "Grade not found",
    "invalid_data": "Invalid grade data."
}

error_user = {
    "not_found": "User not found",
    "already_exists": "User email already exists",
    "invalid_data": "Invalid user data."
}

error_auth = {
    # Deliberately identical for "no such account", "Google-only account", and
    # "wrong password" — a distinct message for each would turn the login
    # endpoint into an account-enumeration oracle.
    "invalid_credentials": "Invalid email or password",
}

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
    "auth_409": {400: {"description": error_user["already_exists"]}}
}

weight_error = {
    "invalid_weights": "Invalid category weights. The sum of weights must be less than or equal to 100.",
    "invalid_weight_value": "Invalid weight value. Each weight must be between 0 and 100."
}
