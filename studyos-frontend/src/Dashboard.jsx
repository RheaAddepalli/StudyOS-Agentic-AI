import StageRow from "./StageRow";

export default function Dashboard({ learnerId, pathName, summary, onRefresh, onBack }) {
  const currentStage = summary.stages.find((s) => s.is_current);
  const allDone = summary.stages.length > 0 && !currentStage;

  return (
    <div className="dashboard">
      <button className="link-button back-link" onClick={onBack}>
        ← all topics
      </button>
      <header className="dashboard-header">
        <h1>{pathName}</h1>
        <p className="dashboard-goal">{summary.goal_text}</p>
      </header>

      {allDone && (
        <p className="dashboard-complete">
          Every concept in this path is mastered or proficient. Nice work.
        </p>
      )}

      {!allDone && (
        <p className="dashboard-note">
          Progress only updates when you complete a practice round — opening a resource
          link doesn't count, since there's no way to detect that. Each topic below has its
          own Practice button, independent of the others.
        </p>
      )}

      <div className="stage-timeline">
        {summary.stages.map((stage, i) => (
          <StageRow
            key={stage.concept_id}
            stage={stage}
            isLast={i === summary.stages.length - 1}
            learnerId={learnerId}
            pathName={pathName}
            onRefresh={onRefresh}
          />
        ))}
      </div>
    </div>
  );
}





//7 sep
//  import { useEffect, useState } from "react";
// import { getPractice } from "./api";
// import StageRow from "./StageRow";

// export default function Dashboard({ learnerId, pathName, summary, onRefresh, onBack }) {
//   const [practiceState, setPracticeState] = useState({ loading: false, items: null, results: [], error: null });
//   const currentStage = summary.stages.find((s) => s.is_current);
//   const allDone = summary.stages.length > 0 && !currentStage;

//   useEffect(() => {
//     if (!currentStage) return;
//     let cancelled = false;
//     setPracticeState({ loading: true, items: null, results: [], error: null });
//     getPractice(learnerId, pathName)
//       .then((data) => {
//         if (cancelled) return;
//         if (data.done) {
//           setPracticeState({ loading: false, items: null, results: [], error: null });
//           onRefresh();
//           return;
//         }
//         setPracticeState({ loading: false, items: data.items, results: data.results, error: null });
//       })
//       .catch((err) => {
//         if (!cancelled) setPracticeState({ loading: false, items: null, results: [], error: err.message });
//       });
//     return () => {
//       cancelled = true;
//     };
//     // Re-fetch whenever the current concept changes (i.e. after advancing/remediating).
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, [learnerId, pathName, currentStage?.concept_id]);

//   function handleStageComplete() {
//     // The stage moved on (advanced or a fresh remediation round started) —
//     // pull the latest summary from the server rather than guess locally.
//     onRefresh();
//   }

//   return (
//     <div className="dashboard">
//       <button className="link-button back-link" onClick={onBack}>
//         ← all topics
//       </button>
//       <header className="dashboard-header">
//         <h1>{pathName}</h1>
//         <p className="dashboard-goal">{summary.goal_text}</p>
//       </header>

//       {allDone && (
//         <p className="dashboard-complete">
//           Every concept in this path is mastered or proficient. Nice work.
//         </p>
//       )}

//       <div className="stage-timeline">
//         {summary.stages.map((stage, i) => (
//           <StageRow
//             key={stage.concept_id}
//             stage={stage}
//             isLast={i === summary.stages.length - 1}
//             learnerId={learnerId}
//             pathName={pathName}
//             practiceState={stage.is_current ? practiceState : {}}
//             onStageComplete={handleStageComplete}
//           />
//         ))}
//       </div>
//     </div>
//   );
// }























// import { useEffect, useState } from "react";
// import { getPractice } from "./api";
// import StageRow from "./StageRow";

// export default function Dashboard({ learnerId, summary, onRefresh }) {
//   const [practiceState, setPracticeState] = useState({ loading: false, items: null, results: [], error: null });
//   const currentStage = summary.stages.find((s) => s.is_current);
//   const allDone = summary.stages.length > 0 && !currentStage;

//   useEffect(() => {
//     if (!currentStage) return;
//     let cancelled = false;
//     setPracticeState({ loading: true, items: null, results: [], error: null });
//     getPractice(learnerId)
//       .then((data) => {
//         if (cancelled) return;
//         if (data.done) {
//           setPracticeState({ loading: false, items: null, results: [], error: null });
//           onRefresh();
//           return;
//         }
//         setPracticeState({ loading: false, items: data.items, results: data.results, error: null });
//       })
//       .catch((err) => {
//         if (!cancelled) setPracticeState({ loading: false, items: null, results: [], error: err.message });
//       });
//     return () => {
//       cancelled = true;
//     };
//     // Re-fetch whenever the current concept changes (i.e. after advancing/remediating).
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, [learnerId, currentStage?.concept_id]);

//   function handleStageComplete() {
//     // The stage moved on (advanced or a fresh remediation round started) —
//     // pull the latest summary from the server rather than guess locally.
//     onRefresh();
//   }

//   return (
//     <div className="dashboard">
//       <header className="dashboard-header">
//         <h1>Your learning path</h1>
//         <p className="dashboard-goal">{summary.goal_text}</p>
//       </header>

//       {allDone && (
//         <p className="dashboard-complete">
//           Every concept in this path is mastered or proficient. Nice work.
//         </p>
//       )}

//       <div className="stage-timeline">
//         {summary.stages.map((stage, i) => (
//           <StageRow
//             key={stage.concept_id}
//             stage={stage}
//             isLast={i === summary.stages.length - 1}
//             learnerId={learnerId}
//             practiceState={stage.is_current ? practiceState : {}}
//             onStageComplete={handleStageComplete}
//           />
//         ))}
//       </div>
//     </div>
//   );
// }
