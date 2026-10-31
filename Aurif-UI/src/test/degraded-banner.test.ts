import { describe, expect, it } from "vitest";
import { KEYWORD_ACT_COPY, modelStatusBanner, type ModelHealth } from "@/lib/degraded-banner";

const textUp = {
  degraded: false,
  powered_by: "Meta Muse Spark 1.3",
  provider: "meta",
  model: "muse-spark-1.3",
};

const visionModal = {
  powered_by: "DeepSeek V4.1 Flash (Modal)",
  provider: "modal",
  label: "DeepSeek V4.1 Flash (Modal)",
  model: "deepseek-ai/DeepSeek-V4.1-Flash",
};

describe("per-model status banner", () => {
  it("names a vision outage and says text is still scoring", () => {
    const health: ModelHealth = {
      ok: true,
      degraded: true,
      partial: true,
      text: textUp,
      vision: {
        ...visionModal,
        degraded: true,
        last_error:
          "vision model deepseek-ai/DeepSeek-V4.1-Flash: 403 forbidden, check Modal model access or slug",
      },
    };
    const warning = modelStatusBanner(health);
    expect(warning).toBe(
      "CAPTCHA vision (DeepSeek V4.1 Flash via Modal) unavailable: 403. Text features on Meta Muse Spark 1.3 are working.",
    );
    expect(warning).not.toContain("keyword rules");
    expect(warning).not.toContain(KEYWORD_ACT_COPY);
  });

  it("names a text outage, keeps the keyword-rule copy, and says vision is working", () => {
    const health: ModelHealth = {
      ok: false,
      degraded: true,
      partial: false,
      text: {
        ...textUp,
        degraded: true,
        last_error: "model key missing or provider misconfigured",
      },
      vision: { ...visionModal, degraded: false },
    };
    const warning = modelStatusBanner(health) || "";
    expect(warning).toContain("Text features (Meta Muse Spark 1.3) unavailable");
    expect(warning).toContain("model key missing");
    expect(warning).toContain("Handshake uses keyword rules");
    expect(warning).toContain(KEYWORD_ACT_COPY);
    expect(warning).toContain("CAPTCHA vision (DeepSeek V4.1 Flash via Modal) is working.");
    expect(warning.toLowerCase()).not.toContain("not granted automatically");
  });

  it("stays quiet when both models are up", () => {
    expect(modelStatusBanner({ text: textUp, vision: { ...visionModal, degraded: false } })).toBeNull();
    expect(modelStatusBanner(null)).toBeNull();
  });
});
