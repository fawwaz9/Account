// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchAssistantToken: vi.fn(), makeAssistantToken: vi.fn(), revokeAssistantToken: vi.fn() };
vi.mock("./assistantApi", () => ({
  fetchAssistantToken: (...a: unknown[]) => api.fetchAssistantToken(...a),
  makeAssistantToken: (...a: unknown[]) => api.makeAssistantToken(...a),
  revokeAssistantToken: (...a: unknown[]) => api.revokeAssistantToken(...a),
}));

import AssistantSetting from "./AssistantSetting";

/** Phase 4 item 7: off until made; the token shown once; revocable at once. */

const OFF = { enabled: false, prefix: null, created_at: null, last_used_at: null };

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.fetchAssistantToken.mockResolvedValue(OFF);
  api.makeAssistantToken.mockResolvedValue({ token: "acct_secret-token-value", prefix: "acct_secret-", created_at: "2026-11-01T00:00:00" });
  api.revokeAssistantToken.mockResolvedValue(undefined);
});
afterEach(cleanup);

describe("AssistantSetting", () => {
  it("is off until you ask for it", async () => {
    render(<AssistantSetting userId="u1" />);

    expect(await screen.findByRole("button", { name: "Let my assistant read my briefing" })).toBeTruthy();
    expect(screen.queryByText(/acct_/)).toBeNull();
  });

  it("shows the token once, with where to point an assistant", async () => {
    render(<AssistantSetting userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Let my assistant read my briefing" }));

    expect(await screen.findByText("acct_secret-token-value")).toBeTruthy();
    expect(screen.getByText(/won't be shown again/)).toBeTruthy();
    expect(screen.getByText(/assistant\/mcp/)).toBeTruthy();
    expect(screen.getByText("On")).toBeTruthy();
  });

  it("never shows a token it was only told about", async () => {
    api.fetchAssistantToken.mockResolvedValue({ enabled: true, prefix: "acct_abc1234", created_at: "2026-11-01T00:00:00",
      last_used_at: null });
    render(<AssistantSetting userId="u1" />);

    expect(await screen.findByText(/acct_abc1234…/)).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("turns it off, and the token goes with it", async () => {
    render(<AssistantSetting userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Let my assistant read my briefing" }));
    await screen.findByText("acct_secret-token-value");

    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));

    await waitFor(() => expect(api.revokeAssistantToken).toHaveBeenCalledWith("u1"));
    expect(await screen.findByText(/The token no longer works/)).toBeTruthy();
    expect(screen.queryByText("acct_secret-token-value")).toBeNull();
  });
});
