import { describe, expect, it } from "vitest";
import { buildCsp, buildHeaders, originOf } from "./securityHeaders";

/**
 * These guard the one file in the project whose mistakes are invisible from
 * the server. A wrong `connect-src` makes the browser refuse every API call
 * *before sending it*, so the API's logs stay clean while the app looks down --
 * the same shape as the CORS bug Phase 0 found, and the reason this file is
 * generated from `VITE_API_BASE_URL` rather than checked in.
 */
describe("originOf", () => {
  it("reduces an absolute API base to its origin", () => {
    expect(originOf("https://account-api-210502804146.us-west1.run.app/api"))
      .toBe("https://account-api-210502804146.us-west1.run.app");
    expect(originOf("http://localhost:8001/api")).toBe("http://localhost:8001");
  });

  /**
   * A root-relative base is already same-origin, which `'self'` covers. It
   * returns "" rather than null because it is a real configuration -- it is
   * what putting the API behind the same hostname looks like -- and must not
   * be reported as a mistake.
   */
  it("treats a root-relative base as same-origin, not as an error", () => {
    expect(originOf("/api")).toBe("");
  });

  it("returns null for something that is neither", () => {
    expect(originOf("localhost:8001/api")).toBeNull();
    expect(originOf("not a url")).toBeNull();
    expect(originOf("")).toBeNull();
  });
});

describe("buildCsp", () => {
  it("names the API origin so the browser will allow the call", () => {
    const csp = buildCsp("https://api.example.com");
    const connect = csp.split("; ").find((d) => d.startsWith("connect-src"));

    expect(connect).toContain("https://api.example.com");
    expect(connect).toContain("'self'");
  });

  it("omits an empty origin rather than leaving a double space", () => {
    const connect = buildCsp("").split("; ").find((d) => d.startsWith("connect-src"));

    expect(connect).toBe("connect-src 'self' https://accounts.google.com/gsi/");
  });

  /**
   * The trap worth a test of its own. `upgrade-insecure-requests` applies to
   * the whole document, so adding it to a build that talks to
   * http://localhost rewrites those calls to https and breaks every one of
   * them -- during local development, where the policy is least likely to be
   * read.
   */
  it("upgrades insecure requests only when the API is already https", () => {
    expect(buildCsp("https://api.example.com")).toContain("upgrade-insecure-requests");
    expect(buildCsp("http://localhost:8001")).not.toContain("upgrade-insecure-requests");
    expect(buildCsp("")).not.toContain("upgrade-insecure-requests");
  });

  it("keeps script-src strict while style-src carries the inline concession", () => {
    const csp = buildCsp("https://api.example.com");
    const script = csp.split("; ").find((d) => d.startsWith("script-src"));
    const style = csp.split("; ").find((d) => d.startsWith("style-src"));

    // The directive that actually stops XSS. If this ever gains
    // 'unsafe-inline' it should be a decision, not a diff nobody noticed.
    expect(script).not.toContain("unsafe-inline");
    expect(script).not.toContain("unsafe-eval");
    expect(style).toContain("'unsafe-inline'");
  });

  it("refuses to be framed and allows no plugins", () => {
    const csp = buildCsp("https://api.example.com");

    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("default-src 'self'");
  });
});

describe("buildHeaders", () => {
  it("emits all six headers Pages is meant to apply", () => {
    const file = buildHeaders("https://api.example.com/api");

    for (const header of [
      "Strict-Transport-Security:",
      "X-Content-Type-Options:",
      "Referrer-Policy:",
      "X-Frame-Options:",
      "Permissions-Policy:",
      "Content-Security-Policy:",
    ]) {
      expect(file).toContain(header);
    }
  });

  /**
   * HSTS without `preload` is deliberate: submitting to the preload list is
   * close to irreversible and commits every future subdomain.
   */
  it("does not claim preload", () => {
    expect(buildHeaders("https://api.example.com/api")).not.toContain("preload");
  });

  it("applies the rules to every path", () => {
    expect(buildHeaders("https://api.example.com/api")).toContain("/*");
  });
});
