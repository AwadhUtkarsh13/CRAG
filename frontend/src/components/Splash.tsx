import { useEffect, useState } from "react";

const CAPTIONS = ["Preparing your workspace", "Loading your library", "Almost ready"];

export default function Splash({ leaving = false, caption }: { leaving?: boolean; caption?: string }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (caption) return;
    const id = window.setInterval(() => setStep((s) => Math.min(s + 1, CAPTIONS.length - 1)), 2600);
    return () => window.clearInterval(id);
  }, [caption]);
  const text = caption ?? CAPTIONS[step];
  return (
    <div className={`splash${leaving ? " leaving" : ""}`} aria-busy="true" aria-live="polite">
      <div className="splash-inner">
        <div className="wordmark" aria-label="CRAG">
          <span>C</span>
          <span>R</span>
          <span>A</span>
          <span>G</span>
        </div>
        <div className="progress-track">
          <div className="progress-bar-indeterminate" />
        </div>
        <div className="splash-caption" key={text}>
          {text}
        </div>
      </div>
    </div>
  );
}
