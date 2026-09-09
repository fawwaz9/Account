export const endpoints = {
  users: {
    base: "users",
    detail: (userId: string) => `users/${userId}`,
    me: "users/me",
    academicStatus: (userId: string) => `users/${userId}/academic-status`,
  },
  grades: {
    courses: (userId: string) => `grades/${userId}/courses`,
    dashboard: (userId: string) => `grades/${userId}/grades/dashboard`,
    courseDetail: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}`,
    CategoryWeights: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/category-weights`,
    requiredFinal: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/required-final`,
    courseGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades`,
    bulkGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades/bulk`,
    gradeDetail: (userId: string, courseId: string, gradeId: string) => `grades/${userId}/courses/${courseId}/grades/${gradeId}`,
  },
  calendar: {
    events: (userId: string) => `calendar/${userId}/events`,
  },
  tasks: {
    list: (userId: string) => `tasks/${userId}/tasks`,
  },
  finances: {
    accounts: (userId: string) => `finances/${userId}/accounts`,
    account: (userId: string, accountId: string) => `finances/${userId}/accounts/${accountId}`,
    transactions: (userId: string) => `finances/${userId}/transactions`,
    transaction: (userId: string, transactionId: string) =>
      `finances/${userId}/transactions/${transactionId}`,
    transfers: (userId: string) => `finances/${userId}/transfers`,
    categories: (userId: string) => `finances/${userId}/categories`,
    category: (userId: string, categoryId: string) => `finances/${userId}/categories/${categoryId}`,
    budgetTargets: (userId: string) => `finances/${userId}/budget-targets`,
    budgetSummary: (userId: string) => `finances/${userId}/budget-summary`,
  },
};