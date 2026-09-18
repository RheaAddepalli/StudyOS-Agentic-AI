import { useEffect, useState } from "react";
import LearnerGate from "./LearnerGate";
import NewPathForm from "./NewPathForm";
import ProgressStream from "./ProgressStream";
import PathsList from "./PathsList";
import Dashboard from "./Dashboard";
import { listPaths, getPath, streamGoal } from "./api";

const STORAGE_KEY = "studyos.learnerId";

export default function App() {
  const [learnerId, setLearnerId] = useState(() => localStorage.getItem(STORAGE_KEY));
  const [paths, setPaths] = useState(null);
  const [pathsError, setPathsError] = useState(null);

  const [creatingNew, setCreatingNew] = useState(false);
  const [activePathName, setActivePathName] = useState(null);
  const [pathDetail, setPathDetail] = useState(null);

  const [progressLines, setProgressLines] = useState([]);
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState(null);
  const [buildingPathName, setBuildingPathName] = useState(null);

  useEffect(() => {
    if (!learnerId) return;
    refreshPaths();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [learnerId]);

  useEffect(() => {
    if (!activePathName) return;
    refreshPathDetail(activePathName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [learnerId, activePathName]);

  function refreshPaths() {
    setPathsError(null);
    listPaths(learnerId)
      .then(setPaths)
      .catch((err) => setPathsError(err.message));
  }

  function refreshPathDetail(pathName) {
    getPath(learnerId, pathName)
      .then(setPathDetail)
      .catch((err) => setPathsError(err.message));
  }

  function handleEnter(name) {
    localStorage.setItem(STORAGE_KEY, name);
    setLearnerId(name);
  }

  function handleSwitchLearner() {
    localStorage.removeItem(STORAGE_KEY);
    setLearnerId(null);
    setPaths(null);
    setActivePathName(null);
    setPathDetail(null);
  }

  function handleStartNew() {
    setCreatingNew(true);
  }

  function handleCancelNew() {
    setCreatingNew(false);
  }

  function handleOpenPath(pathName) {
    setActivePathName(pathName);
  }

  function handleBackToPaths() {
    setActivePathName(null);
    setPathDetail(null);
    refreshPaths();
  }

  function handleNewPathSubmit(pathName, rawRequest) {
    setCreatingNew(false);
    setBuilding(true);
    setBuildError(null);
    setBuildingPathName(pathName);
    setProgressLines([]);
    streamGoal(learnerId, pathName, rawRequest, {
      onProgress: (line) => setProgressLines((prev) => [...prev, line]),
      onDone: () => {
        setBuilding(false);
        refreshPaths();
        setActivePathName(pathName); // continuation, not back to the list
      },
      onError: (msg) => {
        setBuilding(false);
        setBuildError(msg);
      },
    });
  }

  if (!learnerId) {
    return <LearnerGate onEnter={handleEnter} />;
  }

  const existingNames = paths ? paths.map((p) => p.path_name) : [];

  return (
    <div className="app-shell">
      <nav className="topbar">
        <span className="topbar-brand">StudyOS</span>
        <span className="topbar-learner">
          {learnerId} · <button className="link-button" onClick={handleSwitchLearner}>switch</button>
        </span>
      </nav>

      <main className="app-main">
        {pathsError && <p className="load-error">{pathsError}</p>}

        {building && <ProgressStream lines={progressLines} error={buildError} />}

        {!building && buildError && (
          <div>
            <p className="progress-error">Something went wrong: {buildError}</p>
            <button className="btn" onClick={() => setBuildError(null)}>
              Back to topics
            </button>
          </div>
        )}

        {!building && !buildError && creatingNew && (
          <NewPathForm
            onSubmit={handleNewPathSubmit}
            onCancel={paths && paths.length > 0 ? handleCancelNew : undefined}
            existingNames={existingNames}
          />
        )}

        {!building && !buildError && !creatingNew && activePathName && pathDetail && (
          <Dashboard
            learnerId={learnerId}
            pathName={activePathName}
            summary={pathDetail}
            onRefresh={() => refreshPathDetail(activePathName)}
            onBack={handleBackToPaths}
          />
        )}

        {!building && !buildError && !creatingNew && !activePathName && paths && (
          <PathsList paths={paths} onOpen={handleOpenPath} onStartNew={handleStartNew} />
        )}
      </main>
    </div>
  );
}