import { del, get, post, patch, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { TermBlackout, TermBlackoutCreate, CrunchStrip, FreeBlock, WeekLoad,
  CalendarEvent,
  ClassScheduleCreate,
  EventCreate,
  EventOccurrence,
  EventUpdate,
} from "./types";

/** Every occurrence of every event from `start` to `end` inclusive, expanded by the server. */
export async function fetchAgenda(userId: string, start: string, end: string) {
  const base = endpoints.calendar.agenda(userId);
  return get<EventOccurrence[]>(`${base}?start=${start}&end=${end}`);
}

/** The stored events, one row per series, optionally for one course. */
export async function fetchEvents(userId: string, courseId?: string) {
  const base = endpoints.calendar.events(userId);
  return get<CalendarEvent[]>(courseId ? `${base}?course_id=${courseId}` : base);
}

/** Create an event. */
export async function createEvent(userId: string, payload: EventCreate) {
  return post<CalendarEvent>(endpoints.calendar.events(userId), payload);
}

/** Patch an event. */
export async function updateEvent(userId: string, eventId: string, payload: EventUpdate) {
  return patch<CalendarEvent>(endpoints.calendar.event(userId, eventId), payload);
}

/** Delete a whole series; `skipOccurrence` cancels a single date instead. */
export async function deleteEvent(userId: string, eventId: string) {
  return del<CalendarEvent>(endpoints.calendar.event(userId, eventId));
}

/** Cancel one date of a series, leaving the rest running; same URL as a delete plus `on_date`. */
export async function skipOccurrence(userId: string, eventId: string, onDate: string) {
  return del<CalendarEvent>(`${endpoints.calendar.event(userId, eventId)}?on_date=${onDate}`);
}

/** Bring back a cancelled date of a series. */
export async function restoreOccurrence(userId: string, eventId: string, onDate: string) {
  return post<CalendarEvent>(
    `${endpoints.calendar.restoreOccurrence(userId, eventId)}?on_date=${onDate}`,
    {}
  );
}

/** The timetable events of one course. */
export async function fetchClassSchedule(userId: string, courseId: string) {
  return get<CalendarEvent[]>(endpoints.calendar.classSchedule(userId, courseId));
}

/** Replace a course's whole timetable, so sending it twice leaves one copy. */
export async function setClassSchedule(
  userId: string,
  courseId: string,
  payload: ClassScheduleCreate
) {
  return put<CalendarEvent[]>(endpoints.calendar.classSchedule(userId, courseId), payload);
}

/** The start and end query string for a date window. */
function window(start: string, end: string) {
  return `?start=${start}&end=${end}`;
}

/** Gaps between commitments inside the study hours, longest first. */
export async function fetchFreeBlocks(userId: string, start: string, end: string) {
  return get<FreeBlock[]>(endpoints.calendar.freeBlocks(userId) + window(start, end));
}

/** Booked and estimated minutes for a window. */
export async function fetchWeekLoad(userId: string, start: string, end: string) {
  return get<WeekLoad>(endpoints.calendar.weekLoad(userId) + window(start, end));
}

/** Weekly crunch weights for a window. */
export async function fetchCrunch(userId: string, start: string, end: string) {
  return get<CrunchStrip>(endpoints.calendar.crunch(userId) + window(start, end));
}

/** The student's term blackouts. */
export async function fetchBlackouts(userId: string) {
  return get<TermBlackout[]>(endpoints.calendar.blackouts(userId));
}

/** Add a term blackout. */
export async function createBlackout(userId: string, data: TermBlackoutCreate) {
  return post<TermBlackout>(endpoints.calendar.blackouts(userId), data);
}

/** Delete a term blackout. */
export async function deleteBlackout(userId: string, id: string) {
  return del(endpoints.calendar.blackout(userId, id));
}
