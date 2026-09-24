import { describe, expect, it } from "vitest";
import { preconnectTag } from "./apiPreconnect";

/**
 * A wrong preconnect hint fails the way a wrong `connect-src` does -- without
 * saying anything. The browser ignores a hint it cannot use, so the only
 * symptom is that the app is no faster than before, which is indistinguishable
 * from the hint never having been added.
 */
describe("preconnectTag", () => {
  it("names the API origin, and only the origin", () => {
    const tag = preconnectTag("https://account-api-210502804146.us-west1.run.app/api");

    expect(tag).not.toBeNull();
    expect(tag!.attrs!.href).toBe("https://account-api-210502804146.us-west1.run.app");
    expect(tag!.attrs!.rel).toBe("preconnect");
  });

  /**
   * The attribute that makes the hint worth having. Every API call carries an
   * `Authorization` header, so it is a CORS request, and a connection warmed
   * anonymously cannot be reused for a credentialled one -- the browser opens a
   * second. Without this the hint costs a socket and saves nothing while
   * reading as correct in the markup, which is why it gets its own assertion
   * rather than being left to the one above.
   */
  it("warms a credentialled connection, not an anonymous one", () => {
    const tag = preconnectTag("https://api.example.com/api");

    expect(tag!.attrs).toHaveProperty("crossorigin");
  });

  /**
   * Nothing to preconnect to when the API is already same-origin: the browser
   * is connected to it by definition, having just loaded the page from it.
   */
  it("emits nothing for a root-relative API base", () => {
    expect(preconnectTag("/api")).toBeNull();
  });

  /**
   * The mistake `originOf` exists to catch. `new URL("localhost:8001/api")`
   * succeeds -- "localhost:" parses as a scheme -- and its origin serialises to
   * the string "null", so a hint built without that check would emit
   * `href="null"`. Reusing `originOf` is what keeps this honest, and this test
   * is what says so.
   */
  it("emits nothing for a base that is neither, rather than a broken hint", () => {
    expect(preconnectTag("localhost:8001/api")).toBeNull();
    expect(preconnectTag("not a url")).toBeNull();
    expect(preconnectTag("")).toBeNull();
  });
});
