import { useEffect, useRef, useState } from "react";
import type { ServiceRover } from "../missions/api";
import type { ServiceConfig } from "../config";
import { studentCarry } from "../missions/studentCarry";
import { runStudentService, type PromptKind, type ServicePrompt } from "../service/studentService";
import { speakEnglish } from "../speech";
import { ManualPathClearance } from "./ManualPathClearance";

interface Props {
  rover: ServiceRover;
  config: ServiceConfig;
  eligible: boolean;
  acquire(): void;
  cancel(): boolean;
  emergencyStop(): void;
  clearance(confirmed: boolean): boolean;
}
export function StudentServicePanel({ rover, config, eligible, acquire, cancel, emergencyStop, clearance }: Props) {
  const [running, setRunning] = useState(false);
  const [clearanceGeneration, setClearanceGeneration] = useState(0);
  const [detail, setDetail] = useState("Acquire control and confirm a clear path before starting.");
  const [input, setInput] = useState<{ kind: PromptKind; message: string; reply(value: boolean): void } | null>(null);
  const controller = useRef<AbortController | null>(null);
  // useRoverSocket exposes a new cancel callback on each telemetry render.
  // Lifecycle cleanup must track mounting/eligibility, not callback identity.
  const actions = useRef({ cancel, clearance });
  actions.current = { cancel, clearance };
  const stop = () => { controller.current?.abort(); cancel(); clearance(false); };
  useEffect(() => {
    if (!eligible) { controller.current?.abort(); actions.current.cancel(); actions.current.clearance(false); }
  }, [eligible]);
  useEffect(() => {
    const suspend = () => {
      if (document.hidden) { controller.current?.abort(); actions.current.cancel(); actions.current.clearance(false); }
    };
    document.addEventListener("visibilitychange", suspend);
    return () => {
      document.removeEventListener("visibilitychange", suspend);
      controller.current?.abort();
      actions.current.cancel();
      actions.current.clearance(false);
    };
  }, []);
  const start = async () => {
    if (controller.current || !eligible) return;
    const run = new AbortController();
    controller.current = run;
    setRunning(true);
    const prompt: ServicePrompt = (kind, message, signal) => new Promise((resolve, reject) => {
      signal.throwIfAborted();
      const cleanup = () => { signal.removeEventListener("abort", abort); setInput(null); };
      const abort = () => { cleanup(); reject(signal.reason); };
      signal.addEventListener("abort", abort, { once: true });
      setInput({ kind, message, reply: (value) => { cleanup(); resolve(value); } });
    });
    try {
      await runStudentService(studentCarry, {
        rover, config, signal: run.signal,
        report: (progress) => setDetail(progress.detail),
        say: (message) => { setDetail(message); speakEnglish(message); }
      }, prompt);
      setDetail("Service complete (stop confirmed)");
    } catch (error) {
      setDetail(error instanceof Error ? error.message : "Service stopped");
    } finally {
      controller.current = null;
      setRunning(false);
      setClearanceGeneration((value) => value + 1);
      setInput(null);
      clearance(false);
    }
  };
  return <section className="panel" aria-label="Student service">
    <h2>{studentCarry.title}</h2>
    <p role="status">{detail}</p>
    <button className="button" disabled={running || eligible} onClick={acquire}>Acquire control</button>
    <ManualPathClearance key={clearanceGeneration} eligible={eligible} blocked={false} onChange={clearance} />
    <button className="button" disabled={running || !eligible} onClick={() => void start()}>Start service</button>
    {input && <div><p>{input.message}</p>
      <button className="button" onClick={() => input.reply(true)}>{input.kind === "question" ? "Yes" : input.kind === "loaded" ? "Items are loaded" : "We have arrived"}</button>
      {input.kind === "question" && <button className="button" onClick={() => input.reply(false)}>No</button>}
    </div>}
    <button className="button button--stop" disabled={!running} onClick={stop}>Cancel and stop</button>
    <button className="button button--estop" onClick={() => { stop(); emergencyStop(); }}>Emergency stop</button>
  </section>;
}
