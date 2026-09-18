const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const resp = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${resp.status}`);
  }
  return resp.json();
}

export function listPaths(learnerId) {
  return request(`/learners/${encodeURIComponent(learnerId)}/paths`);
}

export function getPath(learnerId, pathName) {
  return request(`/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}`);
}

export function getPractice(learnerId, pathName, conceptId) {
  return request(
    `/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}/concepts/${encodeURIComponent(
      conceptId
    )}/practice`
  );
}

export function submitAnswer(learnerId, pathName, conceptId, itemId, answer) {
  return request(
    `/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}/concepts/${encodeURIComponent(
      conceptId
    )}/practice/${encodeURIComponent(itemId)}/answer`,
    { method: "POST", body: JSON.stringify({ answer }) }
  );
}

export function restartPractice(learnerId, pathName, conceptId) {
  return request(
    `/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}/concepts/${encodeURIComponent(
      conceptId
    )}/practice/restart`,
    { method: "POST" }
  );
}

export function getSubmissions(learnerId, pathName, conceptId) {
  return request(
    `/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}/concepts/${encodeURIComponent(
      conceptId
    )}/submissions`
  );
}

export function streamGoal(learnerId, pathName, rawRequest, { onProgress, onDone, onError }) {
  const url = `${BASE_URL}/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(
    pathName
  )}/goal/stream?raw_request=${encodeURIComponent(rawRequest)}`;
  const source = new EventSource(url);

  source.addEventListener("progress", (e) => onProgress?.(e.data));
  source.addEventListener("done", () => {
    onDone?.();
    source.close();
  });
  source.addEventListener("error", (e) => {
    onError?.(e.data || "Connection to the server was lost.");
    source.close();
  });

  return { close: () => source.close() };
}



// 7 sep
// const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// async function request(path, options = {}) {
//   const resp = await fetch(`${BASE_URL}${path}`, {
//     headers: { "Content-Type": "application/json" },
//     ...options,
//   });
//   if (!resp.ok) {
//     const body = await resp.json().catch(() => ({}));
//     throw new Error(body.detail || `Request failed: ${resp.status}`);
//   }
//   return resp.json();
// }

// export function listPaths(learnerId) {
//   return request(`/learners/${encodeURIComponent(learnerId)}/paths`);
// }

// export function getPath(learnerId, pathName) {
//   return request(`/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}`);
// }

// export function getPractice(learnerId, pathName) {
//   return request(
//     `/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}/practice`
//   );
// }

// export function submitAnswer(learnerId, pathName, itemId, answer) {
//   return request(
//     `/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(pathName)}/practice/${encodeURIComponent(
//       itemId
//     )}/answer`,
//     { method: "POST", body: JSON.stringify({ answer }) }
//   );
// }

// /**
//  * Streams curriculum-generation progress via SSE for a brand-new path.
//  * Returns an object with a `close()` method so the caller can tear down the
//  * connection if the user navigates away mid-stream.
//  */
// export function streamGoal(learnerId, pathName, rawRequest, { onProgress, onDone, onError }) {
//   const url = `${BASE_URL}/learners/${encodeURIComponent(learnerId)}/paths/${encodeURIComponent(
//     pathName
//   )}/goal/stream?raw_request=${encodeURIComponent(rawRequest)}`;
//   const source = new EventSource(url);

//   source.addEventListener("progress", (e) => onProgress?.(e.data));
//   source.addEventListener("done", () => {
//     onDone?.();
//     source.close();
//   });
//   source.addEventListener("error", (e) => {
//     // Browser EventSource fires a generic "error" event both for our custom
//     // server-sent "error" events AND for connection drops — data is only
//     // present in the former case.
//     onError?.(e.data || "Connection to the server was lost.");
//     source.close();
//   });

//   return { close: () => source.close() };
// }












// const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// async function request(path, options = {}) {
//   const resp = await fetch(`${BASE_URL}${path}`, {
//     headers: { "Content-Type": "application/json" },
//     ...options,
//   });
//   if (!resp.ok) {
//     const body = await resp.json().catch(() => ({}));
//     throw new Error(body.detail || `Request failed: ${resp.status}`);
//   }
//   return resp.json();
// }

// export function getLearner(learnerId) {
//   return request(`/learners/${encodeURIComponent(learnerId)}`);
// }

// export function getPractice(learnerId) {
//   return request(`/learners/${encodeURIComponent(learnerId)}/practice`);
// }

// export function submitAnswer(learnerId, itemId, answer) {
//   return request(
//     `/learners/${encodeURIComponent(learnerId)}/practice/${encodeURIComponent(itemId)}/answer`,
//     { method: "POST", body: JSON.stringify({ answer }) }
//   );
// }

// /**
//  * Streams curriculum-generation progress via SSE. Returns an object with a
//  * `close()` method so the caller can tear down the connection if the user
//  * navigates away mid-stream.
//  */
// export function streamGoal(learnerId, rawRequest, { onProgress, onDone, onError }) {
//   const url = `${BASE_URL}/learners/${encodeURIComponent(learnerId)}/goal/stream?raw_request=${encodeURIComponent(
//     rawRequest
//   )}`;
//   const source = new EventSource(url);

//   source.addEventListener("progress", (e) => onProgress?.(e.data));
//   source.addEventListener("done", () => {
//     onDone?.();
//     source.close();
//   });
//   source.addEventListener("error", (e) => {
//     // Browser EventSource fires a generic "error" event both for our custom
//     // server-sent "error" events AND for connection drops — data is only
//     // present in the former case.
//     onError?.(e.data || "Connection to the server was lost.");
//     source.close();
//   });

//   return { close: () => source.close() };
// }
