import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app, rooms


def recv_event(ws, expected=None):
    msg = ws.receive_json()
    if expected:
        assert msg["event"] == expected, msg
    return msg


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


def test_two_player_room_gameplay_and_chat():
    rooms.clear()
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as host:
            host.send_json({"event":"create_room","data":{"name":"Host","player_id":"host-1"}})
            welcome = recv_event(host, "welcome")["data"]
            code = welcome["room_code"]
            recv_event(host, "state")
            assert len(code) == 6

            with client.websocket_connect('/ws') as guest:
                guest.send_json({"event":"join_room","data":{"name":"Guest","player_id":"guest-1","room_code":code}})
                recv_event(guest, "welcome")
                host_state = recv_event(host, "state")["data"]
                guest_state = recv_event(guest, "state")["data"]
                assert len(host_state["players"]) == 2
                assert [p["name"] for p in guest_state["players"]] == ["Guest", "Host"] or len(guest_state["players"]) == 2

                host.send_json({"event":"start_game","data":{}})
                host_state = recv_event(host, "state")["data"]
                guest_state = recv_event(guest, "state")["data"]
                assert host_state["status"] == "round"
                assert guest_state["round_number"] == 1
                assert len(host_state["hints"]) == 1

                room = rooms[code]
                answer = room.current_word["word"]
                guest.send_json({"event":"submit_guess","data":{"guess":"not-the-answer"}})
                wrong = recv_event(guest, "guess_result")["data"]
                assert wrong["correct"] is False

                guest.send_json({"event":"submit_guess","data":{"guess":answer.lower()}})
                correct = recv_event(guest, "guess_result")["data"]
                assert correct["correct"] is True
                assert correct["points"] >= 100
                # State and correct-answer broadcast follow the private result.
                recv_event(host, "player_guessed")
                host_state = recv_event(host, "state")["data"]
                assert next(p for p in host_state["players"] if p["id"] == "guest-1")["score"] > 0

                guest.send_json({"event":"chat","data":{"message":"GG!"}})
                host_chat = recv_event(host, "chat_message")["data"]
                assert host_chat["message"] == "GG!"
                assert host_chat["name"] == "Guest"

                guest.send_json({"event":"reveal_hint","data":{}})
                host_state = recv_event(host, "state")["data"]
                assert host_state["revealed_hints"] == 2


def test_room_rejects_invalid_code():
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as ws:
            ws.send_json({"event":"join_room","data":{"name":"Visitor","player_id":"visitor-1","room_code":"NOPE99"}})
            error = recv_event(ws, "error")["data"]
            assert "Room not found" in error["message"]


def test_room_capacity_is_six_players():
    from contextlib import ExitStack
    rooms.clear()
    with TestClient(app) as client, ExitStack() as stack:
        sockets = []
        host = stack.enter_context(client.websocket_connect('/ws'))
        sockets.append(host)
        host.send_json({"event":"create_room","data":{"name":"P1","player_id":"cap-1"}})
        code = recv_event(host, "welcome")["data"]["room_code"]
        recv_event(host, "state")
        for index in range(2, 7):
            ws = stack.enter_context(client.websocket_connect('/ws'))
            sockets.append(ws)
            ws.send_json({"event":"join_room","data":{"name":f"P{index}","player_id":f"cap-{index}","room_code":code}})
            recv_event(ws, "welcome")
            # Existing participants receive the player-list update.
            for prior in sockets[:-1]: recv_event(prior, "state")
            recv_event(ws, "state")
        assert len(rooms[code].players) == 6
        rejected = stack.enter_context(client.websocket_connect('/ws'))
        rejected.send_json({"event":"join_room","data":{"name":"P7","player_id":"cap-7","room_code":code}})
        error = recv_event(rejected, "error")["data"]
        assert "full" in error["message"].lower()
