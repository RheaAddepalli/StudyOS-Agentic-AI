import { useState } from "react";

export default function NewPathForm({ onSubmit, onCancel, disabled, existingNames = [] }) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [nameError, setNameError] = useState(null);

  function handleSubmit(e) {
    e.preventDefault();
    const trimmedName = name.trim().toLowerCase();
    const trimmedText = text.trim();
    if (!trimmedName || !trimmedText) return;
    if (existingNames.includes(trimmedName)) {
      setNameError(`You already have a path called "${trimmedName}" — pick a different name.`);
      return;
    }
    setNameError(null);
    onSubmit(trimmedName, trimmedText);
  }

  return (
    <form onSubmit={handleSubmit} className="goal-form">
      <h2>Start a new topic</h2>
      <p className="goal-hint">
        Give it a short name so you can find it again later, and say what you
        want to learn — as much or as little as you know already.
      </p>

      <label className="field-label" htmlFor="path-name">
        Name
      </label>
      <input
        id="path-name"
        className="field"
        value={name}
        onChange={(e) => {
          setName(e.target.value);
          setNameError(null);
        }}
        placeholder="e.g. python, transformers"
        disabled={disabled}
        autoFocus
      />
      {nameError && <p className="practice-error">{nameError}</p>}

      <label className="field-label" htmlFor="path-goal">
        Goal
      </label>
      <textarea
        id="path-goal"
        className="field goal-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="I want to learn..."
        rows={4}
        disabled={disabled}
      />

      <div className="form-actions">
        <button className="btn" type="submit" disabled={disabled || !name.trim() || !text.trim()}>
          Build this learning path
        </button>
        {onCancel && (
          <button className="btn btn-secondary" type="button" onClick={onCancel} disabled={disabled}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}