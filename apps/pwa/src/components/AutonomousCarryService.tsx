import {
  type CSSProperties,
  type FormEvent,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState
} from "react";

import {
  assistantApi,
  type AssistantDecision,
  type AssistantIntentDefinition
} from "../assistantApi";
import type { ServiceConfig } from "../config";
import type { MissionDefinition, MissionInput, ServiceRover } from "../missions";
import type { FrontObstacleSnapshot, PersonEvent } from "../protocol";
import {
  advanceCarryConcierge,
  initialCarryConciergeState,
  OFFER_REPLY_TIMEOUT_MS,
  type CarryConciergePhase
} from "../service/carryConcierge";
import { speakEnglish } from "../speech";

interface AutonomousCarryServiceProps {
  connected: boolean;
  isOwner: boolean;
  controlAvailable: boolean;
  estopLatched: boolean;
  batteryPercent: number | null;
  frontObstacle?: FrontObstacleSnapshot | null;
  rover: ServiceRover;
  approachMission: MissionDefinition | undefined;
  mission: MissionDefinition | undefined;
  config: ServiceConfig;
  onAcquireControl: () => void;
  onReleaseControl: () => void;
  onCancelMotion: () => boolean;
  onEmergencyStop: () => void;
  onPathClearanceChange?: (confirmed: boolean) => boolean;
  speak?: (text: string) => void;
  onRunningChange?: (running: boolean) => void;
}

interface SpeechRecognitionResultEvent {
  results: ArrayLike<{ readonly [index: number]: { transcript: string } }>;
}

interface SpeechRecognitionInstance {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  abort: () => void;
}

interface SpeechRecognitionWindow extends Window {
  SpeechRecognition?: new () => SpeechRecognitionInstance;
  webkitSpeechRecognition?: new () => SpeechRecognitionInstance;
}

const consentIntents: readonly AssistantIntentDefinition[] = [
  {
    id: "accept_help",
    description: "Accept the rover's offer to help carry something by following the person.",
    examples: ["お願いします", "机までついてきて", "Yes, please help me"],
    keywords: ["お願い", "はい", "頼む", "手伝って", "ついて", "机まで", "yes", "please"],
    response: "Okay. I will follow you."
  },
  {
    id: "decline_help",
    description: "Decline the rover's offer of carrying assistance.",
    examples: ["大丈夫です", "いりません", "No thank you"],
    keywords: ["大丈夫", "いらない", "いりません", "結構", "no thanks", "no thank you"],
    response: "No problem. I will keep waiting."
  }
];

const activeServiceIntents: readonly AssistantIntentDefinition[] = [
  {
    id: "finish_delivery",
    description: "Finish the carrying service because the person and rover have arrived.",
    examples: ["着いたよ", "ここでいいよ", "We have arrived"],
    keywords: ["着いた", "到着", "ここでいい", "終わり", "arrived", "we are here", "done"],
    response: "We have arrived. Please take your belongings."
  }
];

const loadingIntents: readonly AssistantIntentDefinition[] = [
  {
    id: "items_loaded",
    description: "Confirm that the belongings are on the rover and it may begin following.",
    examples: ["荷物を載せたよ", "準備できた", "The items are loaded"],
    keywords: ["載せた", "のせた", "準備できた", "行こう", "loaded", "ready", "let's go"],
    response: "Thank you. I will follow you."
  }
];

const PATH_CLEARANCE_HEARTBEAT_MS = 400;
const ignorePathClearance = () => false;

const phaseCopy: Record<CarryConciergePhase, { label: string; headline: string }> = {
  paused: { label: "PAUSED", headline: "Ready when you are" },
  waiting: { label: "READY", headline: "I am ready to help" },
  noticing: { label: "NOTICING", headline: "Hello there" },
  approaching: { label: "APPROACHING", headline: "I am coming closer" },
  offering: { label: "OFFERING HELP", headline: "Would you like some help?" },
  loading: { label: "LOADING", headline: "Place your items on the rover" },
  following: { label: "FOLLOWING", headline: "I am following you" },
  cooldown: { label: "WAITING", headline: "No problem" },
  complete: { label: "ARRIVED", headline: "We have arrived" },
  lost: { label: "TARGET LOST", headline: "I lost sight of you" },
  stopped: { label: "STOPPED", headline: "Service stopped" },
  error: { label: "NEEDS HELP", headline: "I could not continue" }
};

