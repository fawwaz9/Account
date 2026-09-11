import { get, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { OmniboxPreview, OmniboxResult } from "./types";

/** What a line would be filed as. A read: it writes nothing. */
export async function previewLine(userId: string, text: string) {
  const base = endpoints.omnibox.base(userId);
  return get<OmniboxPreview>(`${base}?text=${encodeURIComponent(text)}`);
}

/** File the line into whichever module it belongs to. */
export async function fileLine(userId: string, text: string) {
  return post<OmniboxResult>(endpoints.omnibox.base(userId), { text });
}
