/** Every API path, grouped by module; the functions fill in the ids. */
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
    schemes: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/schemes`,
    countingScheme: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/counting-scheme`,
    scheme: (userId: string, courseId: string, schemeId: string) =>
      `grades/${userId}/courses/${courseId}/schemes/${schemeId}`,
    courseGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades`,
    bulkGrades: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/grades/bulk`,
    gradeDetail: (userId: string, courseId: string, gradeId: string) => `grades/${userId}/courses/${courseId}/grades/${gradeId}`,
    /** Search the shared course catalogue. */
    catalogue: (userId: string) => `grades/${userId}/catalogue`,
    courseCatalogue: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/catalogue`,
    /** A course's prerequisites, yours and the catalogue's, met or not. */
    prerequisites: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/prerequisites`,
    checkPrerequisite: (userId: string) => `grades/${userId}/prerequisites/check`,
    /** What past classes' shared answers say about a course, above each floor. */
    classFigures: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/class-figures`,
    /** Check in at a course's office hours. */
    officeHours: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/office-hours`,
    /** What can be done with outlines on a course: offer, read, apply (Phase 3 item 2). */
    outline: (userId: string, courseId: string) => `grades/${userId}/courses/${courseId}/outline`,
    /** One of your own check-ins, to undo it. */
    officeHoursCheckIn: (userId: string, checkinId: string) => `grades/${userId}/office-hours/${checkinId}`,
  },
  calendar: {
    /** Occurrences in a window; takes ?start= and ?end=. */
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
    /** Writes each repeat's window; idempotent, so safe on every load. */
    repeatingRun: (userId: string) => `tasks/${userId}/repeating/run`,
    repeatingSkip: (userId: string, ruleId: string) =>
      `tasks/${userId}/repeating/${ruleId}/skip`,
    /** GET previews what a line means; POST creates that task. */
    quickCapture: (userId: string) => `tasks/${userId}/quick-capture`,
    /** Literal path: the server declares it above the task-id route. */
    timing: (userId: string) => `tasks/${userId}/tasks/timing`,
    snooze: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}/snooze`,
    reminders: (userId: string) => `tasks/${userId}/reminders`,
    /** Literal path: the server declares it above the reminder-id route. */
    remindersDue: (userId: string) => `tasks/${userId}/reminders/due`,
    reminder: (userId: string, reminderId: string) =>
      `tasks/${userId}/reminders/${reminderId}`,
    dismissReminder: (userId: string, reminderId: string) =>
      `tasks/${userId}/reminders/${reminderId}/dismiss`,
    snoozes: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}/snoozes`,
    /** Literal path: the server declares it above the task-id route. */
    estimates: (userId: string) => `tasks/${userId}/tasks/estimates`,
    timerStart: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}/timer/start`,
    timerStop: (userId: string, taskId: string) => `tasks/${userId}/tasks/${taskId}/timer/stop`,
  },
  jobs: {
    list: (userId: string) => `jobs/${userId}/jobs`,
    detail: (userId: string, jobId: string) => `jobs/${userId}/jobs/${jobId}`,
    schedule: (userId: string, jobId: string) => `jobs/${userId}/jobs/${jobId}/schedule`,
    /** Literal path: the server declares it above the job-id route. */
    shifts: (userId: string) => `jobs/${userId}/jobs/shifts`,
    addShift: (userId: string, jobId: string) => `jobs/${userId}/jobs/${jobId}/shifts`,
    shift: (userId: string, eventId: string) => `jobs/${userId}/jobs/shifts/${eventId}`,
    shiftRecord: (userId: string, eventId: string, onDate: string) =>
      `jobs/${userId}/jobs/shifts/${eventId}/${onDate}`,
    earnings: (userId: string) => `jobs/${userId}/earnings`,
    /** Sits beside /earnings, outside /jobs/, so it never parses as a job id. */
    cashTipAccount: (userId: string) => `jobs/${userId}/cash-tip-account`,
    paycheques: (userId: string) => `jobs/${userId}/paycheques`,
    /** Literal path: the server declares it above the paycheque-id route. */
    paychequePreview: (userId: string) => `jobs/${userId}/paycheques/preview`,
    paycheque: (userId: string, paychequeId: string) =>
      `jobs/${userId}/paycheques/${paychequeId}`,
    paychequeCheck: (userId: string, paychequeId: string) =>
      `jobs/${userId}/paycheques/${paychequeId}/check`,
  },
  omnibox: {
    /** GET previews which module a line goes to; POST files it there. */
    base: (userId: string) => `omnibox/${userId}`,
  },
  usage: {
    visits: (userId: string) => `usage/${userId}/visits`,
  },
  survey: {
    pending: (userId: string) => `survey/${userId}/pending`,
    responses: (userId: string) => `survey/${userId}/responses`,
  },
  degree: {
    audit: (userId: string) => `degree/${userId}`,
    requirements: (userId: string) => `degree/${userId}/requirements`,
    requirement: (userId: string, id: string) => `degree/${userId}/requirements/${id}`,
    equivalences: (userId: string) => `degree/${userId}/equivalences`,
    equivalence: (userId: string, id: string) => `degree/${userId}/equivalences/${id}`,
  },
  intake: {
    status: (userId: string) => `intake/${userId}/status`,
    syllabus: (userId: string) => `intake/${userId}/syllabus`,
    apply: (userId: string, parseId: string) => `intake/${userId}/syllabus/${parseId}/apply`,
    courseSyllabi: (userId: string, courseId: string) => `intake/${userId}/courses/${courseId}/syllabi`,
    file: (userId: string, parseId: string) => `intake/${userId}/syllabus/${parseId}/file`,
    addTo: (userId: string, parseId: string, courseId: string) =>
      `intake/${userId}/syllabus/${parseId}/add-to/${courseId}`,
  },
  push: {
    status: (userId: string) => `push/${userId}/status`,
    subscriptions: (userId: string) => `push/${userId}/subscriptions`,
    remove: (userId: string) => `push/${userId}/subscriptions/remove`,
    test: (userId: string) => `push/${userId}/test`,
  },
  finances: {
    safeToSpend: (userId: string) => `finances/${userId}/safe-to-spend`,
    forecast: (userId: string) => `finances/${userId}/forecast`,
    plan: (userId: string) => `finances/${userId}/plan`,
    /** POST saves the plan as it stands, a new row each time. */
    planSaved: (userId: string) => `finances/${userId}/plan/saved`,
    planReview: (userId: string) => `finances/${userId}/plan/review`,
    imports: (userId: string) => `finances/${userId}/imports`,
    importPreview: (userId: string) => `finances/${userId}/imports/preview`,
    importOne: (userId: string, importId: string) => `finances/${userId}/imports/${importId}`,
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
    accountMonthValue: (userId: string, accountId: string) =>
      `finances/${userId}/accounts/${accountId}/month-value`,
    transactions: (userId: string) => `finances/${userId}/transactions`,
    transaction: (userId: string, transactionId: string) =>
      `finances/${userId}/transactions/${transactionId}`,
    transfers: (userId: string) => `finances/${userId}/transfers`,
    categories: (userId: string) => `finances/${userId}/categories`,
    category: (userId: string, categoryId: string) => `finances/${userId}/categories/${categoryId}`,
    budgetTargets: (userId: string) => `finances/${userId}/budget-targets`,
    accountCategoryLimits: (userId: string) =>
      `finances/${userId}/account-category-limits`,
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
    /** Writes any payment now owed; idempotent, so safe on every load. */
    recurringRun: (userId: string) => `finances/${userId}/recurring/run`,
    /** Committed payments still to come: projections, not rows. */
    recurringUpcoming: (userId: string) => `finances/${userId}/recurring/upcoming`,
    recurringSkip: (userId: string, ruleId: string) =>
      `finances/${userId}/recurring/${ruleId}/skip`,
  },
};