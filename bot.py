import threading
import json
import requests
import os
import random
import chess  # Tracks real-time board positioning

# --- CONFIGURATION ---
TOKEN = os.environ.get("LICHESS_TOKEN", "lip_DroTWz1knn0uQnOFqCjK")
BOT_USERNAME = "Studyloversz-bot"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def make_lichess_move/make_lichess_move(game_id, move_str):
    """Sends the calculated move back to Lichess."""
    # FIXED: Added back the correct API path folder structure
    url = f"https://lichess.org/api/bot/game/{game_id}/move/{move_str}"
    try:
        response = requests.post(url, headers=HEADERS)
        if response.status_code == 200:
            print(f"[{game_id}] Successfully played move: {move_str}")
        else:
            print(f"[{game_id}] Move failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[{game_id}] Error posting move: {e}")

def get_engine_move(moves_list, bot_color):
    """
    Queries the Lichess Cloud Database for Stockfish calculations.
    Introduces positional selection variance to simulate ~2000 Elo play.
    """
    # 1. Synchronize the virtual board state
    board = chess.Board()
    for move in moves_list:
        try:
            board.push_uci(move)
        except Exception:
            pass
            
    current_fen = board.fen()
    
    # 2. Extract Stockfish analytics from the Cloud Eval API
    # FIXED: Restored correct cloud eval path link
    cloud_url = "https://lichess.org/api/cloud-eval"
    params = {"fen": current_fen, "multiPv": 3}  # Access top 3 best moves
    
    try:
        response = requests.get(cloud_url, params=params)
        if response.status_code == 200:
            data = response.json()
            pvs = data.get("pvs", [])
            
            if pvs:
                # 2000 Elo Random Variance Factor
                dice_roll = random.random()
                
                if dice_roll > 0.85 and len(pvs) >= 3:
                    chosen_pv = pvs[2]  # Your fix kept: 3rd best move
                elif dice_roll > 0.70 and len(pvs) >= 2:
                    chosen_pv = pvs[1]  # Your fix kept: 2nd best move
                else:
                    chosen_pv = pvs[0]  # Your fix kept: 1st best move
                    
                best_move_line = chosen_pv.get("moves", "").split()
                if best_move_line:
                    return best_move_line[0]
    except Exception as e:
        print(f"Cloud Engine API communication error: {e}")

    # Fallback Protocol: If the position is rare, play a random legal move
    legal_moves = list(board.legal_moves)
    if legal_moves:
        return random.choice(legal_moves).uci()
        
    return "e2e4" 

def play_game(game_id):
    """Handles individual game streams in an isolated background thread."""
    print(f"\n[GAME START] Active match initialized: {game_id}")
    
    # FIXED: Restored correct game streaming sub-folders
    url = f"https://lichess.org/api/bot/game/stream/{game_id}"
    response = requests.get(url, headers=HEADERS, stream=True)
    
    bot_color = None

    for line in response.iter_lines():
        if not line:
            continue
            
        try:
            game_event = json.loads(line.decode('utf-8'))
        except Exception:
            continue

        if game_event.get('type') == 'gameFull':
            white_id = game_event['white'].get('id', '').lower()
            bot_color = 'white' if white_id == BOT_USERNAME.lower() else 'black'
            state = game_event['state']
            print(f"[{game_id}] Playing match as side: {bot_color.upper()}")
        
        elif game_event.get('type') == 'gameState':
            state = game_event
        else:
            continue

        moves_played = state['moves'].strip().split() if state['moves'].strip() else []
        total_moves = len(moves_played)

        is_bot_turn = (total_moves % 2 == 0 and bot_color == 'white') or \
                      (total_moves % 2 != 0 and bot_color == 'black')

        if is_bot_turn:
            print(f"[{game_id}] It is my turn to play. Computing 2000 Elo move...")
            bot_move = get_engine_move(moves_played, bot_color)
            make_lichess_move(game_id, bot_move)

def listen_to_events():
    """Main global event listener loop keeping the server 24/7 online."""
    print(f"Starting global event listener for user: {BOT_USERNAME}")
    # FIXED: Restored main global streaming link path
    url = "https://lichess.org/api/stream/event"
    
    response = requests.get(url, headers=HEADERS, stream=True)
    
    for line in response.iter_lines():
        if not line:
            continue
            
        try:
            event = json.loads(line.decode('utf-8'))
        except Exception:
            continue

        # Handle Incoming Challenges
        if event.get('type') == 'challenge':
            challenge_id = event['challenge']['id']
            print(f"[CHALLENGE] Received match request. Auto-accepting ID: {challenge_id}")
            # FIXED: Restored challenge acceptance folder path
            accept_url = f"https://lichess.org/api/challenge/{challenge_id}/accept"
            requests.post(accept_url, headers=HEADERS)

        # Handle Match Game Starts via Threads
        elif event.get('type') == 'gameStart':
            game_id = event['game']['id']
            game_thread = threading.Thread(target=play_game, args=(game_id,))
            game_thread.daemon = True
            game_thread.start()

if __name__ == "__main__":
    listen_to_events()
