import { useState } from "react";
import SubmissionsView from "./SubmissionsView";
import PracticeSection from "./PracticeSection";

const MASTERY_LABEL = {
  not_started: "Not started",
  developing: "Developing",
  proficient: "Proficient",
  mastered: "Mastered",
};

function ResourceLink({ resource, roleLabel }) {
  return (
    <div className="resource-line">
      <span className="resource-role">{roleLabel}</span>
      <a href={resource.url} target="_blank" rel="noreferrer">
        {resource.title}
      </a>
      {resource.justification && <span className="resource-why"> — {resource.justification}</span>}
    </div>
  );
}

export default function StageRow({ stage, isLast, learnerId, pathName, onRefresh }) {
  const [showSubmissions, setShowSubmissions] = useState(false);
  const [practiceOpen, setPracticeOpen] = useState(false);
  const dotClass = `stage-dot stage-dot-${stage.mastery}`;
  const label = stage.in_progress ? "In progress" : MASTERY_LABEL[stage.mastery];

  return (
    <div className="stage-row">
      <div className="stage-line">
        <span className={dotClass} />
        {!isLast && <span className="stage-connector" />}
      </div>

      <div className="stage-body">
        <div className="stage-header">
          <h3 className="stage-title">{stage.concept_id.replace(/-/g, " ")}</h3>
          <div className="stage-header-right">
            <span className="stage-meta">
              {label}
              {stage.best_score != null && ` · best ${stage.best_score}/10`}
            </span>
            <button className="btn btn-secondary stage-practice-btn" onClick={() => setPracticeOpen((v) => !v)}>
              {practiceOpen ? "hide practice" : "Practice"}
            </button>
          </div>
        </div>
        <p className="stage-reason">{stage.reason}</p>

        {stage.primary_resource && <ResourceLink resource={stage.primary_resource} roleLabel="primary" />}
        {stage.alternative_resources.map((r) => (
          <ResourceLink key={r.url} resource={r} roleLabel="alternative" />
        ))}
        {stage.reference_resources.map((r) => (
          <ResourceLink key={r.url} resource={r} roleLabel="reference" />
        ))}

        {stage.has_submissions && (
          <button className="link-button submissions-toggle" onClick={() => setShowSubmissions((s) => !s)}>
            {showSubmissions ? "hide submissions" : "view submissions"}
          </button>
        )}
        {showSubmissions && (
          <SubmissionsView
            learnerId={learnerId}
            pathName={pathName}
            conceptId={stage.concept_id}
            onClose={() => setShowSubmissions(false)}
          />
        )}

        {practiceOpen && (
          <PracticeSection
            learnerId={learnerId}
            pathName={pathName}
            conceptId={stage.concept_id}
            onAdvance={onRefresh}
            onClose={() => setPracticeOpen(false)}
          />
        )}
      </div>
    </div>
  );
}







// 7 sep
// import PracticePanel from "./PracticePanel";

// const MASTERY_LABEL = {
//   not_started: "Not started",
//   developing: "Developing",
//   proficient: "Proficient",
//   mastered: "Mastered",
// };

// function ResourceLink({ resource, roleLabel }) {
//   return (
//     <div className="resource-line">
//       <span className="resource-role">{roleLabel}</span>
//       <a href={resource.url} target="_blank" rel="noreferrer">
//         {resource.title}
//       </a>
//       {resource.justification && <span className="resource-why"> — {resource.justification}</span>}
//     </div>
//   );
// }

// export default function StageRow({
//   stage,
//   isLast,
//   practiceState,
//   learnerId,
//   pathName,
//   onStageComplete,
// }) {
//   const dotClass = `stage-dot stage-dot-${stage.mastery}`;

//   return (
//     <div className="stage-row">
//       <div className="stage-line">
//         <span className={dotClass} />
//         {!isLast && <span className="stage-connector" />}
//       </div>

//       <div className="stage-body">
//         <div className="stage-header">
//           <h3 className="stage-title">{stage.concept_id.replace(/-/g, " ")}</h3>
//           <span className="stage-meta">
//             {MASTERY_LABEL[stage.mastery]} · ~{stage.estimated_minutes} min
//           </span>
//         </div>
//         <p className="stage-reason">{stage.reason}</p>

//         {stage.primary_resource && <ResourceLink resource={stage.primary_resource} roleLabel="primary" />}
//         {stage.alternative_resources.map((r) => (
//           <ResourceLink key={r.url} resource={r} roleLabel="alternative" />
//         ))}
//         {stage.reference_resources.map((r) => (
//           <ResourceLink key={r.url} resource={r} roleLabel="reference" />
//         ))}

//         {stage.is_current && (
//           <div className="stage-practice">
//             {practiceState.loading && <p className="practice-loading">Loading practice…</p>}
//             {practiceState.error && <p className="practice-error">{practiceState.error}</p>}
//             {practiceState.items && (
//               <PracticePanel
//                 learnerId={learnerId}
//                 pathName={pathName}
//                 conceptId={stage.concept_id}
//                 items={practiceState.items}
//                 initialResults={practiceState.results}
//                 onStageComplete={onStageComplete}
//               />
//             )}
//           </div>
//         )}
//       </div>
//     </div>
//   );
// }
