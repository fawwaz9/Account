export const endpoints = {
  users: {
    base: "users",
    detail: (userId: string) => `users/${userId}`,
    me: "users/me",
  },
  grades: {
    courses: (userId: string) => `grades/${userId}/courses`,
    dashboard: (userId: string) => `grades/${userId}/grades/dashboard`,
    courseDetail: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}`,
    CategoryWeights: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/category-weights`,
    courseGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades`,
    gradeDetail: (userId: string, courseId: string, gradeId: string) => `grades/${userId}/courses/${courseId}/grades/${gradeId}`,
  },
  calendar: {
    events: (userId: string) => `calendar/${userId}/events`,
  },
  tasks: {
    list: (userId: string) => `tasks/${userId}/tasks`,
  },
  finances: {
    budgets: (userId: string) => `finances/${userId}/budgets`,
    goals: (userId: string) => `finances/${userId}/goals`,
  },
};