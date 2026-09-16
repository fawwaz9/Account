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
    resolveCourse: (userId: string) => `grades/${userId}/courses/resolve`,
    blindSpots: (userId: string) => `grades/${userId}/category-blind-spots`,
    gradeBand: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grade-band`,
    cheapestPath: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/cheapest-path`,
    courseGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades`,
    bulkGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades/bulk`,
    gradeDetail: (userId: string, courseId: string, gradeId: string) => `grades/${userId}/courses/${courseId}/grades/${gradeId}`,
  },
  calendar: {
    /** Materialised occurrences for a window; takes ?start= and ?end=. */
    agenda: (userId: string) => `calendar/${userId}/agenda`,
    freeBlocks: (userId: string) => `calendar/${userId}/free-blocks`,
    weekLoad: (userId: string) => `calendar/${userId}/week-load`,
    crunch: (userId: string) => `calendar/${userId}/crunch`,
    blackouts: (userId: string) => `calendar/${userId}/blackouts`,
    blackout: (userId: string, id: string) => `calendar/${userId}/blackouts/${id}`,
    events: (userId: string) => `calendar/${userId}/events`,
    event: (userId: string, eventId: string) => `calendar/${userId}/events/${eventId}`,
    restoreOccurrence: (userId: string, eventId: string) =>
      `calendar/${userId}/events/${eventId}/restore`,
    classSchedule: (userId: string, courseId: string) =>
      `calendar/${userId}/courses/${courseId}/class-schedule`,
  },
  tasks: {
    list: (userId: string) => `tasks/${userId}/tasks`,
    detail: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}`,
    repeating: (userId: string) => `tasks/${userId}/repeating`,
    repeatingRule: (userId: string, ruleId: string) => `tasks/${userId}/repeating/${ruleId}`,
    /** Writes each repeat's window. Idempotent, so it is safe on every load. */
    repeatingRun: (userId: string) => `tasks/${userId}/repeating/run`,
    repeatingSkip: (userId: string, ruleId: string) =>
      `tasks/${userId}/repeating/${ruleId}/skip`,
    /** GET previews what a line means; POST creates the task it describes. */
    quickCapture: (userId: string) => `tasks/${userId}/quick-capture`,
    /** Declared above /tasks/{task_id} on the server, or "timing" parses as an id. */
    timing: (userId: string) => `tasks/${userId}/tasks/timing`,
    snooze: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}/snooze`,
    reminders: (userId: string) => `tasks/${userId}/reminders`,
    /** Declared above /reminders/{id} on the server, or "due" parses as an id. */
    remindersDue: (userId: string) => `tasks/${userId}/reminders/due`,
    reminder: (userId: string, reminderId: string) =>
      `tasks/${userId}/reminders/${reminderId}`,
    dismissReminder: (userId: string, reminderId: string) =>
      `tasks/${userId}/reminders/${reminderId}/dismiss`,
    snoozes: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}/snoozes`,
  },
  jobs: {
    list: (userId: string) => `jobs/${userId}/jobs`,
    detail: (userId: string, jobId: string) => `jobs/${userId}/jobs/${jobId}`,
    schedule: (userId: string, jobId: string) => `jobs/${userId}/jobs/${jobId}/schedule`,
    /** Declared above /jobs/{job_id} on the server, or "shifts" parses as an id. */
    shifts: (userId: string) => `jobs/${userId}/jobs/shifts`,
    addShift: (userId: string, jobId: string) => `jobs/${userId}/jobs/${jobId}/shifts`,
    shift: (userId: string, eventId: string) => `jobs/${userId}/jobs/shifts/${eventId}`,
    shiftRecord: (userId: string, eventId: string, onDate: string) =>
      `jobs/${userId}/jobs/shifts/${eventId}/${onDate}`,
    earnings: (userId: string) => `jobs/${userId}/earnings`,
    paycheques: (userId: string) => `jobs/${userId}/paycheques`,
    /** Declared above /paycheques/{id} on the server, or "preview" parses as an id. */
    paychequePreview: (userId: string) => `jobs/${userId}/paycheques/preview`,
    paycheque: (userId: string, paychequeId: string) =>
      `jobs/${userId}/paycheques/${paychequeId}`,
  },
  omnibox: {
    /** GET previews which module a line goes to; POST files it there. */
    base: (userId: string) => `omnibox/${userId}`,
  },
  finances: {
    safeToSpend: (userId: string) => `finances/${userId}/safe-to-spend`,
    subscriptions: (userId: string) => `finances/${userId}/subscriptions`,
    confirmSubscription: (userId: string) => `finances/${userId}/subscriptions/confirm`,
    sinkingFunds: (userId: string) => `finances/${userId}/sinking-funds`,
    sinkingFund: (userId: string, fundId: string) =>
      `finances/${userId}/sinking-funds/${fundId}`,
    contribute: (userId: string, fundId: string) =>
      `finances/${userId}/sinking-funds/${fundId}/contribute`,
    contribution: (userId: string, fundId: string, contributionId: string) =>
      `finances/${userId}/sinking-funds/${fundId}/contributions/${contributionId}`,
    netWorth: (userId: string) => `finances/${userId}/net-worth`,
    accounts: (userId: string) => `finances/${userId}/accounts`,
    account: (userId: string, accountId: string) => `finances/${userId}/accounts/${accountId}`,
    accountActivity: (userId: string, accountId: string) =>
      `finances/${userId}/accounts/${accountId}/activity`,
    transactions: (userId: string) => `finances/${userId}/transactions`,
    transaction: (userId: string, transactionId: string) =>
      `finances/${userId}/transactions/${transactionId}`,
    transfers: (userId: string) => `finances/${userId}/transfers`,
    categories: (userId: string) => `finances/${userId}/categories`,
    category: (userId: string, categoryId: string) => `finances/${userId}/categories/${categoryId}`,
    budgetTargets: (userId: string) => `finances/${userId}/budget-targets`,
    budgetSummary: (userId: string) => `finances/${userId}/budget-summary`,
    termBudget: (userId: string) => `finances/${userId}/term-budget`,
    deposits: (userId: string) => `finances/${userId}/deposits`,
    depositPreview: (userId: string) => `finances/${userId}/deposit-preview`,
    tuition: (userId: string) => `finances/${userId}/tuition`,
    tuitionPayment: (userId: string, paymentId: string) =>
      `finances/${userId}/tuition/${paymentId}`,
    tuitionPreview: (userId: string) => `finances/${userId}/tuition/preview`,
    courseCost: (userId: string, courseId: string) =>
      `finances/${userId}/courses/${courseId}/cost`,
    recurring: (userId: string) => `finances/${userId}/recurring`,
    recurringRule: (userId: string, ruleId: string) => `finances/${userId}/recurring/${ruleId}`,
    /** Writes any payment that is owed. Idempotent, so it is safe on every load. */
    recurringRun: (userId: string) => `finances/${userId}/recurring/run`,
    /** Projections, not rows: what is committed but has not happened yet. */
    recurringUpcoming: (userId: string) => `finances/${userId}/recurring/upcoming`,
    recurringSkip: (userId: string, ruleId: string) =>
      `finances/${userId}/recurring/${ruleId}/skip`,
  },
};