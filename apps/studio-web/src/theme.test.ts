import { afterEach, describe, expect, it } from "vitest";
import { readTheme, writeTheme } from "./theme";

afterEach(() => { document.cookie = "studio_theme=; path=/; max-age=0"; });

describe("saved theme preference", () => {
  it("restores the explicit dark and light choices from the cookie", () => {
    writeTheme("dark");
    expect(readTheme()).toBe("dark");
    writeTheme("light");
    expect(readTheme()).toBe("light");
  });
  it("ignores missing or invalid preferences", () => {
    expect(readTheme()).toBeNull();
    document.cookie = "studio_theme=dark-extra; path=/";
    expect(readTheme()).toBeNull();
  });
});
