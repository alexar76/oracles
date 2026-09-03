import { useEffect, useRef, useState } from "react";
import type { AgentInvoke, DreamPreview, Telemetry, Witness } from "../lib/types";

const WS_URL =
  (location.protocol === "https:" ? "wss://" : "ws://") +
  location.host +
  "/ws";

export function usePlatonSocket() {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [connected, setConnected] = useState(false);
  const [witnesses, setWitnesses] = useState<Witness[]>([]);
  const [agentInvokes, setAgentInvokes] = useState<AgentInvoke[]>([]);
  const [dreamPreview, setDreamPreview] = useState<DreamPreview | null>(null);
  const [dreaming, setDreaming] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "state") setTelemetry(msg.data);
      if (msg.type === "event") fetchWitnesses();
      if (msg.type === "agent_invoke") {
        const record = msg.data as AgentInvoke;
        setAgentInvokes((prev) => [record, ...prev].slice(0, 24));
      }
      if (msg.type === "dream") {
        setDreaming(false);
        const d = msg.data;
        if (d?.surrogate && d?.truth) {
          setDreamPreview({
            surrogate: d.surrogate,
            truth: d.truth,
            divergence_at: d.divergence_at ?? 0,
            source: msg.source ?? "unknown",
          });
        }
      }
    };

    fetchWitnesses();
    fetchActivity();
    const iv = setInterval(() => {
      fetchWitnesses();
      fetchActivity();
    }, 12000);

    return () => {
      clearInterval(iv);
      ws.close();
    };
  }, []);

  async function fetchWitnesses() {
    try {
      const r = await fetch("/api/witnesses?limit=12");
      const d = await r.json();
      setWitnesses(d.witnesses ?? []);
    } catch {
      /* offline */
    }
  }

  async function fetchActivity() {
    try {
      const r = await fetch("/api/activity?limit=30");
      const d = await r.json();
      const invokes = (d.activity ?? [])
        .filter((a: { kind: string }) => a.kind === "agent_invoke")
        .map((a: { payload: AgentInvoke }) => a.payload);
      if (invokes.length) {
        setAgentInvokes((prev) => {
          const seen = new Set(prev.map((p) => p.timestamp));
          const merged = [...prev];
          for (const inv of invokes) {
            if (!seen.has(inv.timestamp)) merged.push(inv);
          }
          return merged.sort((a, b) => b.timestamp - a.timestamp).slice(0, 24);
        });
      }
    } catch {
      /* offline */
    }
  }

  function steer(prompt: string) {
    wsRef.current?.send(JSON.stringify({ type: "steer", prompt }));
  }

  function project(theta1: number, theta2: number) {
    wsRef.current?.send(JSON.stringify({ type: "project", theta1, theta2 }));
  }

  function dream(steps = 60) {
    setDreaming(true);
    wsRef.current?.send(JSON.stringify({ type: "dream", steps }));
  }

  return {
    telemetry,
    connected,
    witnesses,
    agentInvokes,
    dreamPreview,
    steer,
    project,
    dream,
    dreaming,
  };
}
