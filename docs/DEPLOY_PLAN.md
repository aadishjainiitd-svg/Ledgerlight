# Deployment plan: Render (backend) + Vercel (frontend), one sandbox per visitor

**Goal:** a public link the hiring panel can open, run every sample and edge case on, and reset, without ever
seeing another visitor's data. The same link is used in the 5-minute video and the live interview.

## Decisions (made 17 Nov 2026)

| | Choice | Why |
|---|---|---|
| Backend | Render free web service (Python), deployed from GitHub | Free, runs FastAPI as is. It sleeps after 15 min idle: open the link a minute before any demo. |
| Frontend | Vercel (Next.js), deployed from GitHub | Free, builds Next.js natively. `NEXT_PUBLIC_API_BASE` points at the Render URL. |
| Data | **One sandbox per visitor** | Samples always behave as designed, and reset only affects that visitor. |
| AI key | `GROQ_API_KEY` as a Render environment variable | Never in the repo. Use a **new** key; revoke the one pasted in chat. |

## What you do (accounts and secrets: about 15 minutes)

1. **GitHub:** create an empty **private** repository (e.g. `ledgerlight`) and send me its URL. Make it public later
   only if you want the panel to read the code.
2. **Groq:** create a new API key in the Groq console and revoke the old one. Paste the key into Render yourself
   (step 4); never into chat.
3. **Render:** sign up with GitHub, then **New → Web Service** on the repo. I will give you the exact settings
   (root `backend`, build and start commands, region) in a `render.yaml`, so this is a few clicks.
4. **Render environment:** add `GROQ_API_KEY` (your new key). The other variables come from `render.yaml`.
5. **Vercel:** sign up with GitHub, **Add New → Project** on the repo, root directory `frontend`, and set
   `NEXT_PUBLIC_API_BASE` to the Render URL.

## What I build (code, in this repo)

**A. Per-visitor sandboxes (backend)**
- On the first request without a sandbox id, the backend makes one: a random id, returned to the browser and
  sent on every later request (a header the frontend adds, so it also works across the Vercel and Render
  domains).
- Each sandbox gets its own SQLite file, copied from a pre-seeded template that is built once at startup. A
  new visitor is ready in under a second, with no re-seeding.
- Every database access, including background runs and the live run stream, uses the visitor's sandbox.
- Demo reset re-copies the template for that visitor only.
- Housekeeping: sandboxes unused for 24 hours are deleted, and there is a cap on the total (oldest removed first).
- The AI extraction cache is shared across sandboxes, since it is keyed by file hash, so SI-05 is read by Groq
  once per deployment and is instant for everyone after that.
- The admin-style endpoints that change master data keep working, but only inside the visitor's own sandbox.

**B. Deployment config**
- `render.yaml`: the Python service, build and start commands, a health check on `/api/health`, and
  environment variables. CORS limited to the Vercel domain.
- Frontend: the API base comes from `NEXT_PUBLIC_API_BASE`, the sandbox header is sent on every call
  (including the live run stream), and the build passes on Vercel.
- A small "warm-up" step after deploy: run SI-05 once so the Groq result is cached.

**C. Checks**
- Backend tests for sandboxes: two visitors running the same sample both get the designed decision; one
  visitor's reset leaves the other's data alone; a background run and its live stream use the right sandbox;
  old sandboxes are cleaned up.
- The existing suites stay green: pytest, `npm run check` and the adversarial run (49/49).
- After deploy: a Playwright run against the **public URLs** (two separate browser contexts as two visitors)
  covering all 8 screens, all 7 samples (SI-05 through Groq), the override and reset, with 0 console errors.

## Done when

- Two visitors on the live link each run SI-01 and both get **Auto-approve**. Neither sees the other's runs.
- All 7 samples give their expected decisions on the live link, and SI-05 is read by Groq.
- The live Playwright check passes with 0 console errors, and the cold start (after sleep) loads in under about a
  minute.
- No secret is in the repo; the old Groq key is revoked.

## Order and rough effort

| # | Step | Who | Effort |
|---|---|---|---|
| 1 | Build per-visitor sandboxes + tests | me | 3-4 h |
| 2 | Deployment config (`render.yaml`, frontend API base and sandbox header) | me | 1 h |
| 3 | Create GitHub repo, new Groq key | you | 5 min |
| 4 | Push to GitHub | me, on your go-ahead | 2 min |
| 5 | Render and Vercel projects, set env vars | you, with my settings | 10 min |
| 6 | Warm-up, then live Playwright check on the public URLs | me | 30 min |
| 7 | Update README with the live link and how sandboxes work | me | 15 min |

Steps 1-2 can start now; steps 3 and 5 can happen at the same time.

## Risks

- **Free Render sleeps** after 15 min idle: open the link before the demo or the interview. The paid starter
  plan (about $7/month) removes this if you want it for the interview week.
- **Render's free disk is temporary:** sandboxes and the AI cache are lost on each deploy or restart. That is fine
  for a demo, because everything re-seeds itself. Run the warm-up again after each deploy.
- **Groq free tier:** a scan can take about a minute the first time. The shared cache makes it instant afterwards.
