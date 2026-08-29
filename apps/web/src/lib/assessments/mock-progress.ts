import {
  analysisProgressModeSchema,
  analysisProgressSnapshotSchema,
  progressEventSchema,
  type AnalysisProgressMode,
  type AnalysisProgressSnapshot,
  type ProgressEvent,
} from "@/lib/contracts";

type ScheduledEvent = {
  offsetMs: number;
  event: Omit<ProgressEvent, "occurredAt">;
};

const providerEvents: ScheduledEvent[] = [
  {
    offsetMs: 0,
    event: {
      sequenceNumber: 1,
      kind: "system",
      name: "system.analysis.started",
      status: "started",
      safeSummary: "Preparing the farm assessment.",
    },
  },
  {
    offsetMs: 300,
    event: {
      sequenceNumber: 2,
      kind: "provider",
      name: "provider.nasa_power.started",
      status: "started",
      safeSummary: "Collecting climate history and rainfall context.",
    },
  },
  {
    offsetMs: 550,
    event: {
      sequenceNumber: 3,
      kind: "provider",
      name: "provider.open_meteo.started",
      status: "started",
      safeSummary: "Collecting current and forecast weather evidence.",
    },
  },
  {
    offsetMs: 800,
    event: {
      sequenceNumber: 4,
      kind: "provider",
      name: "provider.ssurgo.started",
      status: "started",
      safeSummary: "Resolving mapped soil and available-water storage evidence.",
    },
  },
  {
    offsetMs: 1050,
    event: {
      sequenceNumber: 5,
      kind: "provider",
      name: "provider.fortyguard.started",
      status: "started",
      safeSummary: "Collecting local heat exposure evidence.",
    },
  },
  {
    offsetMs: 2000,
    event: {
      sequenceNumber: 6,
      kind: "provider",
      name: "provider.nasa_power.succeeded",
      status: "succeeded",
      safeSummary: "Climate history is ready from a reusable normalized record.",
      cacheState: "cache",
    },
  },
  {
    offsetMs: 2400,
    event: {
      sequenceNumber: 7,
      kind: "provider",
      name: "provider.open_meteo.succeeded",
      status: "succeeded",
      safeSummary: "Current and forecast weather evidence is ready.",
      cacheState: "live",
    },
  },
  {
    offsetMs: 2800,
    event: {
      sequenceNumber: 8,
      kind: "provider",
      name: "provider.ssurgo.succeeded",
      status: "succeeded",
      safeSummary: "Mapped soil evidence is ready from a reusable normalized record.",
      cacheState: "cache",
    },
  },
];

function completionEvents(mode: AnalysisProgressMode): ScheduledEvent[] {
  if (mode === "failure") {
    return [
      {
        offsetMs: 3300,
        event: {
          sequenceNumber: 9,
          kind: "provider",
          name: "provider.fortyguard.failed",
          status: "failed",
          safeSummary: "Heat evidence could not be collected within the allowed time.",
        },
      },
      {
        offsetMs: 3800,
        event: {
          sequenceNumber: 10,
          kind: "system",
          name: "system.analysis.failed",
          status: "failed",
          safeSummary: "The assessment stopped because required heat evidence is unavailable. Try again.",
        },
      },
    ];
  }

  const fortyGuardEvent: ScheduledEvent = {
    offsetMs: 3300,
    event: {
      sequenceNumber: 9,
      kind: "provider",
      name: "provider.fortyguard.succeeded",
      status: "succeeded",
      safeSummary:
        mode === "fallback"
          ? "Heat evidence is ready from the approved demonstration fallback."
          : "Local heat exposure evidence is ready.",
      cacheState: mode === "fallback" ? "fallback" : "live",
    },
  };

  return [
    fortyGuardEvent,
    {
      offsetMs: 3800,
      event: {
        sequenceNumber: 10,
        kind: "evidence",
        name: "evidence.bundle.started",
        status: "started",
        safeSummary: "Combining provider and farm evidence.",
      },
    },
    {
      offsetMs: 4800,
      event: {
        sequenceNumber: 11,
        kind: "evidence",
        name: "evidence.bundle.succeeded",
        status: "succeeded",
        safeSummary: "The evidence bundle is complete and internally consistent.",
      },
    },
    {
      offsetMs: 5300,
      event: {
        sequenceNumber: 12,
        kind: "scoring",
        name: "scoring.deterministic.started",
        status: "started",
        safeSummary: "Comparing all 22 catalog crops with the evidence bundle.",
      },
    },
    {
      offsetMs: 6500,
      event: {
        sequenceNumber: 13,
        kind: "scoring",
        name: "scoring.deterministic.succeeded",
        status: "succeeded",
        safeSummary: "Preliminary suitability scores are ready.",
      },
    },
    {
      offsetMs: 7000,
      event: {
        sequenceNumber: 14,
        kind: "validation",
        name: "validation.results.started",
        status: "started",
        safeSummary: "Checking ranking, evidence and presentation rules.",
      },
    },
    {
      offsetMs: 7800,
      event: {
        sequenceNumber: 15,
        kind: "validation",
        name: "validation.results.succeeded",
        status: "succeeded",
        safeSummary: "The assessment passed validation.",
      },
    },
    {
      offsetMs: 8200,
      event: {
        sequenceNumber: 16,
        kind: "system",
        name: "system.analysis.completed",
        status: "succeeded",
        safeSummary:
          mode === "fallback"
            ? "The assessment is complete with clearly labeled fallback heat evidence."
            : "The assessment is complete.",
      },
    },
  ];
}

export function parseProgressMode(value: string | null): AnalysisProgressMode {
  const parsed = analysisProgressModeSchema.safeParse(value);
  return parsed.success ? parsed.data : "success";
}

export function getMockProgressSchedule(mode: AnalysisProgressMode) {
  return [...providerEvents, ...completionEvents(mode)];
}

export function getMockProgressSnapshot(
  assessmentSessionId: string,
  startedAt: number,
  now: number,
  mode: AnalysisProgressMode,
): AnalysisProgressSnapshot {
  const elapsed = Math.max(0, now - startedAt);
  const events = getMockProgressSchedule(mode)
    .filter((scheduled) => scheduled.offsetMs <= elapsed)
    .map((scheduled) =>
      progressEventSchema.parse({
        ...scheduled.event,
        occurredAt: new Date(startedAt + scheduled.offsetMs).toISOString(),
      }),
    );
  const finalEvent = events.at(-1);
  const failed = finalEvent?.name === "system.analysis.failed";
  const completed = finalEvent?.name === "system.analysis.completed";

  return analysisProgressSnapshotSchema.parse({
    assessmentSessionId,
    status: failed ? "failed" : completed ? "completed" : "running",
    outcome: failed ? "failure" : completed ? mode : null,
    terminal: failed || completed,
    events,
  });
}

export function normalizeProgressStart(value: string | null, now = Date.now()) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed > now + 5000 || parsed < now - 300000) {
    return now;
  }
  return Math.trunc(parsed);
}
