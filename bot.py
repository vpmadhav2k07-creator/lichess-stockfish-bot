import threading
import json
import requests
import os
import random
import time
import queue
import shutil
import chess
import chess.engine

# --- CONFIGURATION ---
TOKEN = os.environ.get("LICHESS_TOKEN", "YOUR_SECRET_TOKEN_HERE")
BOT_USERNAME = "Studyloversz-bot"

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
    
    resolved_path = shutil.which("stockfish")
    
    if resolved_path:
        print(f"[ENGINE] Successfully located Stockfish binary at: {resolved_path}")
    else:
        possible_paths = ["/usr/games/stockfish", "/usr/bin/stockfish", "./stockfish", "/usr/local/bin/stockfish"]
        for path in possible_paths:
            if os.path.exists(path):
                resolved_path = path
                print(f"[ENGINE] Fallback found Stockfish binary at: {resolved_path}")
                break
                
    if not resolved_path:
        print("[CRITICAL] Could not locate Stockfish binary anywhere in the system path!")
        return

    try:
        # FIXED: Using the synchronous SimpleEngine wrapper instead of the raw async coroutine
        engine = chess.engine.SimpleEngine.popen_uci(resolved_path)
        engine.configure({"Skill Level": 20, "Hash": 64, "Threads": 1})
        print("[ENGINE] Stockfish is fully loaded and ready to accept match jobs.")
    except Exception as e:
        print(f"[CRITICAL] Failed to start Stockfish engine instance: {e}")
        return

    while True:
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

            result = engine.play(board, chess.engine.Limit(time=0.1))
            best_move = result.move

            if best_move and board.is_legal(best_move):
                print(f"[{game_id}] Engine generated valid move: {best_move.uci()}")
                callback(best_move.uci())
            else:
                legal_moves = list(board.legal_moves)
                if legal_moves:
                    fallback_move = random.choice(legal_moves).uci()
                    print(f"[{game_id}] Panic fallback triggered. Selected move: {fallback_move}")
                    callback(fallback_move)
                else:
                    callback(None)

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
        response = requests.get(url, headers=HEADERS, stream=True, timeout=None)
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
            white_player = game_event.get('white', {})
            white_id = white_player.get('id', '') if isinstance(white_player, dict) else ''
            
            if white_id.lower() == BOT_USERNAME.lower():
                bot_color = 'white'
            else:
                bot_color = 'black'
                
            state = game_event['state']
            print(f"[{game_id}] Match configuration locked. Bot Color side: {bot_color.upper()}")
            
        elif event_type == 'gameState':
            state = game_event
            # FIXED FALLBACK: Fetches single JSON data securely via the standard export endpoint
            if bot_color is None:
                print(f"[{game_id}] Stream reconnected mid-game. Fetching true match details...")
                try:
                    export_url = f"https://lichess.org{game_id}"
                    export_headers = {**HEADERS, "Accept": "application/json"}
                    meta_resp = requests.get(export_url, headers=export_headers, timeout=5)
                    
                    if meta_resp.status_code == 200:
                        meta_data = meta_resp.json()
                        w_id = meta_data.get('players', {}).get('white', {}).get('user', {}).get('id', '')
                        bot_color = 'white' if w_id.lower() == BOT_USERNAME.lower() else 'black'
                        print(f"[{game_id}] Recovered color profile safely: {bot_color.upper()}")
                    else:
                        print(f"[{game_id}] Export API returned status code: {meta_resp.status_code}")
                except Exception as ex:
                    print(f"[{game_id}] Error recovering color profile: {ex}")
        else:
            continue

        if state.get('status') != 'started':
            print(f"[{game_id}] Match complete. Reason: {state.get('status')}")
            send_chat_message(game_id, "player", "Good game! Thanks for playing.")
            break

        if event_type == 'gameFull' and not sent_welcome:
            send_chat_message(game_id, "player", "Hello! Fast Engine Mode active. Good luck!")
            sent_welcome = True

        moves_played = state['moves'].strip().split() if state['moves'].strip() else []
        total_moves = len(moves_played)

        if bot_color is None:
            print(f"[{game_id}] Warning: Skipping move check because bot color is unknown.")
            continue

        is_bot_turn = (total_moves % 2 == 0 and bot_color == 'white') or \
                      (total_moves % 2 != 0 and bot_color == 'black')

        if is_bot_turn:
            print(f"[{game_id}] Bot turn detected (Move #{total_moves + 1}). Queueing engine evaluation...")
            def handle_move_result(move_uci):
                if move_uci:
                    make_lichess_move(game_id, move_uci)

            engine_queue.put((game_id, moves_played, handle_move_result))

def listen_to_events():
    """Listens to global challenges and game starts."""
    print(f"Starting global event listener for user: {BOT_USERNAME}")
    url = "https://lichess.org/api/stream/event"
    
    while True:
        try:
            response = requests.get(url, headers=HEADERS, stream=True, timeout=None)
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
                        requests.post(f"https://lichess.org/api/challenge/decline{challenge_id}/decline", headers=HEADERS, timeout=5)
                        continue

                    print(f"[CHALLENGE] Auto-accepting ID: {challenge_id}")
                    accept_url = f"https://lichess.org/api/challenge/accept{challenge_id}/accept"
                    requests.post(accept_url, headers=HEADERS, timeout=5)

                elif event.get('type') == 'gameStart':
                    game_id = event['game']['id']  
                    game_thread = threading.Thread(target=play_game, args=(game_id,))
                    game_thread.daemon = True
                    game_thread.start()
                    
        except Exception as global_err:
            print(f"[SYSTEM] Critical network or stream failure: {global_err}")
            print("[SYSTEM] Reconnecting to Lichess event stream in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    # Start the engine worker background thread
    worker_thread = threading.Thread(target=stockfish_worker, daemon=True)
    worker_thread.start()
    
    # Start the event listener loop safely
    try:
        listen_to_events()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Bot execution halted manually.")
    finally:
        print("[SHUTDOWN] Clean exit completed.")
