import { useState } from "react";

export default function GoalForm({ onSubmit, disabled }) {
  const [text, setText] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (trimmed) onSubmit(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} className="goal-form">
      <h2>What do you want to learn?</h2>
      <p className="goal-hint">
        Say as much or as little as you know — what you already know, how much
        time you have, how deep you want to go. Try: "I know Python and basic
        neural nets, want to understand Transformers deeply, 1 hour a day."
      </p>
      <textarea
        className="field goal-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="I want to learn..."
        rows={4}
        disabled={disabled}
        autoFocus
      />
      <button className="btn" type="submit" disabled={disabled || !text.trim()}>
        Build my learning path
      </button>
    </form>
  );
}
