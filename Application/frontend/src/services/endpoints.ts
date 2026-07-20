export const endpoints = {
  users: {
    base: "",
    detail: (userId: string) => `/${userId}`,
  },
  grades: {
    courses: (userId: string) => `/${userId}/courses`,
    dashboard: (userId: string) => `/${userId}/grades/dashboard`,
    courseDetail: (userId: string, courseId: string) => `/${userId}/courses/${courseId}`,
    CategoryWeights: (userId: string, courseId: string) => `/${userId}/courses/${courseId}/category-weights`,
    courseGrades: (userId: string, courseId: string) => `/${userId}/courses/${courseId}/grades`,
    gradeDetail: (userId: string, courseId: string, gradeId: string) => `/${userId}/courses/${courseId}/grades/${gradeId}`,
  },
  calendar: {
    events: (userId: string) => `/${userId}/events`,
  },
  tasks: {
    list: (userId: string) => `/${userId}/tasks`,
  },
  finances: {
    budgets: (userId: string) => `/${userId}/budgets`,
    goals: (userId: string) => `/${userId}/goals`,
  },
};
