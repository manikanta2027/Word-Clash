# Word Clash

A real-time multiplayer word guessing game for 2–6 players. Players create or join a room with a six-character code, solve five timed word rounds, chat, and compete on a live leaderboard.

## Stack
- Frontend: React 18 + Vite
- Backend: FastAPI + WebSockets
- State: in-memory server-side room manager (single backend process)

## Run locally

### 1. Backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend (new terminal)
```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (usually http://localhost:5173). For a local multiplayer test, open two separate browser windows or devices on the same network; set `VITE_WS_URL=ws://YOUR_COMPUTER_LAN_IP:8000/ws` in `frontend/.env.local` for other devices on the LAN.

## Gameplay
- 2–6 players per room; the host starts a game once at least two are connected.
- Five rounds, 45 seconds each, with up to four shared clues per word.
- First correct guess per player per round scores: 100/75/50/25 base points based on clue count, plus a small speed bonus (maximum 20).
- Incorrect guesses may be retried; only one correct score is awarded per player per round.
- Host advances between rounds. A majority rematch vote starts a new match.
- Chat is room-wide. The sound toggle controls local sound effects.

## WebSocket protocol
The client first sends `create_room` or `join_room` with `{name, player_id, room_code?}`. After joining, supported events are `ready`, `start_game`, `submit_guess`, `reveal_hint`, `chat`, `next_round`, and `rematch_vote`. The server sends `welcome`, `state`, `guess_result`, `player_guessed`, `chat_message`, and `error` events.

## Deploy publicly

### Backend on Render
1. Push this folder to a GitHub repository.
2. In Render, create a new Blueprint from the repository (the included `render.yaml` defines the FastAPI service), or create a Python web service manually.
3. Confirm the service health check at `/health` and copy its public host.

### Frontend on Vercel
1. Import the same repository into Vercel and set the project root directory to `frontend`.
2. Set the build command to `npm run build` and output directory to `dist` (Vite defaults).
3. Add environment variable `VITE_WS_URL` with `wss://YOUR-RENDER-SERVICE.onrender.com/ws`.
4. Deploy and open the Vercel URL. Test by joining from two separate devices.

## Notes before public deployment
- This starter stores rooms in memory. A process restart clears active rooms; use Redis for multi-instance or durable room coordination.
- Configure `VITE_WS_URL` to the deployed `wss://.../ws` endpoint for production.
- Restrict CORS origins and add rate limits / moderation before opening a public instance.
- The current demo uses a curated word bank and no account system by design.
