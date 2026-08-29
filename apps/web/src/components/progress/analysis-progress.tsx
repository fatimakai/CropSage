"use client";

import {
  Calculator,
  Check,
  CircleAlert,
  Clock3,
  CloudSun,
  Database,
  Flame,
  Layers3,
  LoaderCircle,
  PackageCheck,
  RefreshCw,
  Satellite,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  analysisProgressSnapshotSchema,
  progressEventSchema,
  type AnalysisProgressMode,
  type ProgressEvent,
} from "@/lib/contracts";

type AnalysisProgressProps = {
  assessmentSessionId: string;
  mode: AnalysisProgressMode;
};

type DeliveryState = "connecting" | "streaming" | "polling" | "complete" | "failed";
type StageStatus = "pending" | "running" | "succeeded" | "failed";

const providers = [
  {
    code: "nasa_power",
    name: "NASA POWER",
    description: "Climate and rainfall history",
    icon: CloudSun,
  },
  {
    code: "open_meteo",
    name: "Open-Meteo",
    description: "Current and forecast weather",
    icon: Satellite,
  },
  {
    code: "ssurgo",
    name: "USDA SSURGO",
    description: "Mapped soil and water storage",
    icon: Layers3,
  },
  {
    code: "fortyguard",
    name: "FortyGuard",
    description: "Local heat exposure",
    icon: Flame,
  },
] as const;

const pipelineStages = [
  { prefix: "evidence.bundle", name: "Evidence bundle", icon: PackageCheck },
  { prefix: "scoring.deterministic", name: "Deterministic scoring", icon: Calculator },
  { prefix: "validation.results", name: "Result validation", icon: ShieldCheck },
] as const;

function latestEvent(events: ProgressEvent[], prefix: string) {
  return events.findLast((event) => event.name.startsWith(prefix));
}

function stageStatus(event: ProgressEvent | undefined): StageStatus {
  if (!event) return "pending";
  if (event.status === "started") return "running";
  if (event.status === "failed") return "failed";
  return "succeeded";
}

function StatusIcon({ status }: { status: StageStatus }) {
  if (status === "running") return <LoaderCircle className="spin" size={18} aria-hidden="true" />;
  if (status === "succeeded") return <Check size={18} aria-hidden="true" />;
  if (status === "failed") return <CircleAlert size={18} aria-hidden="true" />;
  return <Clock3 size={17} aria-hidden="true" />;
}

function addProgressEvent(current: ProgressEvent[], next: ProgressEvent) {
  if (current.some((event) => event.sequenceNumber === next.sequenceNumber)) return current;
  return [...current, next].sort((left, right) => left.sequenceNumber - right.sequenceNumber);
}

