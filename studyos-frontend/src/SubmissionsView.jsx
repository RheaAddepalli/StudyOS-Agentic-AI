import { useEffect, useState } from "react";
import { getSubmissions } from "./api";

const TYPE_LABELS = {
  quiz: "Quiz",
  conceptual_question: "Conceptual",
  coding_exercise: "Coding exercise",
  implementation_task: "Implementation",
  project: "Project",
  revision: "Revision",
};

export default function SubmissionsView({ learnerId, pathName, conceptId, onClose }) {
  const [state, setState] = useState({ loading: true, records: null, error: null });

  useEffect(() => {
    getSubmissions(learnerId, pathName, conceptId)
      .then((records) => setState({ loading: false, records, error: null }))
      .catch((err) => setState({ loading: false, records: null, error: err.message }));
  }, [learnerId, pathName, conceptId]);

  return (
    <div className="submissions-view">
      <div className="practice-section-header">
        <h3>Submissions — {conceptId.replace(/-/g, " ")}</h3>
        <button className="link-button" onClick={onClose}>
          close
        </button>
      </div>

      {state.loading && <p className="practice-loading">Loading…</p>}
      {state.error && <p className="practice-error">{state.error}</p>}

      {state.records && state.records.length === 0 && (
        <p className="paths-empty">Nothing answered here yet.</p>
      )}

      {state.records &&
        state.records.map((r, i) => (
          <div className="practice-item practice-item-done" key={i}>
            <div className="practice-item-type">{TYPE_LABELS[r.type] || r.type}</div>
            <p className="practice-prompt">{r.prompt}</p>
            <p className="submission-answer">Your answer: {r.answer}</p>
            <p className="practice-score">
              {r.score}/10 — {r.feedback}
            </p>
          </div>
        ))}
    </div>
  );
}




















// 7 sep
// import { useEffect, useState } from "react";
// import { getSubmissions } from "./api";

// const TYPE_LABELS = {
//   quiz: "Quiz",
//   conceptual_question: "Conceptual",
//   coding_exercise: "Coding exercise",
//   implementation_task: "Implementation",
//   project: "Project",
//   revision: "Revision",
// };

// export default function SubmissionsView({ learnerId, pathName, conceptId, onClose }) {
//   const [state, setState] = useState({ loading: true, records: null, error: null });

//   useEffect(() => {
//     getSubmissions(learnerId, pathName, conceptId)
//       .then((records) => setState({ loading: false, records, error: null }))
//       .catch((err) => setState({ loading: false, records: null, error: err.message }));
//   }, [learnerId, pathName, conceptId]);

//   return (
//     <div className="submissions-view">
//       <div className="practice-section-header">
//         <h3>Submissions — {conceptId.replace(/-/g, " ")}</h3>
//         <button className="link-button" onClick={onClose}>
//           close
//         </button>
//       </div>

//       {state.loading && <p className="practice-loading">Loading…</p>}
//       {state.error && <p className="practice-error">{state.error}</p>}

//       {state.records && state.records.length === 0 && (
//         <p className="paths-empty">Nothing answered here yet.</p>
//       )}

//       {state.records &&
//         state.records.map((r, i) => (
//           <div className="practice-item practice-item-done" key={i}>
//             <div className="practice-item-type">{TYPE_LABELS[r.type] || r.type}</div>
//             <p className="practice-prompt">{r.prompt}</p>
//             <p className="submission-answer">Your answer: {r.answer}</p>
//             <p className="practice-score">
//               {r.score}/10 — {r.feedback}
//             </p>
//           </div>
//         ))}
//     </div>
//   );
// }