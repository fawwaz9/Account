// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import Icon from "./Icon";

/**
 * Every icon is gold (the owner's ask). The PNGs are drawn black, so the colour
 * comes from the stylesheet filling them as a mask -- and if that rule went,
 * every icon would quietly turn black on a navy page.
 */

afterEach(cleanup);

describe("an icon", () => {
  it("draws its image as the shape, through --icon", () => {
    const { container } = render(<Icon src="/x/home.png" />);
    const icon = container.querySelector<HTMLElement>(".appIcon")!;
    expect(icon.style.getPropertyValue("--icon")).toBe('url("/x/home.png")');
  });

  it("is hidden from assistive technology, since what holds it carries the name", () => {
    const { container } = render(<Icon src="/x/home.png" className="extra" />);
    const icon = container.querySelector(".appIcon")!;
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.classList.contains("extra")).toBe(true);
  });

  it("is painted gold, with the image only as a mask", () => {
    // jsdom applies no stylesheet, so this reads the rule itself.
    const css = readFileSync(join(__dirname, "../../styles/globals.css"), "utf8");
    const rule = css.match(/\.appIcon\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/background-color:\s*var\(--gold\)/);
    expect(rule).toMatch(/(^|\s)mask:\s*var\(--icon\)/);
    expect(rule).toMatch(/-webkit-mask:\s*var\(--icon\)/);
  });
});
