"""
Battlesnake Local Game Simulator  — 10-scenario stress test
Opponents:
  simple   : first safe move in [up,down,left,right] order
  random   : random safe move
  hungry   : always moves toward nearest food
  clone    : uses our own choose_move logic (mirror match)
"""

import random
import sys
import os
import io
import contextlib
import heapq

sys.path.insert(0, os.path.dirname(__file__))
from logic import choose_move, get_next_coord, manhattan

# ------------------------------------------------------------------
#  SUPPRESS logic.py PRINT OUTPUT DURING SIMULATION
# ------------------------------------------------------------------

@contextlib.contextmanager
def suppress_output():
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


# ------------------------------------------------------------------
#  CONSTANTS
# ------------------------------------------------------------------

BOARD_W = 11
BOARD_H = 11
GAME_OBJ = {
    "id": "sim", "ruleset": {
        "name": "standard", "version": "cli",
        "settings": {
            "foodSpawnChance": 15, "minimumFood": 1,
            "hazardDamagePerTurn": 0, "hazardMap": "", "hazardMapAuthor": "",
            "royale": {"shrinkEveryNTurns": 25},
            "squad": {"allowBodyCollisions": False, "sharedElimination": False,
                      "sharedHealth": False, "sharedLength": False}
        }
    }, "map": "standard", "timeout": 5000, "source": ""
}


# ------------------------------------------------------------------
#  OPPONENT AI IMPLEMENTATIONS
# ------------------------------------------------------------------

def ai_simple(snake_id, game_state):
    """Always picks first safe move in [up,down,left,right] order."""
    board = game_state['board']
    snake = next(s for s in board['snakes'] if s['id'] == snake_id)
    head  = snake['head']
    occupied = {(p['x'], p['y']) for s in board['snakes'] for p in s['body']}
    for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),
                            ("left",(-1,0)),("right",(1,0))]:
        nx, ny = head['x'] + dx, head['y'] + dy
        if 0 <= nx < board['width'] and 0 <= ny < board['height'] \
                and (nx, ny) not in occupied:
            return move
    return "up"


def ai_random(snake_id, game_state):
    """Picks a random safe move."""
    board = game_state['board']
    snake = next(s for s in board['snakes'] if s['id'] == snake_id)
    head  = snake['head']
    occupied = {(p['x'], p['y']) for s in board['snakes'] for p in s['body']}
    safe = []
    for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),
                            ("left",(-1,0)),("right",(1,0))]:
        nx, ny = head['x'] + dx, head['y'] + dy
        if 0 <= nx < board['width'] and 0 <= ny < board['height'] \
                and (nx, ny) not in occupied:
            safe.append(move)
    return random.choice(safe) if safe else "up"


def ai_hungry(snake_id, game_state):
    """Greedily moves toward nearest food; falls back to simple."""
    board = game_state['board']
    snake = next(s for s in board['snakes'] if s['id'] == snake_id)
    head  = snake['head']
    food  = board.get('food', [])

    if food:
        # Find food with minimum Manhattan distance
        target = min(food, key=lambda f: manhattan(head, f))
        # Pick the move that reduces distance most
        occupied = {(p['x'], p['y']) for s in board['snakes'] for p in s['body']}
        best_move, best_dist = None, float('inf')
        for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),
                                ("left",(-1,0)),("right",(1,0))]:
            nx, ny = head['x'] + dx, head['y'] + dy
            if 0 <= nx < board['width'] and 0 <= ny < board['height'] \
                    and (nx, ny) not in occupied:
                d = abs(nx - target['x']) + abs(ny - target['y'])
                if d < best_dist:
                    best_dist, best_move = d, move
        if best_move:
            return best_move

    return ai_simple(snake_id, game_state)


def ai_clone(snake_id, game_state):
    """Uses our own choose_move logic — mirror match."""
    snake    = next(s for s in game_state['board']['snakes'] if s['id'] == snake_id)
    gs_clone = {**game_state, "you": snake}
    with suppress_output():
        return choose_move(gs_clone)


AI_REGISTRY = {
    "simple": ai_simple,
    "random": ai_random,
    "hungry": ai_hungry,
    "clone":  ai_clone,
}


# ------------------------------------------------------------------
#  GAME STATE HELPERS
# ------------------------------------------------------------------

