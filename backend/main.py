from __future__ import annotations
import asyncio, json, os, random, re, string, time
from dataclasses import dataclass, field
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = FastAPI(title="Word Clash API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

WORDS = [
 {"word":"VOLCANO","category":"Nature","hints":["I can be found on land or beneath the ocean.","I may remain quiet for many years.","Pressure builds beneath my surface.","I can release lava, ash and gases."]},
 {"word":"ALGORITHM","category":"Technology","hints":["I am a set of ordered instructions.","I help solve a problem or complete a task.","Computers use me constantly.","I am fundamental to programming."]},
 {"word":"COMPASS","category":"Everyday","hints":["I am small enough to carry.","I help people find their way.","I respond to Earth's magnetic field.","My needle points north."]},
 {"word":"BUTTERFLY","category":"Animals","hints":["I begin life in a very different form.","I have six legs.","I often visit flowers.","I have large colorful wings."]},
 {"word":"ECLIPSE","category":"Science","hints":["I am an event in the sky.","I involve the Sun, Moon and Earth.","I can be total or partial.","One celestial body blocks another from view."]},
 {"word":"LIBRARY","category":"Places","hints":["People visit me to learn or explore.","I can be quiet and peaceful.","You may borrow things from me.","I contain shelves full of books."]},
 {"word":"PINEAPPLE","category":"Food","hints":["I grow in warm climates.","My outside is rough and spiky.","I am sweet and tangy.","I have a leafy crown."]},
 {"word":"SATELLITE","category":"Space","hints":["I travel around a larger object.","Some of me are natural and some are made by people.","I help with communication and navigation.","The Moon is Earth's natural example."]},
 {"word":"KEYBOARD","category":"Technology","hints":["I am used to give instructions to a device.","I contain many buttons.","I can be mechanical or virtual.","You type words on me."]},
 {"word":"RAINBOW","category":"Nature","hints":["I appear when light interacts with water.","I form an arc in the sky.","I contain a spectrum of colors.","You may see me after rain when sunlight returns."]},
 {"word":"ASTRONAUT","category":"People","hints":["My workplace can be far from Earth.","I need special training.","I may travel in a spacecraft.","I explore space."]},
 {"word":"TREADMILL","category":"Fitness","hints":["I stay in one place.","I help people exercise indoors.","My surface moves beneath your feet.","You walk or run on me."]},
]

@dataclass
class Player:
    id: str
    name: str
    websocket: WebSocket | None = None
    score: int = 0
    ready: bool = False
    connected: bool = True
    guesses: set[int] = field(default_factory=set)
    hints_used: dict[int, int] = field(default_factory=dict)

@dataclass
class Room:
    code: str
    host_id: str
    players: dict[str, Player] = field(default_factory=dict)
    status: str = "lobby"
    round_number: int = 0
    total_rounds: int = 5
    current_word: dict[str, Any] | None = None
    revealed_hints: int = 0
    round_started: float = 0
    round_duration: int = 45
    used_words: set[str] = field(default_factory=set)
    round_results: list[dict[str, Any]] = field(default_factory=list)
    chat: list[dict[str, Any]] = field(default_factory=list)
    rematch_votes: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    generation_in_progress: bool = False


rooms: dict[str, Room] = {}

# Quick Match queue: each waiting connection owns a Future that resolves
# when another player is paired with it.
matchmaking_waiters: dict[str, dict[str, Any]] = {}
matchmaking_lock = asyncio.Lock()


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def difficulty_for_round(round_number: int, total_rounds: int) -> tuple[str, int]:
    """Increase difficulty from Easy to Medium to Hard across the match."""
    total = max(1, total_rounds)
    progress_index = max(0, round_number - 1)
    tier = min(2, (progress_index * 3) // total)
    return [("Easy", 100), ("Medium", 150), ("Hard", 200)][tier]




def _generate_word_with_gemini(used_words: set[str], difficulty: str = "Easy") -> dict[str, Any] | None:
    """Generate one fresh Word Clash answer and four progressive hints."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)
    prompt = f"""
Create exactly one original word-guessing round for a multiplayer game.
Difficulty for this question: {difficulty}. Match the answer complexity to this level: Easy uses very common words; Medium uses familiar but less obvious words; Hard uses challenging but still fair general-knowledge words.
Return ONLY valid JSON with this exact shape:
{{
  "word": "ONE WORD OR A COMMON COMPOUND WORD",
  "category": "one short category",
  "hints": [
    "Hint 1: difficult and indirect",
    "Hint 2: a little more helpful",
    "Hint 3: quite helpful",
    "Hint 4: very helpful but do not say the answer"
  ]
}}

Rules:
- Choose a very familiar, everyday answer that most people can guess.
- Prefer common things, animals, foods, sports, places, school items,
  household objects, popular technology, and simple nature words.
- Use simple English that a school student can understand. Keep each hint
  short, friendly, and conversational. Avoid difficult vocabulary, riddles,
  wordplay, technical terms, and confusing descriptions.
- Make all four hints useful and fairly easy, becoming more direct each time.
  Hint 1 should already give a helpful clue; Hint 4 should make the answer
  quite easy to identify without saying the answer.
- Give concrete clues about what it looks like, where it is found, what it
  does, or how people use it.
- Never include the answer itself or its spelling in a hint.
- Avoid obscure, offensive, adult, political, or highly subjective answers.
- Do not use these previously used answers:
{json.dumps(sorted(used_words))}
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.9,
            ),
        )
        result = json.loads(response.text or "{}")
        word = re.sub(r"[^A-Z]", "", str(result.get("word", "")).upper())
        category = str(result.get("category", "General")).strip()[:30]
        hints = result.get("hints")

        if not word or word in used_words or not isinstance(hints, list) or len(hints) != 4:
            return None

        clean_hints = [str(hint).strip()[:220] for hint in hints]
        if any(not hint for hint in clean_hints):
            return None

        return {"word": word, "category": category or "General", "hints": clean_hints}
    except Exception as exc:
        print(f"Gemini question generation failed: {type(exc).__name__}: {exc}")
        return None


