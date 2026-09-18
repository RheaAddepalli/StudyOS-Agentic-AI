import { useEffect, useState } from "react";
import { getPractice, restartPractice } from "./api";
import PracticePanel from "./PracticePanel";

export default function PracticeSection({ learnerId, pathName, conceptId, onAdvance, onClose }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [choiceMade, setChoiceMade] = useState(false);
  const [justCompleted, setJustCompleted] = useState(null);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [learnerId, pathName, conceptId]);

  function load() {
    setState({ loading: true, data: null, error: null });
    setChoiceMade(false);
    setJustCompleted(null);
    getPractice(learnerId, pathName, conceptId)
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => setState({ loading: false, data: null, error: err.message }));
  }

  async function handleStartOver() {
    setState((s) => ({ ...s, loading: true }));
    try {
      await restartPractice(learnerId, pathName, conceptId);
      load();
    } catch (err) {
      setState({ loading: false, data: null, error: err.message });
    }
  }

  function handleStageComplete(result) {
    onAdvance();
    if (result.advanced) {
      setJustCompleted({ mastery: result.mastery });
    } else {
      load();
    }
  }

  return (
    <div className="practice-section">
      <div className="practice-section-header">
        <h2>Practice — {conceptId.replace(/-/g, " ")}</h2>
        <button className="link-button" onClick={onClose}>
          close
        </button>
      </div>

      {state.loading && <p className="practice-loading">Loading practice…</p>}
      {state.error && <p className="practice-error">{state.error}</p>}

      {justCompleted && (
        <p className="dashboard-complete">
          Nice work — this concept is now <strong>{justCompleted.mastery}</strong>. Pick another
          topic's Practice button to keep going, or close this.
        </p>
      )}

      {!state.loading && !state.error && state.data && (
        <>
          {state.data.results.length > 0 && !choiceMade && !justCompleted ? (
            <div className="practice-resume-choice">
              <p>
                You've answered {state.data.results.length} of {state.data.items.length} questions for
                this concept already.
              </p>
              <div className="form-actions">
                <button className="btn" onClick={() => setChoiceMade(true)}>
                  Continue
                </button>
                <button className="btn btn-secondary" onClick={handleStartOver}>
                  Start over
                </button>
              </div>
            </div>
          ) : (
            <PracticePanel
              learnerId={learnerId}
              pathName={pathName}
              conceptId={conceptId}
              items={state.data.items}
              initialResults={state.data.results}
              onStageComplete={handleStageComplete}
            />
          )}
        </>
      )}
    </div>
  );
}