def make_snake(sid, name, x, y, color="#FF4444", health=100):
    body = [{"x": x, "y": y}] * 3
    return {
        "id": sid, "name": name, "latency": "0",
        "health": health,
        "body": body, "head": {"x": x, "y": y}, "length": 3,
        "shout": "", "squad": "",
        "customizations": {"color": color, "head": "default", "tail": "default"}
    }


def spawn_food(board, count=1, existing=None, snakes=None):
    occupied = set()
    if snakes:
        for s in snakes:
            for p in s['body']:
                occupied.add((p['x'], p['y']))
    food = list(existing or [])
    for f in food:
        occupied.add((f['x'], f['y']))
    attempts = 0
    while len(food) - len(existing or []) < count and attempts < 400:
        attempts += 1
        x = random.randint(0, board['width'] - 1)
        y = random.randint(0, board['height'] - 1)
        if (x, y) not in occupied:
            food.append({"x": x, "y": y})
            occupied.add((x, y))
    return food


def make_initial_state(snake_configs):
    """
    snake_configs: list of (id, name, x, y, is_ours, color, ai_name, start_health)
    """
    snakes = []
    for cfg in snake_configs:
        sid, name, x, y, _, color, _, hp = cfg
        snakes.append(make_snake(sid, name, x, y, color, hp))

    board = {
        "height": BOARD_H, "width": BOARD_W,
        "snakes": snakes, "food": [], "hazards": []
    }
    board["food"] = spawn_food(board, count=max(1, len(snakes)), snakes=snakes)

    our_id    = next(c[0] for c in snake_configs if c[4])
    our_snake = next(s for s in snakes if s['id'] == our_id)
    return {"game": GAME_OBJ, "turn": 0, "board": board, "you": our_snake}


# ------------------------------------------------------------------
#  GAME STEP ENGINE
# ------------------------------------------------------------------

def step(game_state, our_id, moves_dict):
    """Advance by one turn. Returns (new_state, turn) or (None, turn_died)."""
    board  = game_state['board']
    snakes = board['snakes']
    food   = board['food']
    width, height = board['width'], board['height']
    turn   = game_state['turn'] + 1

    deltas = {"up":(0,1),"down":(0,-1),"left":(-1,0),"right":(1,0)}

    # New head positions
    new_heads = {s['id']: {
        "x": s['head']['x'] + deltas[moves_dict.get(s['id'], "up")][0],
        "y": s['head']['y'] + deltas[moves_dict.get(s['id'], "up")][1]
    } for s in snakes}

    # Did we eat?
    food_set = {(f['x'], f['y']) for f in food}
    ate = {s['id']: (new_heads[s['id']]['x'], new_heads[s['id']]['y']) in food_set
           for s in snakes}

    # New bodies
    new_bodies = {}
    for s in snakes:
        nh = new_heads[s['id']]
        body = [nh] + list(s['body'])
        if not ate[s['id']]:
            body = body[:-1]
        new_bodies[s['id']] = body

    eliminated = set()

    # 1. Wall collision
    for s in snakes:
        nh = new_heads[s['id']]
        if not (0 <= nh['x'] < width and 0 <= nh['y'] < height):
            eliminated.add(s['id'])

    # 2. Body collision (head into any non-head body segment)
    body_cells = {}
    for s in snakes:
        if s['id'] in eliminated:
            continue
        for i, part in enumerate(new_bodies[s['id']]):
            if i == 0:
                continue   # skip own new head
            key = (part['x'], part['y'])
            body_cells.setdefault(key, []).append(s['id'])

    for s in snakes:
        if s['id'] in eliminated:
            continue
        nh = new_heads[s['id']]
        if (nh['x'], nh['y']) in body_cells:
            eliminated.add(s['id'])

    # 3. Head-to-head: shorter (or tied) snake dies
    head_cells = {}
    for s in snakes:
        if s['id'] in eliminated:
            continue
        key = (new_heads[s['id']]['x'], new_heads[s['id']]['y'])
        head_cells.setdefault(key, []).append(s['id'])

    for pos, ids in head_cells.items():
        if len(ids) < 2:
            continue
        lengths = {sid: next(s['length'] for s in snakes if s['id'] == sid)
                   for sid in ids}
        max_len = max(lengths.values())
        for sid in ids:
            if lengths[sid] < max_len:
                eliminated.add(sid)
            elif sum(1 for l in lengths.values() if l == max_len) > 1:
                eliminated.add(sid)   # tie — both die

    # Build surviving snake list
    consumed = set()
    new_snake_list = []
    for s in snakes:
        if s['id'] in eliminated:
            continue
        nh = new_heads[s['id']]
        new_health = 100 if ate[s['id']] else s['health'] - 1
        if ate[s['id']]:
            consumed.add((nh['x'], nh['y']))
        if new_health <= 0:
            eliminated.add(s['id'])
            continue
        nb = new_bodies[s['id']]
        new_snake_list.append({
            **s,
            "health": new_health,
            "body": nb, "head": nh, "length": len(nb)
        })

    if our_id in eliminated:
        return None, turn

    # Update food
    remaining_food = [f for f in food if (f['x'], f['y']) not in consumed]
    if len(remaining_food) < 1 or random.random() < 0.15:
        remaining_food = spawn_food(board, count=1,
                                    existing=remaining_food,
                                    snakes=new_snake_list)

    our_snake = next(s for s in new_snake_list if s['id'] == our_id)
    new_board = {**board, "snakes": new_snake_list, "food": remaining_food}
    new_state = {**game_state, "turn": turn, "board": new_board, "you": our_snake}
    return new_state, turn


