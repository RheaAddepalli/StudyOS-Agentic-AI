import { useState } from "react";

export default function LearnerGate({ onEnter }) {
  const [name, setName] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed) onEnter(trimmed);
  }

  return (
    <div className="gate">
      <h1>StudyOS</h1>
      <p className="gate-sub">
        A learning path built around whatever you're trying to learn — not a fixed
        roadmap. Enter a name to start or come back to your plan.
      </p>
      <form onSubmit={handleSubmit} className="gate-form">
        <input
          className="field"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="your name"
          autoFocus
        />
        <button className="btn" type="submit" disabled={!name.trim()}>
          Continue
        </button>
      </form>
    </div>
  );
}
