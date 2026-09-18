import { useEffect, useState } from "react";

export default function ProgressStream({ lines, error }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (error) return;
    const start = Date.now();
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(interval);
  }, [error]);

  return (
    <div className="progress-stream">
      <h2>Building your learning path</h2>
      <p className="progress-note">
        This can take a few minutes — each concept needs its own search and a
        model call to judge the results, so long gaps between lines are
        normal, not stuck.
      </p>
      <ul className="progress-lines">
        {lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
        {lines.length === 0 && !error && <li className="progress-waiting">Starting…</li>}
      </ul>
      {!error && (
        <p className="progress-elapsed">
          <span className="progress-spinner" aria-hidden="true" /> Still working — {elapsed}s elapsed
        </p>
      )}
      {error && <p className="progress-error">Something went wrong: {error}</p>}
    </div>
  );
}


















// export default function ProgressStream({ lines, error }) {
//   return (
//     <div className="progress-stream">
//       <h2>Building your learning path</h2>
//       <ul className="progress-lines">
//         {lines.map((line, i) => (
//           <li key={i}>{line}</li>
//         ))}
//         {lines.length === 0 && !error && <li className="progress-waiting">Starting…</li>}
//       </ul>
//       {error && <p className="progress-error">Something went wrong: {error}</p>}
//     </div>
//   );
// }