# ------------------------------------------------------------------
#  SCENARIO RUNNER
# ------------------------------------------------------------------

def run_simulation(scenario_name, snake_configs, max_turns=200, verbose=True):
    """
    snake_configs: list of (id, name, x, y, is_ours, color, ai_name, start_health)
    Returns (survived_turns, alive_at_end, reason)
    """
    our_id    = next(c[0] for c in snake_configs if c[4])
    ai_map    = {c[0]: c[6] for c in snake_configs}   # id -> ai name
    game_state = make_initial_state(snake_configs)

    if verbose:
        n_enemies = len(snake_configs) - 1
        ai_names  = [f"{c[1]}({c[6]})" for c in snake_configs if not c[4]]
        print(f"\n{'='*62}")
        print(f"  {scenario_name}")
        print(f"  Enemies: {n_enemies}  [{', '.join(ai_names)}]")
        print(f"{'='*62}")

    for _ in range(max_turns):
        board  = game_state['board']
        snakes = board['snakes']

        moves_dict = {}
        for s in snakes:
            ai_name = ai_map.get(s['id'], 'simple')
            if s['id'] == our_id:
                gs_for_us = {**game_state, "you": s}
                with suppress_output():
                    moves_dict[s['id']] = choose_move(gs_for_us)
            else:
                ai_fn = AI_REGISTRY.get(ai_name, ai_simple)
                moves_dict[s['id']] = ai_fn(s['id'], game_state)

        game_state, turn = step(game_state, our_id, moves_dict)

        if game_state is None:
            if verbose:
                print(f"  DIED on turn {turn}")
            return turn, False, "eliminated"

        living = game_state['board']['snakes']

        if len(living) == 1 and living[0]['id'] == our_id:
            if verbose:
                us = game_state['you']
                print(f"  WON (last snake) at turn {turn}  len={us['length']}  hp={us['health']}")
            return turn, True, "last_alive"

        if verbose and game_state['turn'] % 25 == 0:
            us = game_state['you']
            print(f"  t={game_state['turn']:3d}  hp={us['health']:3d}  "
                  f"len={us['length']:3d}  alive={len(living)}")

    us = game_state['you']
    if verbose:
        print(f"  SURVIVED {max_turns} turns  len={us['length']}  hp={us['health']}")
    return max_turns, True, "survived_limit"


# ------------------------------------------------------------------
#  10 SCENARIOS  (diverse seeds, opponents, starting configs)
# ------------------------------------------------------------------