export function AnalysisProgress({ assessmentSessionId, mode }: AnalysisProgressProps) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [delivery, setDelivery] = useState<DeliveryState>("connecting");
  const [outcome, setOutcome] = useState<AnalysisProgressMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState(() => Date.now());

  useEffect(() => {
    let disposed = false;
    let finished = false;
    let pollingTimer: ReturnType<typeof setTimeout> | null = null;
    let pollingFailures = 0;
    const query = new URLSearchParams({ startedAt: String(startedAt), mode });
    const stream = new EventSource(
      `/api/assessments/${assessmentSessionId}/events?${query.toString()}`,
    );

    const deadline = setTimeout(() => {
      if (disposed || finished) return;
      finished = true;
      stream.close();
      if (pollingTimer) clearTimeout(pollingTimer);
      setDelivery("failed");
      setOutcome("failure");
      setError("The analysis did not finish within the allowed time. Try again.");
    }, 30000);

    async function poll() {
      if (disposed || finished) return;

      try {
        const response = await fetch(
          `/api/assessments/${assessmentSessionId}/progress?${query.toString()}`,
          { cache: "no-store", headers: { accept: "application/json" } },
        );

        if (response.status === 401 || response.status === 404) {
          finished = true;
          clearTimeout(deadline);
          setDelivery("failed");
          setOutcome("failure");
          setError("This assessment is unavailable for the current session.");
          return;
        }

        if (!response.ok) {
          throw new Error(`Progress request returned ${response.status}.`);
        }

        const snapshot = analysisProgressSnapshotSchema.parse(await response.json());
        pollingFailures = 0;
        setEvents(snapshot.events);

        if (snapshot.terminal) {
          finished = true;
          clearTimeout(deadline);
          setOutcome(snapshot.outcome);
          setDelivery(snapshot.status === "failed" ? "failed" : "complete");
          if (snapshot.status === "failed") {
            setError(snapshot.events.at(-1)?.safeSummary ?? "The analysis could not be completed.");
          }
          return;
        }

        pollingTimer = setTimeout(poll, 1500);
      } catch {
        pollingFailures += 1;
        if (pollingFailures >= 3) {
          finished = true;
          clearTimeout(deadline);
          setDelivery("failed");
          setOutcome("failure");
          setError("Progress updates are unavailable. Check the connection and try again.");
          return;
        }
        pollingTimer = setTimeout(poll, 1500);
      }
    }

    stream.onopen = () => {
      if (!disposed) setDelivery("streaming");
    };

    stream.addEventListener("progress", (message) => {
      if (disposed || finished) return;

      try {
        const event = progressEventSchema.parse(JSON.parse((message as MessageEvent).data));
        setEvents((current) => addProgressEvent(current, event));

        if (event.name === "system.analysis.completed" || event.name === "system.analysis.failed") {
          finished = true;
          clearTimeout(deadline);
          stream.close();
          const failed = event.name === "system.analysis.failed";
          setOutcome(failed ? "failure" : mode);
          setDelivery(failed ? "failed" : "complete");
          if (failed) setError(event.safeSummary);
        }
      } catch {
        finished = true;
        clearTimeout(deadline);
        stream.close();
        setDelivery("failed");
        setOutcome("failure");
        setError("A progress update was invalid. The analysis has been stopped.");
      }
    });

    stream.onerror = () => {
      if (disposed || finished) return;
      stream.close();
      setDelivery("polling");
      void poll();
    };

    return () => {
      disposed = true;
      stream.close();
      clearTimeout(deadline);
      if (pollingTimer) clearTimeout(pollingTimer);
    };
  }, [assessmentSessionId, mode, startedAt]);

  const stageStates = useMemo(() => {
    const providerStates = providers.map((provider) =>
      stageStatus(latestEvent(events, `provider.${provider.code}`)),
    );
    const pipelineStates = pipelineStages.map((stage) =>
      stageStatus(latestEvent(events, stage.prefix)),
    );
    return [...providerStates, ...pipelineStates];
  }, [events]);

  const progress = Math.round(
    (stageStates.reduce((total, status) => {
      if (status === "succeeded" || status === "failed") return total + 1;
      if (status === "running") return total + 0.5;
      return total;
    }, 0) /
      stageStates.length) *
      100,
  );

  function retry() {
    setEvents([]);
    setDelivery("connecting");
    setOutcome(null);
    setError(null);
    setStartedAt(Date.now());
  }

  const latestSummary = events.at(-1)?.safeSummary ?? "Connecting to the analysis service.";

  return (
    <main className="workspace progress-workspace">
      <header className="page-heading progress-heading">
        <div>
          <p className="eyebrow">Preliminary suitability</p>
          <h1>Analyzing farm evidence</h1>
          <p>{latestSummary}</p>
        </div>
        <div className="progress-heading-badges">
          <span className="scope-label">Prepared evidence run</span>
          <span className={`delivery-badge delivery-${delivery}`}>
            {delivery === "streaming" ? "Live updates" : null}
            {delivery === "polling" ? "Polling fallback" : null}
            {delivery === "connecting" ? "Connecting" : null}
            {delivery === "complete" ? "Complete" : null}
            {delivery === "failed" ? "Stopped" : null}
          </span>
        </div>
      </header>

      <section className="analysis-overview" aria-labelledby="analysis-status-heading">
        <div className="analysis-status-line">
          <div>
            <h2 id="analysis-status-heading">Assessment progress</h2>
            <span>{progress}%</span>
          </div>
          <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label="Assessment progress">
            <span style={{ width: `${progress}%` }} />
          </div>
        </div>
        <p>Assessment {assessmentSessionId.slice(0, 8).toUpperCase()}</p>
      </section>

      <section aria-labelledby="providers-heading">
        <div className="section-title-row">
          <div><h2 id="providers-heading">Location evidence</h2><p>Provider status and source mode for this farm point.</p></div>
          <Database size={19} aria-hidden="true" />
        </div>
        <div className="provider-grid">
          {providers.map((provider) => {
            const event = latestEvent(events, `provider.${provider.code}`);
            const status = stageStatus(event);
            const Icon = provider.icon;
            return (
              <article className={`provider-card provider-${status}`} key={provider.code}>
                <div className="provider-card-heading">
                  <span className="provider-icon" aria-hidden="true"><Icon size={19} /></span>
                  <span className={`stage-status stage-${status}`}><StatusIcon status={status} />{status === "pending" ? "Waiting" : status === "running" ? "Collecting" : status === "succeeded" ? "Ready" : "Unavailable"}</span>
                </div>
                <h3>{provider.name}</h3>
                <p>{event?.safeSummary ?? provider.description}</p>
                {event?.cacheState ? <span className={`source-mode source-${event.cacheState}`}>{event.cacheState === "live" ? "Live source" : event.cacheState === "cache" ? "Reusable record" : "Approved fallback"}</span> : null}
              </article>
            );
          })}
        </div>
      </section>

      <section className="pipeline-section" aria-labelledby="pipeline-heading">
        <div className="section-title-row"><div><h2 id="pipeline-heading">Decision pipeline</h2><p>Evidence is assembled before scoring and validation.</p></div></div>
        <ol className="pipeline-list">
          {pipelineStages.map((stage) => {
            const event = latestEvent(events, stage.prefix);
            const status = stageStatus(event);
            const Icon = stage.icon;
            return <li key={stage.prefix} className={`pipeline-stage pipeline-${status}`}><span className="pipeline-icon"><Icon size={18} aria-hidden="true" /></span><div><strong>{stage.name}</strong><span>{event?.safeSummary ?? "Waiting for provider evidence."}</span></div><span className={`stage-status stage-${status}`}><StatusIcon status={status} />{status === "pending" ? "Waiting" : status === "running" ? "Running" : status === "succeeded" ? "Complete" : "Failed"}</span></li>;
          })}
        </ol>
      </section>

      {outcome === "success" || outcome === "fallback" ? (
        <section className={`terminal-message terminal-${outcome}`} aria-live="polite">
          <Check size={21} aria-hidden="true" />
          <div><h2>Analysis complete</h2><p>{outcome === "fallback" ? "The assessment completed with approved fallback heat evidence. Source labels remain attached to the result." : "Evidence, scoring and validation completed successfully."}</p></div>
        </section>
      ) : null}

      {error ? (
        <section className="terminal-message terminal-failure" role="alert">
          <CircleAlert size={21} aria-hidden="true" />
          <div><h2>Analysis stopped</h2><p>{error}</p></div>
          <button className="button button-secondary" type="button" onClick={retry}><RefreshCw size={17} aria-hidden="true" />Try again</button>
        </section>
      ) : null}

      <details className="activity-log">
        <summary>Activity details <span>{events.length} updates</span></summary>
        <ol>
          {events.map((event) => (
            <li key={event.sequenceNumber}>
              <span className={`activity-dot activity-${event.status}`} aria-hidden="true" />
              <div><strong>{event.safeSummary}</strong><span>{new Date(event.occurredAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}{event.cacheState ? ` · ${event.cacheState}` : ""}</span></div>
            </li>
          ))}
        </ol>
      </details>
    </main>
  );
}