export function AutonomousCarryService({
  connected,
  isOwner,
  controlAvailable,
  estopLatched,
  batteryPercent,
  frontObstacle,
  rover,
  approachMission,
  mission,
  config,
  onAcquireControl,
  onReleaseControl,
  onCancelMotion,
  onEmergencyStop,
  onRunningChange,
  onPathClearanceChange = ignorePathClearance,
  speak = speakEnglish
}: AutonomousCarryServiceProps) {
  const [state, dispatch] = useReducer(advanceCarryConcierge, initialCarryConciergeState);
  const [startRequested, setStartRequested] = useState(false);
  const [command, setCommand] = useState("");
  const [assistantReply, setAssistantReply] = useState("Say yes when you would like help.");
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [movementConsent, setMovementConsent] = useState(false);
  const missionAbortRef = useRef<AbortController | null>(null);
  const pendingMissionInputRef = useRef<Partial<MissionInput>>({});
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const recognitionConstructor = getSpeechRecognitionConstructor();
  const copy = phaseCopy[state.phase];
  const active = state.phase !== "paused";
  useEffect(() => { onRunningChange?.(active || startRequested); }, [active, startRequested, onRunningChange]);
  const pathClearEnabled = connected
    && isOwner
    && !estopLatched
    && movementConsent
    && ["approaching", "following"].includes(state.phase);

  useEffect(() => {
    if (!pathClearEnabled) return;
    onPathClearanceChange(true);
    const heartbeat = window.setInterval(
      () => onPathClearanceChange(true),
      PATH_CLEARANCE_HEARTBEAT_MS
    );
    return () => {
      window.clearInterval(heartbeat);
      onPathClearanceChange(false);
    };
  }, [onPathClearanceChange, pathClearEnabled]);

  useEffect(() => {
    if (connected && !estopLatched && (isOwner || startRequested)) return;
    setMovementConsent(false);
    setStartRequested(false);
    if (!connected) {
      missionAbortRef.current?.abort();
      onCancelMotion();
      dispatch({ type: "disarm" });
    }
  }, [connected, estopLatched, isOwner, onCancelMotion, startRequested]);

  useEffect(() => {
    const suspend = () => {
      if (document.visibilityState !== "hidden") return;
      setMovementConsent(false);
      setStartRequested(false);
      onPathClearanceChange(false);
      missionAbortRef.current?.abort();
      onCancelMotion();
      dispatch({ type: "disarm" });
    };
    document.addEventListener("visibilitychange", suspend);
    return () => document.removeEventListener("visibilitychange", suspend);
  }, [onCancelMotion, onPathClearanceChange]);

  const statusNote = useMemo(() => {
    if (!connected) return "Connecting to the rover";
    if (estopLatched) return "Emergency stop is active";
    if (isOwner) return "Service control active";
    if (!controlAvailable) return "Another controller is using the rover";
    return "Ready to start";
  }, [connected, controlAvailable, estopLatched, isOwner]);

  useEffect(() => rover.onPerson((person) => {
    dispatch({ type: "person", person });
  }), [rover]);

  useEffect(() => {
    if (!startRequested || !isOwner) return;
    setStartRequested(false);
    dispatch({ type: "arm" });
    speak("I am ready to help.");
  }, [isOwner, speak, startRequested]);

  useEffect(() => {
    if (state.phase === "paused" || isOwner) return;
    missionAbortRef.current?.abort();
    onCancelMotion();
    dispatch({ type: "disarm" });
  }, [isOwner, onCancelMotion, state.phase]);

  useEffect(() => {
    if (!estopLatched || state.phase === "paused" || state.phase === "error") return;
    missionAbortRef.current?.abort();
    onCancelMotion();
    dispatch({ type: "error", detail: "Emergency stop is active" });
  }, [estopLatched, onCancelMotion, state.phase]);

  useEffect(() => {
    if (state.phase !== "offering") return;
    const message = "Hello. Would you like help carrying something?";
    setAssistantReply(message);
    speak(message);
    const timer = window.setTimeout(() => {
      dispatch({ type: "offer_timeout" });
      setAssistantReply("No reply. I will wait until you move away.");
      speak("No problem. I will keep waiting.");
    }, OFFER_REPLY_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [speak, state.phase]);

  useEffect(() => () => {
    missionAbortRef.current?.abort();
    recognitionRef.current?.abort();
    onPathClearanceChange(false);
  }, [onPathClearanceChange]);

  const startService = () => {
    if (!connected || estopLatched || !controlAvailable || !approachMission || !mission) return;
    setMovementConsent(true);
    if (isOwner) {
      dispatch({ type: "arm" });
      speak("I am ready to help.");
    } else {
      setStartRequested(true);
      onAcquireControl();
    }
  };

  const runApproachMission = async () => {
    if (!approachMission || missionAbortRef.current) return;
    const controller = new AbortController();
    missionAbortRef.current = controller;
    try {
      await approachMission.run({
        rover,
        config,
        signal: controller.signal,
        report: (progress) => dispatch({ type: "mission_progress", progress }),
        say: () => undefined
      });
    } catch (cause) {
      if (!controller.signal.aborted) {
        dispatch({
          type: "error",
          detail: cause instanceof Error ? cause.message : "I could not approach safely"
        });
        speak("I could not approach safely. Stopping.");
      }
    } finally {
      if (missionAbortRef.current === controller) missionAbortRef.current = null;
    }
  };

  useEffect(() => {
    if (state.phase === "approaching") void runApproachMission();
  }, [state.phase]);

  const runCarryMission = async (input?: Partial<MissionInput>) => {
    if (!mission || missionAbortRef.current) return;
    const controller = new AbortController();
    missionAbortRef.current = controller;
    try {
      await mission.run({
        rover,
        config,
        signal: controller.signal,
        report: (progress) => dispatch({ type: "mission_progress", progress }),
        say: speak
      }, {
        intent: mission.trigger?.intent ?? "follow_person",
        destination: input?.destination ?? null,
        followDistance: input?.followDistance ?? "normal"
      });
    } catch (cause) {
      if (!controller.signal.aborted) {
        dispatch({
          type: "error",
          detail: cause instanceof Error ? cause.message : "The service could not continue"
        });
        speak("I could not continue. Stopping.");
      }
    } finally {
      if (missionAbortRef.current === controller) missionAbortRef.current = null;
    }
  };

  const acceptHelp = (input?: Partial<MissionInput>) => {
    pendingMissionInputRef.current = input ?? {};
    dispatch({ type: "accept" });
    const reply = "Of course. Place your items on the rover, then tell me when you are ready.";
    setAssistantReply(reply);
    speak(reply);
  };

  const beginFollowing = () => {
    if (state.phase !== "loading") return;
    dispatch({ type: "loaded" });
    const reply = "Thank you. I will follow you.";
    setAssistantReply(reply);
    speak(reply);
    void runCarryMission(pendingMissionInputRef.current);
  };

  const stopMotion = async (completed: boolean) => {
    setMovementConsent(false);
    missionAbortRef.current?.abort();
    onCancelMotion();
    try {
      await rover.stop(completed ? "carry service complete" : "carry service stopped");
      dispatch({ type: completed ? "complete" : "stop" });
      const reply = completed
        ? "We have arrived. Please take your belongings."
        : "Stopping.";
      setAssistantReply(reply);
      speak(reply);
    } catch (cause) {
      dispatch({
        type: "error",
        detail: cause instanceof Error ? cause.message : "The rover could not stop"
      });
    }
  };

  const endService = async () => {
    await stopMotion(false);
    dispatch({ type: "disarm" });
    setStartRequested(false);
    if (isOwner) onReleaseControl();
  };

  const handleDecision = (decision: AssistantDecision) => {
    setAssistantReply(decision.response);
    if (state.phase === "offering") {
      if (decision.action === "accept_help") {
        acceptHelp({
          destination: decision.destination,
          followDistance: decision.follow_distance
        });
      } else if (decision.action === "decline_help" || decision.action === "stop") {
        dispatch({ type: "decline" });
        speak(decision.response);
      } else {
        speak(decision.response);
      }
      return;
    }

    if (state.phase === "loading") {
      if (decision.action === "items_loaded") {
        beginFollowing();
      } else if (decision.action === "stop") {
        void stopMotion(false);
      } else {
        speak(decision.response);
      }
      return;
    }

    if (state.phase === "following") {
      if (decision.action === "finish_delivery" || decision.action === "wait_here") {
        void stopMotion(true);
      } else if (decision.action === "stop") {
        void stopMotion(false);
      } else {
        speak(decision.response);
      }
    }
  };

  const runCommand = async (text: string) => {
    if (!text || assistantBusy) return;
    setAssistantBusy(true);
    try {
      const intents = state.phase === "offering"
        ? consentIntents
        : state.phase === "loading" ? loadingIntents : activeServiceIntents;
      const decision = await assistantApi.interpret(text, intents);
      setCommand("");
      handleDecision(decision);
    } catch (cause) {
      const reply = cause instanceof Error ? cause.message : "I could not understand that.";
      setAssistantReply(reply);
      speak(reply);
    } finally {
      setAssistantBusy(false);
    }
  };

  const submitCommand = (event: FormEvent) => {
    event.preventDefault();
    void runCommand(command.trim());
  };

  const listenForCommand = () => {
    if (!recognitionConstructor || listening || assistantBusy) return;
    const recognition = new recognitionConstructor();
    recognitionRef.current = recognition;
    recognition.lang = "ja-JP";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript.trim();
      if (!transcript) return;
      setCommand(transcript);
      void runCommand(transcript);
    };
    recognition.onerror = () => {
      setAssistantReply("I could not hear that. Please try again.");
      setListening(false);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setListening(false);
    };
    recognition.start();
  };

  const restart = () => {
    setAssistantReply("Say yes when you would like help.");
    setMovementConsent(false);
    dispatch({ type: "disarm" });
  };

  const direction = personDirection(state.person);
  const markerStyle = personMarkerStyle(state.person);
  const commandEnabled = ["offering", "loading", "following"].includes(state.phase);

  return (
    <section className={`carry-service carry-service--${state.phase}`} aria-label="Carry assistant">
      <header className="carry-service__statusbar">
        <div>
          <span className={`carry-service__signal${connected ? " is-online" : ""}`} />
          <strong>{statusNote}</strong>
        </div>
        <span>{batteryPercent == null ? "Battery —" : `Battery ${Math.round(batteryPercent)}%`}</span>
      </header>

      <div className="carry-service__stage">
        <p className="carry-service__phase">{copy.label}</p>
        <h2>{copy.headline}</h2>
        <p className="carry-service__detail" role="status" aria-live="polite">
          {state.detail}
        </p>

        <div className="person-guide" aria-label={direction.label}>
          <div className="person-guide__track">
            {state.person?.status === "detected" && (
              <span className="person-guide__marker" style={markerStyle} />
            )}
            <span className="person-guide__center" />
          </div>
          <div className="person-guide__copy">
            <strong>{direction.label}</strong>
            <span>{personDistance(state.person)}</span>
          </div>
        </div>

        {active && (
          <div className="path-clearance">
            <span>{pathClearEnabled ? "Supervised movement enabled" : "Movement paused"}</span>
            <span>
              {frontObstacle?.state === "CLEAR"
                ? "Forward steps enabled"
                : frontObstacle?.state === "BLOCKED"
                  ? "Forward motion blocked"
                  : "Forward steps paused"}
            </span>
          </div>
        )}

        {state.phase === "paused" && (
          <button
            className="button carry-service__start"
            disabled={
              !connected
              || !controlAvailable
              || estopLatched
              || !approachMission
              || !mission
              || startRequested
            }
            onClick={startService}
          >
            {startRequested ? "Starting…" : "Start service and allow movement"}
          </button>
        )}

        {state.phase === "offering" && (
          <div className="carry-service__choices">
            <button
              className="button button--primary"
              onClick={() => {
                acceptHelp();
              }}
            >
              Yes, help me
            </button>
            <button
              className="button button--quiet"
              onClick={() => {
                dispatch({ type: "decline" });
                setAssistantReply("No problem. I will keep waiting.");
                speak("No problem. I will keep waiting.");
              }}
            >
              No, thank you
            </button>
          </div>
        )}

        {state.phase === "loading" && (
          <div className="carry-service__motion-actions">
            <button className="button button--primary" onClick={beginFollowing}>
              Items are loaded
            </button>
            <button className="button button--stop" onClick={() => void stopMotion(false)}>
              Cancel
            </button>
          </div>
        )}

        {state.phase === "following" && (
          <div className="carry-service__motion-actions">
            <button className="button carry-service__arrived" onClick={() => void stopMotion(true)}>
              We have arrived
            </button>
            <button className="button button--stop" onClick={() => void stopMotion(false)}>
              Stop
            </button>
          </div>
        )}

        {["complete", "lost", "stopped", "error"].includes(state.phase) && active && (
          <button className="button button--primary carry-service__restart" onClick={restart}>
            Look for the next person
          </button>
        )}
      </div>

      {commandEnabled && (
        <div className="carry-service__conversation">
          <p>{assistantReply}</p>
          <form onSubmit={submitCommand}>
            <input
              aria-label="Talk to the carry assistant"
              maxLength={500}
              placeholder={state.phase === "offering"
                ? "はい、お願いします"
                : state.phase === "loading" ? "荷物を載せたよ" : "ここでいいよ"}
              value={command}
              onChange={(event) => setCommand(event.target.value)}
            />
            {recognitionConstructor && (
              <button
                className="button button--quiet"
                type="button"
                disabled={assistantBusy || listening}
                onClick={listenForCommand}
              >
                {listening ? "Listening…" : "Speak"}
              </button>
            )}
            <button
              className="button button--primary"
              disabled={assistantBusy || listening || !command.trim()}
            >
              {assistantBusy ? "Thinking…" : "Send"}
            </button>
          </form>
        </div>
      )}

      <footer className="carry-service__controls">
        {active && (
          <button className="button button--stop" onClick={() => void endService()}>
            End service
          </button>
        )}
        <button className="button button--estop" disabled={!connected} onClick={onEmergencyStop}>
          Emergency stop
        </button>
      </footer>
    </section>
  );
}

function personDirection(person: Readonly<PersonEvent> | undefined): { label: string } {
  if (person?.status !== "detected" || person.bearingDeg === undefined) {
    return { label: "Looking for a person" };
  }
  if (person.bearingDeg > 8) return { label: "Person on the left" };
  if (person.bearingDeg < -8) return { label: "Person on the right" };
  return { label: "Person ahead" };
}

function personDistance(person: Readonly<PersonEvent> | undefined): string {
  if (person?.status !== "detected" || person.width === undefined) return "No current target";
  const closeWidth = person.source === "camera" || person.source === "recorded" ? 0.65 : 0.36;
  if (person.width >= closeWidth) return "Close by";
  if (person.width >= closeWidth - 0.12) return "Comfortable distance";
  return "A little farther away";
}

function personMarkerStyle(person: Readonly<PersonEvent> | undefined): CSSProperties | undefined {
  if (person?.status !== "detected" || person.bearingDeg === undefined) return undefined;
  const position = Math.max(6, Math.min(94, 50 - (person.bearingDeg / 45) * 44));
  return { left: `${position}%` };
}

function getSpeechRecognitionConstructor(): (new () => SpeechRecognitionInstance) | undefined {
  if (typeof window === "undefined") return undefined;
  const speechWindow = window as SpeechRecognitionWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
}
