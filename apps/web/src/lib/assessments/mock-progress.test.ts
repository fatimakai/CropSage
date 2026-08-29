import { describe, expect, it } from "vitest";

import {
  getMockProgressSnapshot,
  normalizeProgressStart,
} from "@/lib/assessments/mock-progress";

const assessmentId = "76000000-0000-4000-8000-000000000003";
const startedAt = Date.parse("2026-08-29T12:00:00.000Z");

describe("mock analysis progress", () => {
  it("terminates a successful run after validated scoring", () => {
    const snapshot = getMockProgressSnapshot(
      assessmentId,
      startedAt,
      startedAt + 9000,
      "success",
    );

    expect(snapshot.status).toBe("completed");
    expect(snapshot.outcome).toBe("success");
    expect(snapshot.events).toHaveLength(16);
    expect(snapshot.events.at(-1)?.name).toBe("system.analysis.completed");
  });

  it("labels an approved provider fallback without failing the assessment", () => {
    const snapshot = getMockProgressSnapshot(
      assessmentId,
      startedAt,
      startedAt + 9000,
      "fallback",
    );

    expect(snapshot.status).toBe("completed");
    expect(snapshot.outcome).toBe("fallback");
    expect(snapshot.events.some((event) => event.cacheState === "fallback")).toBe(true);
  });

  it("stops after an actionable required-provider failure", () => {
    const snapshot = getMockProgressSnapshot(
      assessmentId,
      startedAt,
      startedAt + 9000,
      "failure",
    );

    expect(snapshot.status).toBe("failed");
    expect(snapshot.outcome).toBe("failure");
    expect(snapshot.events.at(-1)?.safeSummary).toContain("Try again");
  });

  it("normalizes invalid or stale client start times", () => {
    const now = startedAt;
    expect(normalizeProgressStart("not-a-number", now)).toBe(now);
    expect(normalizeProgressStart(String(now - 300001), now)).toBe(now);
    expect(normalizeProgressStart(String(now - 1000), now)).toBe(now - 1000);
  });
});
