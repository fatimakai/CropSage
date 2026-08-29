# CropSage backend API

The FastAPI service is a private server-to-server boundary for the Next.js
application. The finalized frontend contract is:

```text
POST /v1/recommendations/score
```

Its request contains `farm_profile`, `evidence_bundle`, and `scoring_config`.
The response is the bare validated RecommendationOutput with all 22 crop
results. Unvalidated evidence is rejected and never produces displayable
rankings.

Additional endpoints support the recommendation service and conversational
demo:

```text
GET    /health
POST   /v1/recommendations
POST   /v1/planting-guidance
POST   /v1/chat
DELETE /v1/chat/{session_id}
```

Run locally:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Railway builds from the repository root using `railway.toml`. Set `/health` as
the health-check path. OpenRouter is the primary LLM provider and Gemini is the
optional fallback; deterministic scoring itself needs neither LLM key.

The Python service does not currently query Supabase. The Next.js server owns
authenticated persistence and sends the finalized scoring contracts over
Railway private networking. Do not add unused Supabase secrets to this service.
Conversation state is process-local for the hackathon demo because the
finalized database migrations do not define chat-session/message tables.
