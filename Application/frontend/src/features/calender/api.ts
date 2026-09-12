import { del, get, post, patch, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { CrunchStrip, FreeBlock, WeekLoad,
  CalendarEvent,
  ClassScheduleCreate,
  EventCreate,
  EventOccurrence,
  EventUpdate,
} from "./types";

/**
 * Every date every event falls on between `start` and `end`, inclusive.
 *
 * Repeats are expanded server-side. Asking the API for a window rather than
 * fetching the rules and expanding them here keeps one implementation of what
 * "every other Tuesday" means -- the same reason budget figures are computed
 * server-side.
 */
export async function fetchAgenda(userId: string, start: string, end: string) {
  const base = endpoints.calendar.agenda(userId);
  return get<EventOccurrence[]>(`${base}?start=${start}&end=${end}`);
}

/** The stored events themselves: one row per series, not per occurrence. */
export async function fetchEvents(userId: string, courseId?: string) {
  const base = endpoints.calendar.events(userId);
  return get<CalendarEvent[]>(courseId ? `${base}?course_id=${courseId}` : base);
}

export async function createEvent(userId: string, payload: EventCreate) {
  return post<CalendarEvent>(endpoints.calendar.events(userId), payload);
}

export async function updateEvent(userId: string, eventId: string, payload: EventUpdate) {
  return patch<CalendarEvent>(endpoints.calendar.event(userId, eventId), payload);
}

/** Removes the whole series. To drop a single date, use `skipOccurrence`. */
export async function deleteEvent(userId: string, eventId: string) {
  return del<CalendarEvent>(endpoints.calendar.event(userId, eventId));
}

/**
 * Cancel one date of a repeat, leaving the rest of it running.
 *
 * "No lecture next Monday" and "no lectures ever again" are different
 * instructions, and deleting the event only expresses the second.
 */
export async function skipOccurrence(userId: string, eventId: string, onDate: string) {
  return del<CalendarEvent>(`${endpoints.calendar.event(userId, eventId)}?on_date=${onDate}`);
}

export async function restoreOccurrence(userId: string, eventId: string, onDate: string) {
  return post<CalendarEvent>(
    `${endpoints.calendar.restoreOccurrence(userId, eventId)}?on_date=${onDate}`,
    {}
  );
}

export async function fetchClassSchedule(userId: string, courseId: string) {
  return get<CalendarEvent[]>(endpoints.calendar.classSchedule(userId, courseId));
}

/** Replaces the course's whole timetable, so submitting twice leaves one copy. */
export async function setClassSchedule(
  userId: string,
  courseId: string,
  payload: ClassScheduleCreate
) {
  return put<CalendarEvent[]>(endpoints.calendar.classSchedule(userId, courseId), payload);
}

function window(start: string, end: string) {
  return `?start=${start}&end=${end}`;
}

/** The gaps between commitments, longest first, inside your study hours. */
export async function fetchFreeBlocks(userId: string, start: string, end: string) {
  return get<FreeBlock[]>(endpoints.calendar.freeBlocks(userId) + window(start, end));
}

export async function fetchWeekLoad(userId: string, start: string, end: string) {
  return get<WeekLoad>(endpoints.calendar.weekLoad(userId) + window(start, end));
}

export async function fetchCrunch(userId: string, start: string, end: string) {
  return get<CrunchStrip>(endpoints.calendar.crunch(userId) + window(start, end));
}
