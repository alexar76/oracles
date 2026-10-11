import { describe, expect, it } from "vitest";
import { formatMetric, gridPosition, phaseColor } from "./types";

describe("formatMetric", () => {
  it("formats with default digits", () => {
    expect(formatMetric(0.7312)).toBe("0.731");
  });
});

describe("phaseColor", () => {
  it("returns hsl string", () => {
    expect(phaseColor(0, 0.5)).toMatch(/^hsl\(/);
  });
});

describe("gridPosition", () => {
  it("places 32 oscillators on 8x4 grid", () => {
    const pos = gridPosition(0);
    expect(pos).toHaveLength(3);
    const pos31 = gridPosition(31);
    expect(pos31[0]).toBeGreaterThan(pos[0]);
  });
});
