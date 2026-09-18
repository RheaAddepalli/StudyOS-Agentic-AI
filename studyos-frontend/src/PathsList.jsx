export default function PathsList({ paths, onOpen, onStartNew }) {
  return (
    <div className="paths-list">
      <header className="paths-header">
        <h1>Your topics</h1>
        <p className="paths-sub">
          Each topic is a separate, independent learning path — work through
          several at once without them interfering with each other.
        </p>
      </header>

      {paths.length === 0 && (
        <p className="paths-empty">You haven't started any topics yet.</p>
      )}

      <div className="path-cards">
        {paths.map((p) => (
          <div className="path-card" key={p.path_name}>
            <div className="path-card-main">
              <h3 className="path-card-name">{p.path_name}</h3>
              {p.goal_text && <p className="path-card-goal">{p.goal_text}</p>}
              {p.total_stages > 0 && (
                <p className="path-card-progress">
                  {p.mastered_or_proficient}/{p.total_stages} concepts mastered or proficient
                  {p.is_complete ? " · complete" : ""}
                </p>
              )}
            </div>
            <button className="btn" onClick={() => onOpen(p.path_name)}>
              {p.is_complete ? "Review" : "Continue"}
            </button>
          </div>
        ))}
      </div>

      <button className="btn btn-secondary new-topic-btn" onClick={onStartNew}>
        + New topic
      </button>
    </div>
  );
}