import { useEffect, useState } from "react";

type Props = {
  eligible: boolean;
  blocked: boolean;
  onChange: (confirmed: boolean) => void;
};

export function ManualPathClearance({ eligible, blocked, onChange }: Props) {
  const [until, setUntil] = useState<number | null>(null);
  const [clock, setClock] = useState(Date.now);
  const allowed = eligible && !blocked;
  useEffect(() => {
    if (!allowed) setUntil(null);
  }, [allowed]);
  useEffect(() => {
    if (until === null || !allowed) return;
    const revoke = () => setUntil(null);
    const visibility = () => { if (document.hidden) revoke(); };
    const tick = () => {
      const now = Date.now();
      setClock(now);
      if (now >= until || document.hidden) { revoke(); return; }
      onChange(true);
    };
    tick();
    const timer = window.setInterval(tick, 300);
    const expiry = window.setTimeout(revoke, Math.max(0, until - Date.now()));
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("blur", revoke);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(expiry);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("blur", revoke);
      onChange(false);
    };
  }, [until, allowed, onChange]);
  const active = allowed && until !== null && clock < until;
  return <div className="path-clearance">
    <button
      className={`button path-clearance__button${active ? " is-authorized" : ""}`}
      disabled={!allowed}
      aria-pressed={active}
      onClick={() => {
        if (active) setUntil(null);
        else { setClock(Date.now()); setUntil(Date.now() + 30_000); }
      }}
    >{active ? `Revoke clear path · ${Math.ceil((until! - clock) / 1000)} s` : "Confirm clear path · 30 s"}</button>
    {blocked && <span>Forward motion blocked</span>}
  </div>;
}
