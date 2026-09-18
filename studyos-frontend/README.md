# StudyOS frontend

React (Vite) app for the StudyOS learning agent. Talks to the FastAPI backend
in the `studyos` repo — this is a separate deploy, not bundled into it.

No login: a learner is just a name typed once and stored in the browser
(`localStorage`). Every request sends that name to the backend, which uses it
as the key for that learner's saved state.

## Local development

```bash
npm install
cp .env.example .env    # point VITE_API_URL at your local backend
npm run dev
```

Runs on `http://localhost:5173` by default. Requires the backend running
(see the main repo's README) with `ALLOWED_ORIGINS` including
`http://localhost:5173`.

## Tests

```bash
npm test
```

Component tests with the API layer mocked (`vitest` + `@testing-library/react`,
jsdom — no real browser needed). These caught real prop-wiring bugs during
development (a `submitAnswer` call-signature mismatch, `Dashboard` →
`StageRow` → `PracticePanel` state flow), not just "does it render."

## Deploying to Render

1. Push this frontend to its own Git repo (or a subdirectory of one).
2. In Render: **New → Static Site**, point it at the repo.
3. Build command: `npm install && npm run build`
4. Publish directory: `dist`
5. Add an environment variable: `VITE_API_URL` = your deployed backend's URL
   (e.g. `https://studyos-api.onrender.com`).
6. Deploy. Static sites are genuinely free on Render — no expiry, unlike
   Render's free Postgres.

**Don't forget**: once you have the frontend's Render URL, add it to the
backend's `ALLOWED_ORIGINS` env var (comma-separated if there's more than
one), or the browser will block every request with a CORS error.
