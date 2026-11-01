import { useEffect, useRef, useState } from "react";
import { getSpeechRecognitionConstructor, type SpeechRecognitionInstance } from "../speechRecognition";

export function VoiceAnswerButton({ disabled, automatic = false, ready, onAnswer, onStatus }: {
  disabled: boolean;
  automatic?: boolean;
  ready?: Promise<void>;
  onAnswer(text: string): void;
  onStatus(message: string): void;
}) {
  const [listening, setListening] = useState(false);
  const current = useRef<SpeechRecognitionInstance | null>(null);
  const Constructor = getSpeechRecognitionConstructor();
  const abort = () => {
    const recognition = current.current;
    current.current = null;
    recognition?.abort();
  };
  useEffect(() => {
    if (disabled) { abort(); setListening(false); }
    const hide = () => { if (document.hidden) { abort(); setListening(false); } };
    document.addEventListener("visibilitychange", hide);
    return () => { document.removeEventListener("visibilitychange", hide); abort(); };
  }, [disabled]);
  const listen = () => {
    if (!Constructor || disabled || current.current || document.hidden) return;
    window.speechSynthesis?.cancel();
    const recognition = new Constructor();
    current.current = recognition;
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;
    setListening(true);
    onStatus("Listening for your answer...");
    recognition.onresult = event => {
      if (current.current !== recognition) return;
      const text = event.results[0]?.[0]?.transcript.trim();
      abort(); setListening(false);
      if (text) onAnswer(text);
    };
    recognition.onerror = event => {
      if (current.current !== recognition) return;
      abort(); setListening(false);
      onStatus(event.error === "not-allowed" ? "Microphone access denied. You can still select an answer." : "Could not hear your answer. Please try again or select an answer.");
    };
    recognition.onend = () => {
      if (current.current !== recognition) return;
      current.current = null; setListening(false);
      onStatus("No answer heard. Please try again or select an answer.");
    };
    try { recognition.start(); }
    catch { abort(); setListening(false); onStatus("Could not start the microphone. You can still select an answer."); }
  };
  const listenNow = useRef(listen);
  listenNow.current = listen;
  useEffect(() => {
    let cancelled = false;
    if (automatic && !disabled) void Promise.resolve(ready).then(() => {
      if (!cancelled) listenNow.current();
    });
    return () => { cancelled = true; abort(); setListening(false); };
  }, [automatic, disabled, ready]);
  if (!Constructor) return null;
  return <button className="button" disabled={disabled || listening}
    aria-label="Answer the current question in English" onClick={listen}>
    {listening ? "Listening..." : "Answer by voice"}
  </button>;
}
