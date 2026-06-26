import threading
import json
import requests
import os
import random
import time
import queue
import chess
import chess.engine

# --- CONFIGURATION ---
TOKEN = os.environ.get("LICHESS_TOKEN", "YOUR_SECRET_TOKEN_HERE")
BOT_USERNAME = "Studyloversz-bot"
# Update this to the exact path of your local Stockfish binary
STOCKFISH_PATH = "/usr/games/stockfish"  # or "stockfish.exe" on Windows

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Thread-safe job queue for engine calculations
engine_queue = queue.Queue()

def send_chat_message(game_id, room, text):
    """Sends a chat message to the opponent or spectator room."""
    url = f"https://lichess.org/api/bot/game/{game_id}/chat"
    data = {"room": room, "text": text}
    try:
        requests.post(url, headers=HEADERS, json=data, timeout=5)
    except Exception as e:
        print(f"[{game_id}] Failed to send chat: {e}")

def make_lichess_move(game_id, move_str):
    """Sends the calculated move back to Lichess."""
    url = f"https://lichess.org/api/bot/game/{game_id}/move/{move_str}"
    try:
        response = requests.post(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            print(f"[{game_id}] Played move: {move_str}")
        else:
            print(f"[{game_id}] Move failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"[{game_id}] Error posting move: {e}")

def stockfish_worker():
    """Dedicated background thread handling all Stockfish calculations sequentially."""
    print("[ENGINE] Initializing local Stockfish engine instance...")
    try:
        engine = chess.engine.SimpleEngine.Popen(STOCKFISH_PATH)
        # Configure engine behavior for a strong ~2300 Elo playstyle
        engine.configure({"Skill Level": 20, "Hash": 64, "Threads": 1})
    except Exception as e:
        print(f"[CRITICAL] Failed to start Stockfish binary: {e}")
        return

    while True:
        # Fetch calculation task from the queue
        game_id, moves_list, callback = engine_queue.get()
        try:
            board = chess.Board()
            for move in moves_list:
                try:
                    board.push_uci(move)
                except Exception:
                    pass

            if board.is_game_over():
                callback(None)
                engine_queue.task_done()
                continue

            # Limit evaluation to 0.1 seconds for maximum speed
            # Multipv=2 evaluates the top 2 best lines simultaneously
            result = engine.analyse(board, chess.engine.Limit(time=0.1), multipv=2)

            best_move = None
            if isinstance(result, list) and len(result) > 0:
                dice_roll = random.random()
                
                # 1. Safely check if a 2nd best line exists and roll the dice (35% chance)
                if len(result) > 1 and dice_roll > 0.65:
                    pv_list = result[1].get("pv", [])
                    if pv_list:  
                        best_move = pv_list[0]  # FIXED: Target the first move item
                        print(f"[{game_id}] Selection: Alternated to 2nd best move option.")
                
                # 2. Fallback to the absolute best engine line if 2nd line fails or wasn't chosen
                if not best_move:
                    pv_list = result[0].get("pv", [])
                    if pv_list:
                        best_move = pv_list[0]  # FIXED: Target the first move item

            if best_move and best_move in board.legal_moves:
                callback(best_move.uci())
            else:
                # Absolute panic fallback
                legal_moves = list(board.legal_moves)
                callback(random.choice(legal_moves).uci() if legal_moves else None)

        except Exception as err:
            print(f"[{game_id}] Engine error during analysis: {err}")
            callback(None)
        finally:
            engine_queue.task_done()

def play_game(game_id):
    """Streams individual match events. Breaks loop when game ends."""
    print(f"\n[GAME START] Thread spawned for game: {game_id}")
    url = f"https://lichess.org/api/bot/game/stream/{game_id}"
    
    try:
        response = requests.get(url, headers=HEADERS, stream=True, timeout=15)
    except Exception as e:
        print(f"[{game_id}] Stream connection failed: {e}")
        return
        
    bot_color = None
    sent_welcome = False

    for line in response.iter_lines():
        if not line:
            continue
            
        try:
            game_event = json.loads(line.decode('utf-8'))
        except Exception:
            continue

        event_type = game_event.get('type')
        if event_type == 'gameFull':
            white_id = game_event['white'].get('id', '').lower()
            bot_color = 'white' if white_id == BOT_USERNAME.lower() else 'black'
            state = game_event['state']
        elif event_type == 'gameState':
            state = game_event
        else:
            continue

        if state.get('status') != 'started':
            print(f"[{game_id}] Match complete. Reason: {state.get('status')}")
            send_chat_message(game_id, "player", "Good game! Thanks for playing.")
            break

        if event_type == 'gameFull' and not sent_welcome:
            send_chat_message(game_id, "player", "Hello! Upgraded engine active (~2300 Elo). Good luck!")
            sent_welcome = True

        moves_played = state['moves'].strip().split() if state['moves'].strip() else []
        total_moves = len(moves_played)

        is_bot_turn = (total_moves % 2 == 0 and bot_color == 'white') or \
                      (total_moves % 2 != 0 and bot_color == 'black')

        if is_bot_turn:
            time.sleep(random.uniform(0.1, 0.4))
            
            def handle_move_result(move_uci):
                if move_uci:
                    make_lichess_move(game_id, move_uci)

            engine_queue.put((game_id, moves_played, handle_move_result))

def listen_to_events():
    """Listens to global challenges and game starts."""
    print(f"Starting global event listener for user: {BOT_USERNAME}")
    url = "https://lichess.org/api/stream/event"
    
    response = requests.get(url, headers=HEADERS, stream=True, timeout=60)
    
    for line in response.iter_lines():
        if not line:
            continue
            
        try:
            event = json.loads(line.decode('utf-8'))
        except Exception:
            continue

        if event.get('type') == 'challenge':
            challenge_id = event['challenge']['id']
            variant = event['challenge']['variant']['key']
            
            if variant != 'standard':
                print(f"[CHALLENGE] Declining variant '{variant}' for ID: {challenge_id}")
                requests.post(f"https://lichess.org/api/challenge/{challenge_id}/decline", headers=HEADERS, timeout=5)
                continue

            print(f"[CHALLENGE] Auto-accepting ID: {challenge_id}")
            accept_url = f"https://lichess.org/api/challenge/{challenge_id}/accept"
            requests.post(accept_url, headers=HEADERS, timeout=5)

        elif event.get('type') == 'gameStart':
            game_id = event['game']['gameId']  
            game_thread = threading.Thread(target=play_game, args=(game_id,))
            game_thread.daemon = True
            game_thread.start()

if __name__ == "__main__":
    worker_thread = threading.Thread(target=stockfish_worker, daemon=True)
    worker_thread.start()

    while True:
        try:
            listen_to_events()
        except Exception as global_err:
            print(f"Network stream disconnected: {global_err}. Reconnecting in 10 seconds...")
            time.sleep(10)
