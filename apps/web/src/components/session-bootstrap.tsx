"use client";

import { CircleAlert, LoaderCircle, LockKeyhole } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { sessionBootstrapResponseSchema } from "@/lib/contracts";

type SessionState = "starting" | "ready" | "error";

export function SessionBootstrap() {
  const [state, setState] = useState<SessionState>("starting");

  const requestSession = useCallback(async (): Promise<SessionState> => {
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { accept: "application/json" },
        cache: "no-store",
      });
      const payload = sessionBootstrapResponseSchema.parse(await response.json());
      return payload.ok ? "ready" : "error";
    } catch {
      return "error";
    }
  }, []);

  useEffect(() => {
    let active = true;

    void requestSession().then((nextState) => {
      if (active) {
        setState(nextState);
      }
    });

    return () => {
      active = false;
    };
  }, [requestSession]);

  const retry = useCallback(async () => {
    setState("starting");
    setState(await requestSession());
  }, [requestSession]);

  if (state === "starting") {
    return (
      <div className="session-status" role="status" aria-live="polite">
        <LoaderCircle aria-hidden="true" className="spin" size={16} />
        Starting private session
      </div>
    );
  }

  if (state === "ready") {
    return (
      <div className="session-status session-status-ready" role="status">
        <LockKeyhole aria-hidden="true" size={16} />
        Private session ready
      </div>
    );
  }

  return (
    <button className="session-status session-status-error" type="button" onClick={retry}>
      <CircleAlert aria-hidden="true" size={16} />
      Retry session
    </button>
  );
}
