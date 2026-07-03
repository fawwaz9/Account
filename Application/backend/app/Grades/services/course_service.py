from uuid import UUID, uuid4

from Application.backend.app.Grades.schemas.course import CourseCreate, CourseDetail, CourseUpdate
from Application.backend.app.Grades.services.grade_service import calculate_current_average, update_category_weights
from Application.backend.app.Users.services.user_service import get_user

def create_course(user_id: UUID, course_data: CourseCreate):
    user = get_user(user_id)
    if user is None:
        return None

    course = CourseDetail(
        id=uuid4(),
        grades=[],
        average=0.0,
        **course_data.model_dump()
    )
    for c in user.courses:
        if c.code == course_data.code:
            raise ValueError("course code already exists")

    user.courses.append(course)
    return course

def get_all_courses(user_id: UUID):
    user = get_user(user_id)
    if user is None:
        return None

    for course in user.courses:
        course.average = calculate_current_average(course)
    return user.courses

def get_course(user_id: UUID, course_id: UUID):
    user = get_user(user_id)
    if user is None:
        return None

    for course in user.courses:
        if course.id == course_id:
            return course
    return None

def update_course(user_id: UUID, course_id: UUID, data: CourseUpdate):
    course = get_course(user_id, course_id)
    if not course:
        return None

    update_data = data.model_dump(exclude_unset=True)
    category_weights = update_data.pop("category_weights", None)
    for key, value in update_data.items():
        setattr(course, key, value)

    if category_weights is not None:
        update_category_weights(user_id, course_id, category_weights)

    return course

def delete_course(user_id: UUID, course_id: UUID):
    user = get_user(user_id)
    if user is None:
        return None

    course = get_course(user_id, course_id)
    if not course:
        return None

    user.courses.remove(course)
    return course

def get_course_statistics(user_id: UUID, course_id: UUID):
    course = get_course(user_id, course_id)
    if not course:
        return None
    
    average = calculate_current_average(course)
    return {
        "course_id": course.id,
        "course_code": course.code,
        "current_grade": average
    }
    
def search_courses(user_id: UUID, query: str):
    user = get_user(user_id)
    if user is None:
        return None

    query_lower = query.lower()
    return [
        course for course in user.courses
        if query_lower in course.code.lower() or query_lower in course.name.lower()
    ]


