import { describe, expect, it } from "vitest";
import { degradedModelWarning, KEYWORD_ACT_COPY } from "@/lib/degraded-banner";

describe("degraded handshake banner", () => {
  it("matches the keyword rules instead of saying act is never granted", () => {
    for (const warning of [degradedModelWarning(""), degradedModelWarning("model key missing")]) {
      expect(warning).toContain(KEYWORD_ACT_COPY);
      expect(warning).toContain("clear shopping request");
      expect(warning).toContain("view-only");
      expect(warning.toLowerCase()).not.toContain("not granted automatically");
    }
    expect(degradedModelWarning("")).toContain("Model key missing");
    expect(degradedModelWarning("timeout")).toContain("Model degraded (timeout)");
  });
});
