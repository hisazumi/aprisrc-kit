import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { assistantApi, type AssistantDecision } from "../assistantApi";
import type { ServiceConfig } from "../config";
import type {
  MissionDefinition,
  MissionInput,
  MissionProgress,
  ServiceRover
} from "../missions";
import { speakEnglish } from "../speech";
import { getSpeechRecognitionConstructor, type SpeechRecognitionInstance } from "../speechRecognition";

interface HumanInteractionPanelProps {
  disabled: boolean;
  rover: ServiceRover;
  missions: readonly MissionDefinition[];
  config: ServiceConfig;
  cancelMotion: () => boolean;
}

const initialDetail = "Ready when you are";

export function HumanInteractionPanel({
  disabled,
  rover,
  missions,
  config,
  cancelMotion
}: HumanInteractionPanelProps) {
  const [phase, setPhase] = useState("idle");
  const [detail, setDetail] = useState(initialDetail);
  const [lastPerson, setLastPerson] = useState<MissionProgress["person"]>();
  const [command, setCommand] = useState("");
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [missionRunning, setMissionRunning] = useState(false);
  const [listening, setListening] = useState(false);
  const [assistantReply, setAssistantReply] = useState("Ask me to guide, carry, follow, wait, or stop");
  const [assistantSource, setAssistantSource] = useState<AssistantDecision["source"] | "local">("local");
  const abortRef = useRef<AbortController | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const requestedStopRef = useRef<"waiting" | "stopped" | null>(null);
  const active = missionRunning;
  const recognitionConstructor = getSpeechRecognitionConstructor();
  const assistantIntents = useMemo(() => missions.flatMap((mission) => {
    const trigger = mission.trigger;
    return trigger ? [{
      id: trigger.intent,
      description: trigger.description,
      examples: trigger.examples,
      keywords: trigger.keywords,
      response: trigger.response
    }] : [];
  }), [missions]);

  useEffect(() => () => recognitionRef.current?.abort(), []);

  const update = (next: MissionProgress) => {
    setPhase(next.phase);
    setDetail(next.detail);
    if (next.person) setLastPerson(next.person);
    else if (next.phase === "lost") setLastPerson(undefined);
  };

  const runTriggeredMission = async (
    intent: string,
    input?: MissionInput,
    announce = true
  ) => {
    const mission = missions.find((candidate) => candidate.trigger?.intent === intent);
    if (!mission || abortRef.current || active) return;
    setMissionRunning(true);
    requestedStopRef.current = null;
    const controller = new AbortController();
    abortRef.current = controller;
    if (announce && mission.trigger) speakEnglish(mission.trigger.response);
    try {
      await mission.run({
        rover,
        config,
        signal: controller.signal,
        report: update,
        say: speakEnglish
      }, input);
    } catch (cause) {
      if (controller.signal.aborted) {
        const requested = (
          requestedStopRef.current as "waiting" | "stopped" | null
        ) ?? "stopped";
        setPhase(requested);
        setDetail(requested === "waiting" ? "Waiting here" : "Stopped");
      } else {
        setPhase("error");
        setDetail(cause instanceof Error ? cause.message : "Interaction failed");
        speakEnglish("Stopping.");
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setMissionRunning(false);
    }
  };

  const halt = async (next: "waiting" | "stopped", announce = true) => {
    requestedStopRef.current = next;
    abortRef.current?.abort();
    cancelMotion();
    try {
      await rover.stop(next === "waiting" ? "wait here" : "interaction stopped");
      setPhase(next);
      setDetail(next === "waiting" ? "Waiting here" : "Stopped");
      if (announce) speakEnglish(next === "waiting" ? "I will wait here." : "Stopping.");
    } catch (cause) {
      setPhase("error");
      setDetail(cause instanceof Error ? cause.message : "Could not stop");
    }
  };

  const runAssistantCommand = async (text: string) => {
    if (!text || assistantBusy) return;
    setAssistantBusy(true);
    try {
      const decision = await assistantApi.interpret(text, assistantIntents);
      setAssistantSource(decision.source);
      setAssistantReply(decision.response);
      setCommand("");

      const requiresControl = !["clarify", "report_status"].includes(decision.action);
      if (requiresControl && disabled) {
        const reply = "Please acquire control before asking me to move.";
        setAssistantReply(reply);
        speakEnglish(reply);
        return;
      }

      speakEnglish(decision.response);
      if (decision.action === "wait_here") void halt("waiting", false);
      else if (decision.action === "stop") void halt("stopped", false);
      else if (!["clarify", "report_status"].includes(decision.action)) {
        void runTriggeredMission(decision.action, {
          intent: decision.action,
          destination: decision.destination,
          followDistance: decision.follow_distance
        }, false);
      }
    } catch (cause) {
      const reply = cause instanceof Error ? cause.message : "I could not understand that request.";
      setAssistantReply(reply);
      setAssistantSource("local");
      speakEnglish(reply);
    } finally {
      setAssistantBusy(false);
    }
  };

  const submitAssistantCommand = (event: FormEvent) => {
    event.preventDefault();
    void runAssistantCommand(command.trim());
  };

  const listenForCommand = () => {
    if (!recognitionConstructor || listening || assistantBusy) return;
    const recognition = new recognitionConstructor();
    recognitionRef.current = recognition;
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onstart = () => {
      setListening(true);
      setAssistantReply("Listening…");
    };
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript.trim();
      if (!transcript) return;
      setCommand(transcript);
      setAssistantReply(`Heard: ${transcript}`);
      void runAssistantCommand(transcript);
    };
    recognition.onerror = (event) => {
      const reply = event.error === "not-allowed"
        ? "Microphone access was not allowed."
        : "I could not hear that. Please try again.";
      setAssistantReply(reply);
      setListening(false);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setListening(false);
    };
    recognition.start();
  };

  return (
    <article className="panel panel--interaction">
      <div className="interaction-heading">
        <div>
          <p className="section-label">HUMAN INTERACTION</p>
          <h2>Come, follow, and guide</h2>
        </div>
        <span className={`interaction-phase interaction-phase--${phase}`}>{phase}</span>
      </div>

      <div className="interaction-status" role="status" aria-live="polite">
        <strong>{detail}</strong>
        <span>
          {lastPerson?.status === "detected"
            ? `person ${Math.round((lastPerson.width ?? 0) * 100)}% · ${formatBearing(lastPerson.bearingDeg)}`
            : "No current person observation"}
        </span>
      </div>

      <div className="assistant-command">
        <div className="assistant-command__heading">
          <p className="section-label">NATURAL LANGUAGE</p>
          <span>{assistantSource === "openai" ? "LLM" : "LOCAL RULES"}</span>
        </div>
        <form className="assistant-command__form" onSubmit={(event) => void submitAssistantCommand(event)}>
          <input
            aria-label="Natural language rover command"
            maxLength={500}
            placeholder="Guide me to the entrance"
            value={command}
            onChange={(event) => setCommand(event.target.value)}
          />
          {recognitionConstructor ? (
            <button
              className={`button button--quiet assistant-command__speak${listening ? " is-listening" : ""}`}
              type="button"
              disabled={assistantBusy || listening}
              onClick={listenForCommand}
              aria-label="Speak a rover command in English"
            >
              {listening ? "Listening…" : "Speak"}
            </button>
          ) : null}
          <button
            className="button button--primary"
            disabled={assistantBusy || listening || !command.trim()}
          >
            {assistantBusy ? "Thinking…" : "Send"}
          </button>
        </form>
        <p className="assistant-command__reply" role="status">{assistantReply}</p>
      </div>

      <div className="interaction-actions">
        <button
          className="button button--primary"
          disabled={disabled || active}
          onClick={() => void runTriggeredMission("come_here")}
        >
          Come here
        </button>
        <button
          className="button button--primary"
          disabled={disabled || active}
          onClick={() => void runTriggeredMission("follow_person")}
        >
          Follow me
        </button>
        <button
          className="button button--primary"
          disabled={disabled || active}
          onClick={() => void runTriggeredMission("guide_visitor", {
            intent: "guide_visitor",
            destination: "entrance",
            followDistance: "normal"
          })}
        >
          Guide me
        </button>
        <button
          className="button button--quiet"
          disabled={disabled}
          onClick={() => void halt("waiting")}
        >
          Wait here
        </button>
        <button
          className="button button--stop"
          disabled={disabled}
          onClick={() => void halt("stopped")}
        >
          Stop
        </button>
      </div>
    </article>
  );
}

function formatBearing(value: number | undefined): string {
  return value === undefined ? "bearing —" : `bearing ${value.toFixed(1)}°`;
}
