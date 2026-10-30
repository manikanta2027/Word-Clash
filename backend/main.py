from __future__ import annotations
import asyncio, json, random, re, string, time
from dataclasses import dataclass, field
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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

rooms: dict[str, Room] = {}


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
    personal_hint_count = (
        recipient.hints_used.get(room.round_number, 0)
        if recipient and room.status == "round"
        else 0
    )
    data = {
        "room_code": room.code,
        "status": room.status,
        "host_id": room.host_id,
        "players": leaderboard(room),
        "round_number": room.round_number,
        "total_rounds": room.total_rounds,
        "round_duration": room.round_duration,
        "revealed_hints": personal_hint_count,
        "hints": (
            room.current_word["hints"][:personal_hint_count]
            if room.current_word and room.status == "round"
            else []
        ),
        "category": room.current_word["category"] if room.current_word else None,
        "masked_word": " ".join("_" for _ in room.current_word["word"]) if room.current_word else None,
        "round_results": room.round_results[-1] if room.round_results else None,
        "chat": room.chat[-30:],
        "rematch_votes": list(room.rematch_votes),
    }
    if room.status == "round" and room.current_word:
        data["round_ends_at"] = room.round_started + room.round_duration
    if room.status == "finished":
        data["winner"] = leaderboard(room)[0] if room.players else None
    return data

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
            "scores": leaderboard(room),
        })
    await broadcast_state(room)

async def run_round_clock(room: Room):
    this_round = room.round_number
    while room.status == "round" and room.round_number == this_round:
        remaining = room.round_started + room.round_duration - time.time()
        if remaining <= 0:
            await end_round(room); return
        await asyncio.sleep(min(1, remaining))

async def start_next_round(room: Room):
    if room.round_number >= room.total_rounds:
        room.status = "finished"
        await broadcast_state(room); return
    available = [w for w in WORDS if w["word"] not in room.used_words]
    if not available: room.used_words.clear(); available = WORDS[:]
    room.current_word = random.choice(available)
    room.used_words.add(room.current_word["word"])
    room.round_number += 1
    room.revealed_hints = 0  # Compatibility only; hints are tracked per player.
    room.round_started = time.time()
    for player in room.players.values():
        player.guesses.discard(room.round_number)
        player.hints_used[room.round_number] = 0
    room.status = "round"
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
        hints_used = player.hints_used.get(room.round_number, 0)

        hint_points = max(20, 100 - (hints_used * 20))
        speed_bonus = max(
            0,
            round(20 * (1 - min(elapsed, room.round_duration) / room.round_duration)),
        )
        earned = hint_points + speed_bonus
        player.score += earned

        room.round_results.append({
            "round": room.round_number,
            "word": room.current_word["word"],
            "category": room.current_word["category"],
            "round_winner": {
                "id": player.id,
                "name": player.name,
                "points": earned,
                "hints_used": hints_used,
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
                "hints_used": hints_used,
                "time_seconds": round(elapsed, 2),
                "message": f"Correct! You won the round and earned {earned} points.",
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
        if hints_used >= total_hints:
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
        if player.id != room.host_id: await send_one(player,"error",{"message":"Only the host can continue."}); return
        if room.status == "round_result": await start_next_round(room)
    elif event == "rematch_vote":
        room.rematch_votes.add(player.id)
        await broadcast_state(room)
        connected = [p for p in room.players.values() if p.connected]
        if room.status == "finished" and connected and len(room.rematch_votes.intersection(p.id for p in connected)) >= max(2, (len(connected)//2)+1):
            room.round_number=0; room.used_words.clear(); room.round_results.clear(); room.rematch_votes.clear()
            for p in room.players.values(): p.score=0; p.guesses.clear(); p.ready=False
            await start_next_round(room)

@app.get("/")
def root(): return {"name":"Word Clash API","status":"ok","docs":"/docs"}

@app.get("/health")
def health(): return {"status":"healthy","rooms":len(rooms)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    room: Room | None = None; player: Player | None = None
    try:
        raw = await websocket.receive_json()
        action = raw.get("event"); data = raw.get("data") or {}
        player_id = str(data.get("player_id") or f"p_{time.time_ns()}")[:80]
        name = safe_name(data.get("name"))
        if action == "create_room":
            code = new_code(); room = Room(code=code,host_id=player_id); player=Player(player_id,name,websocket); room.players[player_id]=player; rooms[code]=room
        elif action == "join_room":
            code = str(data.get("room_code","")).upper().strip(); room=rooms.get(code)
            if not room: await websocket.send_json({"event":"error","data":{"message":"Room not found. Check the code and try again."}}); await websocket.close(); return
            if room.status == "finished": room.status = "lobby"
            existing=room.players.get(player_id)
            if existing: player=existing; player.name=name; player.websocket=websocket; player.connected=True
            else:
                if len(room.players)>=6: await websocket.send_json({"event":"error","data":{"message":"This room is full (maximum 6 players)."}}); await websocket.close(); return
                player=Player(player_id,name,websocket); room.players[player_id]=player
        else:
            await websocket.send_json({"event":"error","data":{"message":"First create or join a room."}}); await websocket.close(); return
        await send_one(player,"welcome",{"player_id":player.id,"room_code":room.code,"is_host":player.id==room.host_id})
        await broadcast_state(room)
        while True:
            message=await websocket.receive_json()
            async with room.lock: await handle_message(room,player,message)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try: await websocket.send_json({"event":"error","data":{"message":"Connection error. Please reconnect."}})
        except Exception: pass
    finally:
        if room and player:
            player.websocket=None; player.connected=False
            if room.host_id==player.id:
                next_host=next((p for p in room.players.values() if p.connected),None)
                if next_host: room.host_id=next_host.id
            await broadcast_state(room)
            if not any(p.connected for p in room.players.values()): rooms.pop(room.code,None)