SCENARIOS = [
    # (name, seed, configs)
    # cfg tuple: (id, name, x, y, is_ours, color, ai_name, start_health)

    (
        "1. Solo endurance (200t)",
        10,
        [("our", "MoguzBot", 5, 5, True, "#00FFFF", "simple", 100)]
    ),
    (
        "2. 1v1 vs Simple AI — diagonal corners",
        20,
        [
            ("our",  "MoguzBot", 1,  9, True,  "#00FFFF", "simple", 100),
            ("e1",   "SimpleA",  9,  1, False, "#FF4444", "simple", 100),
        ]
    ),
    (
        "3. 1v1 vs Hungry AI — both chase food",
        30,
        [
            ("our",  "MoguzBot", 1, 9, True,  "#00FFFF", "simple", 100),
            ("e1",   "HungryA",  9, 1, False, "#FF8800", "hungry", 100),
        ]
    ),
    (
        "4. 1v1 vs Clone AI — mirror match",
        40,
        [
            ("our",  "MoguzBot", 1, 9, True,  "#00FFFF", "simple", 100),
            ("e1",   "CloneA",   9, 1, False, "#AAFFAA", "clone",  100),
        ]
    ),
    (
        "5. 3-snake vs 2 Simple AIs",
        50,
        [
            ("our",  "MoguzBot", 1, 9, True,  "#00FFFF", "simple", 100),
            ("e1",   "SimpleA",  9, 9, False, "#FF4444", "simple", 100),
            ("e2",   "SimpleB",  5, 1, False, "#FF88FF", "simple", 100),
        ]
    ),
    (
        "6. 3-snake vs Hungry + Random",
        60,
        [
            ("our",  "MoguzBot", 1, 9, True,  "#00FFFF", "simple", 100),
            ("e1",   "HungryA",  9, 9, False, "#FF4444", "hungry", 100),
            ("e2",   "RandomB",  5, 1, False, "#FFFF00", "random", 100),
        ]
    ),
    (
        "7. 4-snake standard positions (all Simple)",
        70,
        [
            ("our",  "MoguzBot", 1, 9, True,  "#00FFFF", "simple", 100),
            ("e1",   "SimpleA",  9, 9, False, "#FF4444", "simple", 100),
            ("e2",   "SimpleB",  1, 1, False, "#FF88FF", "simple", 100),
            ("e3",   "SimpleC",  9, 1, False, "#FFAA00", "simple", 100),
        ]
    ),
    (
        "8. 4-snake vs Hungry + 2 Clones",
        80,
        [
            ("our",  "MoguzBot", 1,  9, True,  "#00FFFF", "simple", 100),
            ("e1",   "HungryA",  9,  9, False, "#FF4444", "hungry", 100),
            ("e2",   "CloneB",   1,  1, False, "#AAFFAA", "clone",  100),
            ("e3",   "CloneC",   9,  1, False, "#AAAAFF", "clone",  100),
        ]
    ),
    (
        "9. Starvation pressure (health=30 at start)",
        90,
        [
            ("our",  "MoguzBot", 5, 5, True,  "#00FFFF", "simple", 30),
            ("e1",   "SimpleA",  1, 1, False, "#FF4444", "simple", 100),
            ("e2",   "SimpleB",  9, 9, False, "#FF88FF", "simple", 100),
        ]
    ),
    (
        "10. Center duel vs Clone (symmetric)",
        100,
        [
            ("our",  "MoguzBot", 3, 5, True,  "#00FFFF", "simple", 100),
            ("e1",   "CloneA",   7, 5, False, "#AAFFAA", "clone",  100),
        ]
    ),
]


# ------------------------------------------------------------------
#  MAIN
# ------------------------------------------------------------------

if __name__ == "__main__":
    TARGET    = 50   # survive past 50 turns (or win before)
    passes    = 0
    results   = []

    for name, seed, configs in SCENARIOS:
        random.seed(seed)
        turns, alive, reason = run_simulation(name, configs, max_turns=200)
        passed = alive or turns >= TARGET
        if passed:
            passes += 1
        results.append((name, turns, alive, reason, passed))

    print("\n" + "="*62)
    print("  FINAL RESULTS")
    print("="*62)
    for name, turns, alive, reason, passed in results:
        status = "PASS" if passed else "FAIL"
        fate   = "alive" if alive else "dead "
        print(f"  {status}  {name:<44}  t={turns:4d}  {fate}  ({reason})")
    print("="*62)
    print(f"  {passes}/{len(SCENARIOS)} scenarios passed (target: alive or >=50t)")
    print("="*62)

    if passes >= 8:
        print(f"\n  SUCCESS: {passes}/10 passed!")
        sys.exit(0)
    else:
        print(f"\n  Needs work: only {passes}/10 passed.")
        sys.exit(1)
