import { get } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { CalendarEvent } from "./types";

export async function fetchEvents(userId: string): Promise<CalendarEvent[]> {
  return get<CalendarEvent[]>(endpoints.calendar.events(userId));
}
