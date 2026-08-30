import { describe, expect, it } from "vitest";

import { summarizeFarmBoundary } from "./boundary";

describe("summarizeFarmBoundary", () => {
  it("calculates acreage and an interior representative point", () => {
    const summary = summarizeFarmBoundary({
      type: "Polygon",
      coordinates: [
        [
          [-101.77, 34.17],
          [-101.76, 34.17],
          [-101.76, 34.18],
          [-101.77, 34.18],
          [-101.77, 34.17],
        ],
      ],
    });

    expect(summary).not.toBeNull();
    expect(summary?.areaAcres).toBeGreaterThan(200);
    expect(summary?.areaAcres).toBeLessThan(300);
    expect(summary?.representativePoint.latitude).toBeGreaterThanOrEqual(34.17);
    expect(summary?.representativePoint.latitude).toBeLessThanOrEqual(34.18);
    expect(summary?.representativePoint.longitude).toBeGreaterThanOrEqual(-101.77);
    expect(summary?.representativePoint.longitude).toBeLessThanOrEqual(-101.76);
  });

  it("rejects an open polygon ring", () => {
    expect(
      summarizeFarmBoundary({
        type: "Polygon",
        coordinates: [
          [
            [-101.77, 34.17],
            [-101.76, 34.17],
            [-101.76, 34.18],
            [-101.77, 34.18],
          ],
        ],
      }),
    ).toBeNull();
  });
});