async def generate_round_word(room: Room, difficulty: str = "Easy") -> dict[str, Any]:
    """Try Gemini first, then use an unused built-in word as a fallback."""
    try:
        # Do not let a slow/unavailable Gemini response hold up the match.
        generated = await asyncio.wait_for(
            asyncio.to_thread(_generate_word_with_gemini, set(room.used_words), difficulty),
            timeout=8,
        )
    except asyncio.TimeoutError:
        print("Gemini question generation timed out; using an unused fallback question.")
        generated = None

    if generated:
        return generated

    fallback_words = [
        item for item in WORDS
        if re.sub(r"[^A-Z]", "", item["word"].upper()) not in room.used_words
    ]
    if fallback_words:
        return random.choice(fallback_words)

    raise RuntimeError(
        "No unused fallback questions remain. Check GEMINI_API_KEY and backend logs."
    )


def safe_name(value: Any) -> str:
    name = re.sub(r"[^\w -]", "", str(value or "Player")).strip()[:18]
    return name or "Player"

def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(random.choice(alphabet) for _ in range(6))
        if code not in rooms: return code

def leaderboard(room: Room) -> list[dict[str, Any]]:
    return sorted([{"id":p.id,"name":p.name,"score":p.score,"connected":p.connected,"ready":p.ready,"is_host":p.id==room.host_id} for p in room.players.values()], key=lambda x:(-x["score"], x["name"].lower()))

def snapshot(room: Room, recipient_id: str | None = None) -> dict[str, Any]:
    recipient = room.players.get(recipient_id) if recipient_id else None
    extra_hints_used = (
        recipient.hints_used.get(room.round_number, 0)
        if recipient and room.status == "round"
        else 0
    )
    visible_hint_count = min(
        len(room.current_word["hints"]) if room.current_word else 0,
        2 + extra_hints_used,
    ) if room.status == "round" else 0
    difficulty, question_points = difficulty_for_round(
        max(1, room.round_number), room.total_rounds
    )
    data = {
        "room_code": room.code,
        "status": room.status,
        "host_id": room.host_id,
        "players": leaderboard(room),
        "round_number": room.round_number,
        "total_rounds": room.total_rounds,
        "round_duration": room.round_duration,
        "revealed_hints": visible_hint_count,
        "hints": (
            room.current_word["hints"][:visible_hint_count]
            if room.current_word and room.status == "round"
            else []
        ),
        "extra_hints_used": extra_hints_used,
        "free_hints": 2,
        "difficulty": difficulty,
        "question_points": question_points,
        "category": room.current_word["category"] if room.current_word else None,
        "masked_word": "".join("_" for _ in room.current_word["word"]) if room.current_word else None,
        "round_results": room.round_results[-1] if room.round_results else None,
        "chat": room.chat[-30:],
        "rematch_votes": list(room.rematch_votes),
    }
    if room.status == "round" and room.current_word:
        data["round_ends_at"] = room.round_started + room.round_duration
    if room.status == "finished":
        final_scores = leaderboard(room)
        top_score = final_scores[0]["score"] if final_scores else 0
        tied = len(final_scores) > 1 and final_scores[1]["score"] == top_score
        data["winner"] = (
            final_scores[0]
            if final_scores and top_score > 0 and not tied
            else None
        )
        data["is_draw"] = bool(final_scores) and (top_score == 0 or tied)
    return data

