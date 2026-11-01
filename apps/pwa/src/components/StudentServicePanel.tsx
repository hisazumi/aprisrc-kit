import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ServiceRover } from "../missions/api";
import type { ServiceConfig } from "../config";
import { runStudentService, type StudentService, type ServiceQuestion, type ServicePrompt } from "../service/studentService";
import { speakEnglish } from "../speech";
import { ManualPathClearance } from "./ManualPathClearance";
import { choiceOption, normalizedSpeech, matchingSpokenChoices } from "../service/simulatedSpeech";
import { VoiceAnswerButton } from "./VoiceAnswerButton";
import { assistantApi } from "../assistantApi";

interface Props {
  service: StudentService;
  rover: ServiceRover;
  config: ServiceConfig;
  eligible: boolean;
  blockedReason?: string;
  acquire(): void;
  cancel(): boolean;
  emergencyStop(): void;
  clearance(confirmed: boolean): boolean;
  simulator?: { available: boolean; unavailableReason?: string; name?: string; startLabel?: string; prepare(signal: AbortSignal): Promise<void> };
  speech?: { id: number; text: string };
  execution?: ReactNode;
  resetToken?: number;
  onRunningChange?(running: boolean): void;
  voiceDefault?: boolean;
}
export function StudentServicePanel({ service, rover, config, eligible, blockedReason, acquire, cancel, emergencyStop, clearance, simulator, resetToken, onRunningChange, execution, speech, voiceDefault = false }: Props) {
  const [voiceMode, setVoiceMode] = useState(voiceDefault);
  const voiceModeNow = useRef(voiceMode);
  voiceModeNow.current = voiceMode;
  const speechDone = useRef<Promise<void>>(Promise.resolve());
  useEffect(() => { setVoiceMode(voiceDefault); }, [voiceDefault]);
  const [running, setRunning] = useState(false);
  const [clearanceGeneration, setClearanceGeneration] = useState(0);
  const [detail, setDetail] = useState("");
  const [input, setInput] = useState<(ServiceQuestion & { id: number; reply(value: string): void }) | null>(null);
  const questionId = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const finished = useRef<Promise<void>>(Promise.resolve());
  const transition = useRef<AbortController | null>(null);
  const [switching, setSwitching] = useState(false);
  const [speechResult, setSpeechResult] = useState("");
  const answerRequest = useRef<AbortController | null>(null);
  const [answerBusy, setAnswerBusy] = useState(false);
  const inputNow = useRef(input);
  inputNow.current = input;
  useEffect(() => () => answerRequest.current?.abort(), []);
  const heard = useRef<number | null>(null);
  const eligibleNow = useRef(eligible);
  eligibleNow.current = eligible;
  // useRoverSocket exposes a new cancel callback on each telemetry render.
  // Lifecycle cleanup must track mounting/eligibility, not callback identity.
  const actions = useRef({ cancel, clearance });
  actions.current = { cancel, clearance };
  useEffect(() => { onRunningChange?.(running || switching); }, [running, switching, onRunningChange]);
  useEffect(() => {
    if (controller.current) {
      controller.current.abort(new Error("Scene reset")); actions.current.cancel(); actions.current.clearance(false);
    }
  }, [resetToken]);
  useEffect(() => {
    if (!simulator || !running || !eligible) return;
    const renew = () => { if (!document.hidden && controller.current && !controller.current.signal.aborted) actions.current.clearance(true); };
    renew();
    const timer = window.setInterval(renew, 300);
    return () => { window.clearInterval(timer); actions.current.clearance(false); };
  }, [Boolean(simulator), running, eligible]);
  const stop = () => { answerRequest.current?.abort(); transition.current?.abort(); controller.current?.abort(); cancel(); clearance(false); };
  const resumeConversation = (message?: string) => {
    if (voiceModeNow.current) {
      // A new readiness promise re-arms this question's microphone after speech.
      speechDone.current = message ? Promise.resolve(speakEnglish(message)) : Promise.resolve();
    }
  };
  const answerSpeech = async (text: string) => {
    const question = input;
    if (!eligibleNow.current || !question || !controller.current || controller.current.signal.aborted) return;
    if (normalizedSpeech(text) === "stop" || normalizedSpeech(text) === "停止") {
      stop(); setSpeechResult("Stop requested"); return;
    }
    answerRequest.current?.abort();
    const matches = matchingSpokenChoices(text, question.options ?? question.choices);
    if (matches.length > 1) {
      const message = "That matches more than one answer. Please select an answer on screen.";
      if (voiceModeNow.current) void speakEnglish(message);
      setAnswerBusy(false); setSpeechResult(message); return;
    }
    if (matches.length === 1) { question.reply(matches[0].value); setSpeechResult(`Heard: ${text}. Answer accepted.`); return; }
    const request = new AbortController();
    answerRequest.current = request;
    setAnswerBusy(true); setSpeechResult(`Heard: ${text}. Interpreting answer...`);
    try {
      const result = await assistantApi.answer(question.message, text,
        (question.options ?? question.choices).map(choiceOption), request.signal);
      if (request.signal.aborted || inputNow.current?.id !== question.id || !eligibleNow.current
        || !controller.current || controller.current.signal.aborted) return;
      if (result.value !== null && question.choices.includes(result.value)) {
        question.reply(result.value);
        setSpeechResult(`Heard: ${text}. Answer accepted (${result.source}).`);
      } else {
        if (result.source !== "rules") {
          resumeConversation(result.outcome === "acknowledgement" ? undefined : result.response);
        }
        setSpeechResult(`Heard: ${text}. ${result.outcome === "acknowledgement" ? "Acknowledged." : "No matching answer."} ${result.response}`);
      }
    } catch {
      if (!request.signal.aborted) setSpeechResult("Could not interpret your answer. Please select an answer or try again.");
    } finally {
      if (answerRequest.current === request) { answerRequest.current = null; setAnswerBusy(false); }
    }
  };
  useEffect(() => {
    if (!speech || heard.current === speech.id) return;
    heard.current = speech.id;
    if (!simulator || !eligible) { setSpeechResult("Speech not accepted: control unavailable"); return; }
    const value = normalizedSpeech(speech.text);
    if (value === "stop" || value === "停止") {
      stop(); setSpeechResult(`Person: ${speech.text} · Stop requested`); return;
    }
    if (input) void answerSpeech(speech.text);
    else setSpeechResult(`Person: ${speech.text} · No question is waiting`);
  }, [speech, input, simulator, eligible]);
  useEffect(() => {
    if (!eligible) { transition.current?.abort(); controller.current?.abort(); actions.current.cancel(); actions.current.clearance(false); }
  }, [eligible]);
  useEffect(() => {
    const suspend = () => {
      if (document.hidden) { transition.current?.abort(); controller.current?.abort(); actions.current.cancel(); actions.current.clearance(false); }
    };
    document.addEventListener("visibilitychange", suspend);
    return () => {
      document.removeEventListener("visibilitychange", suspend);
      transition.current?.abort();
      controller.current?.abort();
      actions.current.cancel();
      actions.current.clearance(false);
    };
  }, []);
  const start = async () => {
    if (blockedReason || controller.current || (simulator ? !simulator.available : !eligible)) return;
    const run = new AbortController();
    controller.current = run;
    let finish!: () => void;
    finished.current = new Promise(resolve => { finish = resolve; });
    setRunning(true);
    const prompt: ServicePrompt = (question, signal) => new Promise((resolve, reject) => {
      signal.throwIfAborted();
      let settled = false;
      const cleanup = () => { answerRequest.current?.abort(); setAnswerBusy(false); signal.removeEventListener("abort", abort); setInput(null); };
      const abort = () => { settled = true; cleanup(); reject(signal.reason); };
      signal.addEventListener("abort", abort, { once: true });
      setSpeechResult("");
      setInput({ ...question, id: ++questionId.current, reply: (value) => {
        if (settled || signal.aborted) return;
        settled = true; cleanup(); resolve(value);
      } });
    });
    try {
      if (simulator) {
        setDetail("Preparing simulator...");
        if (!eligibleNow.current) acquire();
        const deadline = Date.now() + 5000;
        while (!eligibleNow.current) {
          run.signal.throwIfAborted();
          if (Date.now() >= deadline) throw new Error("Could not acquire control. Close other controlling tabs and try again.");
          await new Promise(resolve => window.setTimeout(resolve, 50));
        }
        run.signal.throwIfAborted();
        await simulator.prepare(run.signal);
        run.signal.throwIfAborted();
        clearance(true);
      }
      await runStudentService(service, {
        rover, config, signal: run.signal,
        report: (progress) => setDetail(progress.detail),
        say: (message) => { setDetail(message); speechDone.current = Promise.resolve(speakEnglish(message)); }
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
      finish();
    }
  };
  const startSelected = async () => {
    if (transition.current) return;
    if (!controller.current) { void start(); return; }
    if (!simulator?.available) return;
    const request = new AbortController();
    transition.current = request; setSwitching(true);
    controller.current.abort(new Error("Starting another trial"));
    cancel(); clearance(false);
    try {
      await finished.current;
      request.signal.throwIfAborted();
      await rover.stop("confirm stop before new trial");
      request.signal.throwIfAborted();
      if (!eligibleNow.current || document.hidden) throw new Error("Control is not available");
      void start();
    } catch (error) {
      setDetail(error instanceof Error ? error.message : "New trial cancelled");
    } finally { transition.current = null; setSwitching(false); }
  };
  const unavailableReason = blockedReason ?? (simulator && !simulator.available
    ? simulator.unavailableReason ?? "Simulator control is unavailable." : null);
  const startButton = <button className={running || switching ? "button" : "button button--primary"}
    aria-describedby={unavailableReason ? "student-start-unavailable" : undefined}
    disabled={!!blockedReason || switching || (simulator ? !simulator.available : running || !eligible)}
    onClick={() => void startSelected()}>{switching ? "Stopping previous trial..." : simulator?.startLabel ?? (simulator?.name ? "Start selected scenario" : simulator ? "Start simulation" : "Start service")}</button>;
  return <section className="panel student-service" aria-label="Student service">
    <h2>{service.title}</h2>
    <label><input type="checkbox" checked={voiceMode} onChange={event => setVoiceMode(event.target.checked)} /> Voice conversation</label>
    <p role="status">{input?.message || detail || (simulator ? unavailableReason ? "Simulation unavailable" : "Ready to simulate" : "Acquire control and confirm a clear path before starting.")}</p>
    {unavailableReason && <p id="student-start-unavailable" role="status">{unavailableReason}</p>}
    {!simulator && <>
      <button className="button" disabled={running || eligible} onClick={acquire}>Acquire control</button>
      <ManualPathClearance key={clearanceGeneration} eligible={eligible} blocked={false} onChange={clearance} />
    </>}
    {simulator?.name && <p>Selected scenario: <strong>{simulator.name}</strong></p>}
    {!running && !switching && startButton}
    {input && <div className="student-service__choices">
      {(input.options ?? input.choices).map(choiceOption).map(choice => <button key={choice.value} className="button" onClick={() => input.reply(choice.value)}>{choice.label}</button>)}
      <VoiceAnswerButton key={input.id} disabled={!eligible || !running} automatic={voiceMode} busy={answerBusy}
        ready={speechDone.current} onStatus={setSpeechResult}
        onAnswer={text => { void answerSpeech(text); }} />
    </div>}
    {execution}
    {speechResult && <p role="status">{speechResult}</p>}
    {(running || switching) && startButton}
    <div className="service-stop-actions" data-active={running || switching}>
      <button className="button button--stop" disabled={!running && !switching} onClick={stop}>Cancel and stop</button>
      <button className="button button--estop" onClick={() => { stop(); emergencyStop(); }}>Emergency stop</button>
    </div>
  </section>;
}
