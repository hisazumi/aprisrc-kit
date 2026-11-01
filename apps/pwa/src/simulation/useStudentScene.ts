import { useCallback, useEffect, useRef, useState } from "react";
import { StudentSceneRunner, type StudentScene, type SceneFrame } from "./studentScene";

export function useStudentScene() {
  const runner = useRef<StudentSceneRunner | null>(null);
  const [frame, setFrame] = useState<SceneFrame | null>(null);
  const [active, setActive] = useState(false);
  const [definition, setDefinition] = useState<StudentScene | null>(null);
  const start = useCallback((scene: StudentScene) => {
    const snapshot = structuredClone(scene);
    setDefinition(snapshot);
    runner.current = new StudentSceneRunner(snapshot, performance.now() / 1000);
    setFrame(runner.current.update(performance.now() / 1000)); setActive(true);
  }, []);
  const stop = useCallback(() => { runner.current = null; setActive(false); }, []);
  const next = useCallback(() => {
    if (runner.current) setFrame(runner.current.next(performance.now() / 1000));
  }, []);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      if (runner.current) setFrame(runner.current.update(performance.now() / 1000));
    }, 50);
    const hidden = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", hidden);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", hidden); };
  }, [active, stop]);
  return { definition, frame, active, start, stop, next };
}