async def generate_round_word_from_used(
    used_words: set[str],
    difficulty: str
) -> dict[str, Any]:

    try:
        generated = await asyncio.wait_for(
            asyncio.to_thread(
                _generate_word_with_gemini,
                used_words,
                difficulty
            ),
            timeout=8
        )
    except asyncio.TimeoutError:
        print("Gemini timed out. Using fallback question.")
        generated = None

    if generated:
        return generated

    fallback_words = [
        item for item in WORDS
        if item["word"].upper() not in used_words
    ]

    if fallback_words:
        return random.choice(fallback_words)

    raise RuntimeError("No unused questions remain.")

async def send_one(player: Player, event: str, payload: Any):
    if player.websocket:
        try: await player.websocket.send_json({"event":event,"data":payload})
        except Exception: pass

async def broadcast(room: Room, event: str, payload: Any | None = None):
    message = payload if payload is not None else snapshot(room)
    await asyncio.gather(*(send_one(p,event,message) for p in list(room.players.values()) if p.websocket), return_exceptions=True)

async def broadcast_state(room: Room):
    await asyncio.gather(
        *(
            send_one(player, "state", snapshot(room, player.id))
            for player in list(room.players.values())
            if player.websocket
        ),
        return_exceptions=True,
    )

async def end_round(room: Room):
    if room.status != "round": return
    room.status = "round_result"
    word = room.current_word["word"] if room.current_word else ""
    if not room.round_results or room.round_results[-1].get("round") != room.round_number:
        room.round_results.append({
            "round": room.round_number,
            "word": word,
            "category": room.current_word["category"] if room.current_word else "",
            "round_winner": None,
            "difficulty": difficulty_for_round(room.round_number, room.total_rounds)[0],
            "question_points": difficulty_for_round(room.round_number, room.total_rounds)[1],
            "scores": leaderboard(room),
        })
    await broadcast_state(room)
    # The server advances the game after a 2-second result break.
    # This continues even if the host disconnects.
    asyncio.create_task(auto_advance_round(room, room.round_number))


async def auto_advance_round(
    room: Room,
    completed_round: int
):
    await asyncio.sleep(2)

    await start_next_round(
        room,
        expected_completed_round=completed_round
    )


async def run_round_clock(room: Room):
    this_round = room.round_number
    while room.status == "round" and room.round_number == this_round:
        remaining = room.round_started + room.round_duration - time.time()
        if remaining <= 0:
            await end_round(room); return
        await asyncio.sleep(min(1, remaining))

async def start_next_round(
    room: Room,
    expected_completed_round: int | None = None
):
    # Phase 1: Reserve the next round under the lock.
    async with room.lock:
        if room.generation_in_progress:
            return

        if expected_completed_round is not None:
            if (
                room.status != "round_result"
                or room.round_number != expected_completed_round
            ):
                return
        elif room.status != "lobby":
            return

        if room.round_number >= room.total_rounds:
            room.status = "finished"
            finished = True
            previous_round = room.round_number
        else:
            finished = False
            previous_round = room.round_number
            difficulty, _ = difficulty_for_round(
                previous_round + 1,
                room.total_rounds
            )
            used_words = set(room.used_words)
            room.generation_in_progress = True

    if finished:
        await broadcast_state(room)
        return

    # Phase 2: Generate outside the room lock.
    try:
        generated = await generate_round_word_from_used(
            used_words,
            difficulty
        )
    except Exception as exc:
        async with room.lock:
            room.generation_in_progress = False

        print(f"Question generation failed: {exc}")
        await broadcast(
            room,
            "error",
            {"message": "Could not generate the next question. Please try again."}
        )
        return

    # Phase 3: Commit the generated question under the lock.
    async with room.lock:
        if (
            not room.generation_in_progress
            or room.round_number != previous_round
        ):
            return

        room.current_word = generated
        room.used_words.add(generated["word"].upper())
        room.round_number += 1
        room.revealed_hints = 0
        room.round_started = time.time()
        room.status = "round"

        for player in room.players.values():
            player.guesses.discard(room.round_number)
            player.hints_used[room.round_number] = 0

        room.generation_in_progress = False

    # Phase 4: Notify players and start the clock.
    await broadcast_state(room)
    asyncio.create_task(run_round_clock(room))

