import { useState } from "react";
import { submitAnswer } from "./api";

const TYPE_LABELS = {
  quiz: "Quiz",
  conceptual_question: "Conceptual",
  coding_exercise: "Coding exercise",
  implementation_task: "Implementation",
  project: "Project",
  revision: "Revision",
};

export default function PracticePanel({ learnerId, pathName, conceptId, items, initialResults, onStageComplete }) {
  const [results, setResults] = useState(initialResults || []);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const answeredIds = new Set(results.map((r) => r.practice_item_id));
  const currentItem = items.find((item) => !answeredIds.has(item.id));
  const currentIndex = results.length + 1;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!currentItem || !answer.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitAnswer(learnerId, pathName, conceptId, currentItem.id, answer);
      setResults((prev) => [
        ...prev,
        {
          practice_item_id: currentItem.id,
          score: result.score,
          feedback: result.feedback,
        },
      ]);
      setAnswer("");
      if (result.stage_complete) {
        onStageComplete(result);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="practice-panel">
      {results.map((r) => {
        const item = items.find((i) => i.id === r.practice_item_id);
        return (
          <div className="practice-item practice-item-done" key={r.practice_item_id}>
            <div className="practice-item-type">{TYPE_LABELS[item?.type] || item?.type}</div>
            <p className="practice-prompt">{item?.prompt}</p>
            <p className="practice-score">
              {r.score}/10 — {r.feedback}
            </p>
          </div>
        );
      })}

      {currentItem && (
        <form className="practice-item practice-item-active" onSubmit={handleSubmit}>
          <div className="practice-item-type">
            {TYPE_LABELS[currentItem.type] || currentItem.type}
            <span className="practice-item-counter"> · Question {currentIndex} of {items.length}</span>
          </div>
          <p className="practice-prompt">{currentItem.prompt}</p>
          {currentItem.starter_code && (
            <pre className="practice-starter-code">{currentItem.starter_code}</pre>
          )}
          <textarea
            className="field practice-answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={currentItem.type === "coding_exercise" ? 6 : 3}
            placeholder="Your answer"
            disabled={submitting}
            autoFocus
          />
          <button className="btn" type="submit" disabled={submitting || !answer.trim()}>
            {submitting ? "Grading…" : "Submit"}
          </button>
          {error && <p className="practice-error">{error}</p>}
        </form>
      )}
    </div>
  );
}





































// 7 sep
// import { useState } from "react";
// import { submitAnswer } from "./api";

// const TYPE_LABELS = {
//   quiz: "Quiz",
//   conceptual_question: "Conceptual",
//   coding_exercise: "Coding exercise",
//   implementation_task: "Implementation",
//   project: "Project",
//   revision: "Revision",
// };

// export default function PracticePanel({ learnerId, pathName, conceptId, items, initialResults, onStageComplete }) {
//   const [results, setResults] = useState(initialResults || []);
//   const [answer, setAnswer] = useState("");
//   const [submitting, setSubmitting] = useState(false);
//   const [error, setError] = useState(null);

//   const answeredIds = new Set(results.map((r) => r.practice_item_id));
//   const currentItem = items.find((item) => !answeredIds.has(item.id));

//   async function handleSubmit(e) {
//     e.preventDefault();
//     if (!currentItem || !answer.trim() || submitting) return;
//     setSubmitting(true);
//     setError(null);
//     try {
//       const result = await submitAnswer(learnerId, pathName, currentItem.id, answer);
//       setResults((prev) => [
//         ...prev,
//         {
//           practice_item_id: currentItem.id,
//           score: result.score,
//           feedback: result.feedback,
//         },
//       ]);
//       setAnswer("");
//       if (result.stage_complete) {
//         onStageComplete(result);
//       }
//     } catch (err) {
//       setError(err.message);
//     } finally {
//       setSubmitting(false);
//     }
//   }

//   return (
//     <div className="practice-panel">
//       {results.map((r) => {
//         const item = items.find((i) => i.id === r.practice_item_id);
//         return (
//           <div className="practice-item practice-item-done" key={r.practice_item_id}>
//             <div className="practice-item-type">{TYPE_LABELS[item?.type] || item?.type}</div>
//             <p className="practice-prompt">{item?.prompt}</p>
//             <p className="practice-score">
//               {r.score}/10 — {r.feedback}
//             </p>
//           </div>
//         );
//       })}

//       {currentItem && (
//         <form className="practice-item practice-item-active" onSubmit={handleSubmit}>
//           <div className="practice-item-type">{TYPE_LABELS[currentItem.type] || currentItem.type}</div>
//           <p className="practice-prompt">{currentItem.prompt}</p>
//           {currentItem.starter_code && (
//             <pre className="practice-starter-code">{currentItem.starter_code}</pre>
//           )}
//           <textarea
//             className="field practice-answer"
//             value={answer}
//             onChange={(e) => setAnswer(e.target.value)}
//             rows={currentItem.type === "coding_exercise" ? 6 : 3}
//             placeholder="Your answer"
//             disabled={submitting}
//             autoFocus
//           />
//           <button className="btn" type="submit" disabled={submitting || !answer.trim()}>
//             {submitting ? "Grading…" : "Submit"}
//           </button>
//           {error && <p className="practice-error">{error}</p>}
//         </form>
//       )}
//     </div>
//   );
// }