async def handle_message(room: Room, player: Player, msg: dict[str, Any]):
    event, data = msg.get("event"), msg.get("data") or {}
    if event == "ready":
        player.ready = bool(data.get("ready", True))
        await broadcast_state(room)

    elif event == "set_rounds":
        # Only the room host can change match settings.
        if player.id != room.host_id:
            await send_one(
                player,
                "error",
                {"message": "Only the host can change the number of rounds."},
            )
            return

        # Match settings are locked after the game starts.
        if room.status != "lobby":
            await send_one(
                player,
                "error",
                {"message": "Rounds can only be changed in the lobby."},
            )
            return

        raw_rounds = data.get("rounds", 5)

        # Reject booleans, even though bool is a subclass of int in Python.
        if isinstance(raw_rounds, bool):
            await send_one(
                player,
                "error",
                {"message": "Choose 3, 5, 10, or 15 rounds."},
            )
            return

        try:
            selected_rounds = int(raw_rounds)
        except (TypeError, ValueError):
            await send_one(
                player,
                "error",
                {"message": "Invalid round selection. Choose 3, 5, 10, or 15."},
            )
            return

        if selected_rounds not in {3, 5, 10, 15}:
            await send_one(
                player,
                "error",
                {"message": "Choose 3, 5, 10, or 15 rounds."},
            )
            return

        room.total_rounds = selected_rounds
        await broadcast_state(room)

    elif event == "start_game":
        if player.id != room.host_id: await send_one(player,"error",{"message":"Only the host can start the game."}); return
        if len([p for p in room.players.values() if p.connected]) < 2: await send_one(player,"error",{"message":"At least two players are required."}); return
        if room.status not in ("lobby","finished"): return
        room.round_number=0; room.used_words.clear(); room.round_results.clear(); room.rematch_votes.clear()
        for p in room.players.values(): p.score=0; p.ready=False; p.guesses.clear()
        await start_next_round(room)
    elif event == "submit_guess":
        if room.status != "round" or not room.current_word:
            return

        guess = re.sub(r"\\s+", "", str(data.get("guess", ""))).upper()[:40]
        if not guess:
            return

        if room.round_number in player.guesses:
            await send_one(
                player,
                "error",
                {"message": "Your answer has already been counted this round."},
            )
            return

        correct = guess == room.current_word["word"].upper()
        if not correct:
            await send_one(
                player,
                "guess_result",
                {"correct": False, "points": 0, "message": "Not quite. Try another word!"},
            )
            return

        # First correct answer wins the round; later answers are rejected
        # because end_round changes the room status immediately.
        player.guesses.add(room.round_number)
        elapsed = max(0.0, time.time() - room.round_started)
        extra_hints_used = player.hints_used.get(room.round_number, 0)
        difficulty, question_points = difficulty_for_round(
            room.round_number, room.total_rounds
        )

        # The question's maximum marks are shown in the UI. Two default
        # hints are free. Each additional hint reduces available marks by 20%.
        hint_multiplier = max(0.60, 1 - (extra_hints_used * 0.20))
        speed_multiplier = 1 - (
            0.20 * min(elapsed, room.round_duration) / room.round_duration
        )
        earned = max(0, round(question_points * hint_multiplier * speed_multiplier))
        player.score += earned

        room.round_results.append({
            "round": room.round_number,
            "word": room.current_word["word"],
            "category": room.current_word["category"],
            "difficulty": difficulty,
            "question_points": question_points,
            "round_winner": {
                "id": player.id,
                "name": player.name,
                "points": earned,
                "hints_used": extra_hints_used,
                "time_seconds": round(elapsed, 2),
            },
            "scores": leaderboard(room),
        })

        await send_one(
            player,
            "guess_result",
            {
                "correct": True,
                "points": earned,
                "hints_used": extra_hints_used,
                "difficulty": difficulty,
                "question_points": question_points,
                "time_seconds": round(elapsed, 2),
                "message": f"Correct! You earned {earned} out of {question_points} points.",
            },
        )
        await broadcast(
            room,
            "player_guessed",
            {
                "player_id": player.id,
                "player_name": player.name,
                "correct": True,
                "round_winner": True,
            },
        )
        await end_round(room)

    elif event == "reveal_hint":
        if room.status != "round" or not room.current_word:
            return

        hints_used = player.hints_used.get(room.round_number, 0)
        total_hints = len(room.current_word["hints"])
        if (2 + hints_used) >= total_hints:
            await send_one(
                player,
                "error",
                {"message": "You have already used all available hints."},
            )
            return

        player.hints_used[room.round_number] = hints_used + 1
        # Only the requesting player receives their newly revealed hint.
        await send_one(player, "state", snapshot(room, player.id))
    elif event == "chat":
        text = re.sub(r"[\x00-\x1f]", "", str(data.get("message", ""))).strip()[:180]
        if text:
            room.chat.append({"id":str(time.time_ns()),"player_id":player.id,"name":player.name,"message":text,"time":time.time()})
            room.chat = room.chat[-60:]
            await broadcast(room,"chat_message",room.chat[-1])

    elif event == "next_round":
    # Round progression is automatic and controlled by the server.
        await send_one(
        player,
        "info",
        {"message": "The next question will start automatically."},
    )

    elif event == "rematch_vote":
        room.rematch_votes.add(player.id)
    

    await broadcast_state(room)

    connected = [
        p for p in room.players.values()
        if p.connected
    ]

    if (
        room.status == "finished"
        and connected
        and len(room.rematch_votes.intersection(
            p.id for p in connected
        )) >= max(2, (len(connected) // 2) + 1)
    ):
        room.round_number = 0
        room.used_words.clear()
        room.round_results.clear()
        room.rematch_votes.clear()

        for p in room.players.values():
            p.score = 0
            p.guesses.clear()
            p.ready = False

        asyncio.create_task(start_next_round(room))

@app.get("/")
def root(): return {"name":"Word Clash API","status":"ok","docs":"/docs"}

@app.get("/health")
def health(): return {"status":"healthy","rooms":len(rooms)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    room: Room | None = None
    player: Player | None = None
    player_id = ""
    waiting_for_match = False

    try:
        raw = await websocket.receive_json()
        action = raw.get("event")
        data = raw.get("data") or {}
        player_id = str(data.get("player_id") or f"p_{time.time_ns()}")[:80]
        name = safe_name(data.get("name"))

        if action == "create_room":
            code = new_code()
            room = Room(code=code, host_id=player_id)
            player = Player(player_id, name, websocket)
            room.players[player_id] = player
            rooms[code] = room

        elif action == "join_room":
            code = str(data.get("room_code", "")).upper().strip()
            room = rooms.get(code)
            if not room:
                await websocket.send_json({
                    "event": "error",
                    "data": {"message": "Room not found. Check the code and try again."},
                })
                await websocket.close()
                return

            if room.status == "finished":
                room.status = "lobby"

            existing = room.players.get(player_id)
            if existing:
                player = existing
                player.name = name
                player.websocket = websocket
                player.connected = True
            else:
                if len(room.players) >= 2:
                    await websocket.send_json({
                        "event": "error",
                        "data": {"message": "This room is full (maximum 2 players)."},
                    })
                    await websocket.close()
                    return
                player = Player(player_id, name, websocket)
                room.players[player_id] = player

        elif action == "quick_match":
            loop = asyncio.get_running_loop()
            my_future: asyncio.Future = loop.create_future()
            waiting_entry = None

            async with matchmaking_lock:
                # Drop stale waiters before trying to pair.
                stale_ids = [
                    pid for pid, entry in matchmaking_waiters.items()
                    if entry["future"].done()
                    or entry["websocket"].client_state.name != "CONNECTED"
                ]
                for pid in stale_ids:
                    matchmaking_waiters.pop(pid, None)

                if matchmaking_waiters:
                    waiting_id, waiting_entry = next(iter(matchmaking_waiters.items()))
                    matchmaking_waiters.pop(waiting_id, None)

                    waiting_player = Player(
                        waiting_id,
                        waiting_entry["name"],
                        waiting_entry["websocket"],
                    )
                    player = Player(player_id, name, websocket)
                    code = new_code()
                    room = Room(code=code, host_id=waiting_id, total_rounds=5)
                    room.players[waiting_id] = waiting_player
                    room.players[player_id] = player
                    rooms[code] = room

                    # Notify the waiting player that a match has been found.
                    if not waiting_entry["future"].done():
                        waiting_entry["future"].set_result((room, waiting_player))

                else:
                    # Send the waiting event before exposing this socket in the queue.
                    # This prevents a late "searching" event arriving after "welcome".
                    await websocket.send_json({
                        "event": "matchmaking",
                        "data": {"status": "searching", "message": "Looking for another player..."},
                    })
                    matchmaking_waiters[player_id] = {
                        "name": name,
                        "websocket": websocket,
                        "future": my_future,
                    }
                    waiting_for_match = True

            if waiting_for_match:
                # Exactly one coroutine may call receive_json() on a WebSocket
                # at a time. Keep one receive task alive while waiting, and
                # always cancel AND await it before entering the game loop.
                receive_task = asyncio.create_task(websocket.receive_json())
                try:
                    while True:
                        done, _ = await asyncio.wait(
                            {my_future, receive_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        if my_future in done:
                            receive_task.cancel()
                            await asyncio.gather(receive_task, return_exceptions=True)
                            room, player = my_future.result()
                            break

                        incoming = receive_task.result()
                        if incoming.get("event") == "cancel_matchmaking":
                            async with matchmaking_lock:
                                matchmaking_waiters.pop(player_id, None)
                            await websocket.send_json({
                                "event": "matchmaking",
                                "data": {
                                    "status": "cancelled",
                                    "message": "Matchmaking cancelled.",
                                },
                            })
                            await websocket.close()
                            return

                        # Continue waiting using one new receive task only after
                        # the previous receive_json() call has completed.
                        receive_task = asyncio.create_task(websocket.receive_json())

                except WebSocketDisconnect:
                    async with matchmaking_lock:
                        matchmaking_waiters.pop(player_id, None)
                    return
                finally:
                    if not receive_task.done():
                        receive_task.cancel()
                        await asyncio.gather(receive_task, return_exceptions=True)
                    async with matchmaking_lock:
                        entry = matchmaking_waiters.get(player_id)
                        if entry and entry.get("future") is my_future:
                            matchmaking_waiters.pop(player_id, None)

                if room is None or player is None:
                    return

            # The second player to arrive owns the newly created room.
            # It must welcome BOTH sockets and start the match. The first
            # player's handler is waiting on my_future and then joins its
            # normal receive loop below.
            if action == "quick_match" and not waiting_for_match and room and player and waiting_entry:
                waiting_player = room.players[room.host_id]
                await send_one(player, "welcome", {
                    "player_id": player.id,
                    "room_code": room.code,
                    "is_host": player.id == room.host_id,
                    "match_type": "quick",
                })
                await send_one(waiting_player, "welcome", {
                    "player_id": waiting_player.id,
                    "room_code": room.code,
                    "is_host": waiting_player.id == room.host_id,
                    "match_type": "quick",
                })
                await broadcast_state(room)
                await start_next_round(room)

        else:
            await websocket.send_json({
                "event": "error",
                "data": {"message": "First create a room, join a room, or choose Quick Match."},
            })
            await websocket.close()
            return

        if room is not None and player is not None and action != "quick_match":
            await send_one(player, "welcome", {
                "player_id": player.id,
                "room_code": room.code,
                "is_host": player.id == room.host_id,
            })
            await broadcast_state(room)

        while room is not None and player is not None:
            message = await websocket.receive_json()
            async with room.lock:
                await handle_message(room, player, message)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"WebSocket handler error: {type(exc).__name__}: {exc}")
        try:
            await websocket.send_json({
                "event": "error",
                "data": {"message": "Connection error. Please reconnect."},
            })
        except Exception:
            pass
    finally:
        if player_id:
            async with matchmaking_lock:
                matchmaking_waiters.pop(player_id, None)

        if room and player:
            player.websocket = None
            player.connected = False
            if room.host_id == player.id:
                next_host = next((p for p in room.players.values() if p.connected), None)
                if next_host:
                    room.host_id = next_host.id
            await broadcast_state(room)
            if not any(p.connected for p in room.players.values()):
                rooms.pop(room.code, None)

