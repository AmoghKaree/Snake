"""
25-Scenario Battlesnake Stress Suite
Organized in 5 batches of 5.  After each batch, failures are reported
so logic.py can be patched before moving on.

Usage:
  python simulate25.py [batch_number]   # run one batch (1-5)
  python simulate25.py all              # run all batches sequentially
"""

import random, sys, io, contextlib, heapq, copy
sys.path.insert(0, '.')
from logic import choose_move, manhattan

# ------------------------------------------------------------------
# OUTPUT SUPPRESSOR
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
# CONSTANTS
# ------------------------------------------------------------------
BOARD_W, BOARD_H = 11, 11
GAME_OBJ = {
    "id": "sim",
    "ruleset": {
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
# SNAKE FACTORIES
# ------------------------------------------------------------------
def make_snake(sid, name, x, y, color="#FF4444", health=100):
    body = [{"x": x, "y": y}] * 3
    return {"id": sid, "name": name, "latency": "0",
            "health": health, "body": body,
            "head": {"x": x, "y": y}, "length": 3,
            "shout": "", "squad": "",
            "customizations": {"color": color, "head": "default", "tail": "default"}}

def make_snake_long(sid, name, hx, hy, length, direction, color="#FF4444", health=100):
    """Snake with a real extended body instead of stacked head."""
    dx, dy = {"right": (-1, 0), "left": (1, 0),
               "up": (0, -1), "down": (0, 1)}[direction]
    body = [{"x": hx + dx*i, "y": hy + dy*i} for i in range(length)]
    # Clamp to board
    body = [{"x": max(0, min(10, p["x"])), "y": max(0, min(10, p["y"]))}
            for p in body]
    return {"id": sid, "name": name, "latency": "0",
            "health": health, "body": body,
            "head": body[0], "length": len(body),
            "shout": "", "squad": "",
            "customizations": {"color": color, "head": "default", "tail": "default"}}

# ------------------------------------------------------------------
# FOOD SPAWNER
# ------------------------------------------------------------------
def spawn_food(board, count=1, existing=None, snakes=None):
    occupied = set()
    if snakes:
        for s in snakes:
            for p in s["body"]:
                occupied.add((p["x"], p["y"]))
    food = list(existing or [])
    for f in food:
        occupied.add((f["x"], f["y"]))
    attempts = 0
    while len(food) - len(existing or []) < count and attempts < 500:
        attempts += 1
        x = random.randint(0, board["width"] - 1)
        y = random.randint(0, board["height"] - 1)
        if (x, y) not in occupied:
            food.append({"x": x, "y": y})
            occupied.add((x, y))
    return food

# ------------------------------------------------------------------
# OPPONENT AI IMPLEMENTATIONS
# ------------------------------------------------------------------
def ai_simple(sid, gs):
    """First safe move in [up, down, left, right] order."""
    board = gs["board"]
    snake = next(s for s in board["snakes"] if s["id"] == sid)
    occ   = {(p["x"], p["y"]) for s in board["snakes"] for p in s["body"]}
    for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),("left",(-1,0)),("right",(1,0))]:
        nx, ny = snake["head"]["x"]+dx, snake["head"]["y"]+dy
        if 0 <= nx < board["width"] and 0 <= ny < board["height"] and (nx,ny) not in occ:
            return move
    return "up"

def ai_random(sid, gs):
    """Random safe move."""
    board = gs["board"]
    snake = next(s for s in board["snakes"] if s["id"] == sid)
    occ   = {(p["x"], p["y"]) for s in board["snakes"] for p in s["body"]}
    safe  = []
    for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),("left",(-1,0)),("right",(1,0))]:
        nx, ny = snake["head"]["x"]+dx, snake["head"]["y"]+dy
        if 0 <= nx < board["width"] and 0 <= ny < board["height"] and (nx,ny) not in occ:
            safe.append(move)
    return random.choice(safe) if safe else "up"

def ai_hungry(sid, gs):
    """Greedily chases nearest food; falls back to simple."""
    board = gs["board"]
    snake = next(s for s in board["snakes"] if s["id"] == sid)
    head  = snake["head"]
    food  = board.get("food", [])
    if food:
        target = min(food, key=lambda f: manhattan(head, f))
        occ = {(p["x"], p["y"]) for s in board["snakes"] for p in s["body"]}
        best, bd = None, float("inf")
        for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),("left",(-1,0)),("right",(1,0))]:
            nx, ny = head["x"]+dx, head["y"]+dy
            if 0<=nx<board["width"] and 0<=ny<board["height"] and (nx,ny) not in occ:
                d = abs(nx-target["x"]) + abs(ny-target["y"])
                if d < bd:
                    bd, best = d, move
        if best:
            return best
    return ai_simple(sid, gs)

def ai_aggressive(sid, gs):
    """Tries to cut off enemies; falls back to simple."""
    board = gs["board"]
    snake = next(s for s in board["snakes"] if s["id"] == sid)
    head  = snake["head"]
    my_len = snake["length"]
    enemies = [s for s in board["snakes"] if s["id"] != sid]
    occ = {(p["x"], p["y"]) for s in board["snakes"] for p in s["body"]}
    # Find smaller enemy
    target = next((e for e in enemies if e["length"] < my_len), None)
    if target:
        th = target["head"]
        best, bd = None, float("inf")
        for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),("left",(-1,0)),("right",(1,0))]:
            nx, ny = head["x"]+dx, head["y"]+dy
            if 0<=nx<board["width"] and 0<=ny<board["height"] and (nx,ny) not in occ:
                d = abs(nx-th["x"]) + abs(ny-th["y"])
                if d < bd:
                    bd, best = d, move
        if best:
            return best
    return ai_hungry(sid, gs)

def ai_clone(sid, gs):
    """Uses our own logic — hardest opponent."""
    snake = next(s for s in gs["board"]["snakes"] if s["id"] == sid)
    with suppress_output():
        return choose_move({**gs, "you": snake})

AI_REGISTRY = {
    "simple": ai_simple, "random": ai_random,
    "hungry": ai_hungry, "aggressive": ai_aggressive, "clone": ai_clone,
}

# ------------------------------------------------------------------
# GAME STEP ENGINE
# ------------------------------------------------------------------
def step(gs, our_id, moves_dict):
    board  = gs["board"]
    snakes = board["snakes"]
    food   = board["food"]
    W, H   = board["width"], board["height"]
    turn   = gs["turn"] + 1

    deltas = {"up":(0,1),"down":(0,-1),"left":(-1,0),"right":(1,0)}
    new_heads = {}
    for s in snakes:
        mv = moves_dict.get(s["id"], "up")
        dx, dy = deltas[mv]
        new_heads[s["id"]] = {"x": s["head"]["x"]+dx, "y": s["head"]["y"]+dy}

    food_set = {(f["x"], f["y"]) for f in food}
    ate = {s["id"]: (new_heads[s["id"]]["x"], new_heads[s["id"]]["y"]) in food_set
           for s in snakes}

    new_bodies = {}
    for s in snakes:
        nh   = new_heads[s["id"]]
        body = [nh] + list(s["body"])
        if not ate[s["id"]]:
            body = body[:-1]
        new_bodies[s["id"]] = body

    eliminated = set()

    # Wall
    for s in snakes:
        nh = new_heads[s["id"]]
        if not (0 <= nh["x"] < W and 0 <= nh["y"] < H):
            eliminated.add(s["id"])

    # Body collision
    body_cells = {}
    for s in snakes:
        if s["id"] in eliminated:
            continue
        for i, part in enumerate(new_bodies[s["id"]]):
            if i == 0:
                continue
            body_cells.setdefault((part["x"], part["y"]), []).append(s["id"])

    for s in snakes:
        if s["id"] in eliminated:
            continue
        nh = new_heads[s["id"]]
        if (nh["x"], nh["y"]) in body_cells:
            eliminated.add(s["id"])

    # Head-to-head
    head_cells = {}
    for s in snakes:
        if s["id"] in eliminated:
            continue
        key = (new_heads[s["id"]]["x"], new_heads[s["id"]]["y"])
        head_cells.setdefault(key, []).append(s["id"])

    for pos, ids in head_cells.items():
        if len(ids) < 2:
            continue
        lengths = {sid: next(s["length"] for s in snakes if s["id"] == sid) for sid in ids}
        max_l   = max(lengths.values())
        for sid in ids:
            if lengths[sid] < max_l:
                eliminated.add(sid)
            elif sum(1 for l in lengths.values() if l == max_l) > 1:
                eliminated.add(sid)

    consumed = set()
    new_snake_list = []
    for s in snakes:
        if s["id"] in eliminated:
            continue
        nh  = new_heads[s["id"]]
        hp  = 100 if ate[s["id"]] else s["health"] - 1
        if ate[s["id"]]:
            consumed.add((nh["x"], nh["y"]))
        if hp <= 0:
            eliminated.add(s["id"])
            continue
        nb = new_bodies[s["id"]]
        new_snake_list.append({**s, "health": hp, "body": nb, "head": nh, "length": len(nb)})

    if our_id in eliminated:
        return None, turn

    remaining = [f for f in food if (f["x"], f["y"]) not in consumed]
    if len(remaining) < 1 or random.random() < 0.15:
        remaining = spawn_food(board, 1, remaining, new_snake_list)

    our = next(s for s in new_snake_list if s["id"] == our_id)
    new_board = {**board, "snakes": new_snake_list, "food": remaining}
    return {**gs, "turn": turn, "board": new_board, "you": our}, turn

# ------------------------------------------------------------------
# SCENARIO RUNNER
# ------------------------------------------------------------------
def run_scenario(name, seed, snake_cfgs, max_turns=250, verbose=True):
    """
    snake_cfgs: list of dicts with keys:
      id, name, snake (pre-built snake dict), is_ours, ai
    Returns (turns_survived, alive, reason)
    """
    random.seed(seed)

    snakes = [c["snake"] for c in snake_cfgs]
    our_id = next(c["id"] for c in snake_cfgs if c["is_ours"])
    ai_map = {c["id"]: c["ai"] for c in snake_cfgs}

    board = {"height": BOARD_H, "width": BOARD_W,
             "snakes": snakes, "food": [], "hazards": []}
    board["food"] = spawn_food(board, count=max(1, len(snakes)), snakes=snakes)

    our_snake  = next(s for s in snakes if s["id"] == our_id)
    game_state = {"game": GAME_OBJ, "turn": 0, "board": board, "you": our_snake}

    if verbose:
        others = [f"{c['name']}({c['ai']})" for c in snake_cfgs if not c["is_ours"]]
        print(f"\n{'='*64}")
        print(f"  {name}")
        print(f"  Opponents: [{', '.join(others) if others else 'none'}]")
        print(f"{'='*64}")

    for _ in range(max_turns):
        living = game_state["board"]["snakes"]
        if len(living) == 1 and living[0]["id"] == our_id:
            us = game_state["you"]
            if verbose:
                print(f"  WON at t={game_state['turn']}  len={us['length']}  hp={us['health']}")
            return game_state["turn"], True, "last_alive"

        moves = {}
        for s in living:
            if s["id"] == our_id:
                with suppress_output():
                    moves[s["id"]] = choose_move({**game_state, "you": s})
            else:
                fn = AI_REGISTRY.get(ai_map.get(s["id"], "simple"), ai_simple)
                moves[s["id"]] = fn(s["id"], game_state)

        game_state, turn = step(game_state, our_id, moves)

        if game_state is None:
            if verbose:
                print(f"  DIED  t={turn}")
            return turn, False, "eliminated"

        if verbose and game_state["turn"] % 50 == 0:
            us = game_state["you"]
            print(f"  t={game_state['turn']:3d}  hp={us['health']:3d}  "
                  f"len={us['length']:3d}  alive={len(game_state['board']['snakes'])}")

    us = game_state["you"]
    if verbose:
        print(f"  SURVIVED {max_turns}t  len={us['length']}  hp={us['health']}")
    return max_turns, True, "survived_limit"

# ------------------------------------------------------------------
# SNAKE CONFIG HELPERS
# ------------------------------------------------------------------
def us(sid="our", name="MoguzBot", x=1, y=9, health=100):
    return {"id": sid, "name": name, "snake": make_snake(sid, name, x, y, "#00FFFF", health),
            "is_ours": True, "ai": "self"}

def us_long(sid="our", name="MoguzBot", hx=5, hy=9, length=7,
            direction="right", health=100):
    return {"id": sid, "name": name,
            "snake": make_snake_long(sid, name, hx, hy, length, direction, "#00FFFF", health),
            "is_ours": True, "ai": "self"}

def enemy(sid, name, x, y, ai="simple", health=100):
    colors = {"simple":"#FF4444","random":"#FFAA00","hungry":"#FF88FF",
              "aggressive":"#FF0000","clone":"#AAFFAA"}
    col = colors.get(ai, "#888888")
    return {"id": sid, "name": name, "snake": make_snake(sid, name, x, y, col, health),
            "is_ours": False, "ai": ai}

def enemy_long(sid, name, hx, hy, length, direction, ai="simple", health=100):
    colors = {"simple":"#FF4444","hungry":"#FF88FF","clone":"#AAFFAA"}
    col = colors.get(ai, "#888888")
    return {"id": sid, "name": name,
            "snake": make_snake_long(sid, name, hx, hy, length, direction, col, health),
            "is_ours": False, "ai": ai}

# ------------------------------------------------------------------
# 25 SCENARIOS — 5 BATCHES OF 5
# ------------------------------------------------------------------

BATCHES = {

# ======================================================
# BATCH 1 — Core Survival
# ======================================================
1: [
    ("B1-S1: Solo 300-turn endurance",           11,
     [us(x=5,y=5)],                              300),

    ("B1-S2: 1v1 vs Simple (diagonal corners)",  12,
     [us(x=1,y=9), enemy("e1","SimpleA",9,1,"simple")], 250),

    ("B1-S3: 1v1 vs Hungry AI",                  13,
     [us(x=1,y=9), enemy("e1","HungryA",9,1,"hungry")], 250),

    ("B1-S4: 1v1 vs Clone AI (mirror match)",    14,
     [us(x=1,y=9), enemy("e1","CloneA",9,1,"clone")],   250),

    ("B1-S5: 1v1 vs Random AI",                  15,
     [us(x=1,y=9), enemy("e1","RandomA",9,1,"random")], 250),
],

# ======================================================
# BATCH 2 — Multi-Opponent
# ======================================================
2: [
    ("B2-S1: 3-snake vs 2 Simple AIs",           21,
     [us(x=1,y=9),
      enemy("e1","SimpleA",9,9,"simple"),
      enemy("e2","SimpleB",5,1,"simple")],        250),

    ("B2-S2: 3-snake vs Hungry + Clone",         22,
     [us(x=1,y=9),
      enemy("e1","HungryA",9,9,"hungry"),
      enemy("e2","CloneA",5,1,"clone")],          250),

    ("B2-S3: 4-snake all Simple (corners)",      23,
     [us(x=1,y=9),
      enemy("e1","SimpleA",9,9,"simple"),
      enemy("e2","SimpleB",1,1,"simple"),
      enemy("e3","SimpleC",9,1,"simple")],        250),

    ("B2-S4: 4-snake vs Hungry+Clone+Random",    24,
     [us(x=1,y=9),
      enemy("e1","HungryA",9,9,"hungry"),
      enemy("e2","CloneA",1,1,"clone"),
      enemy("e3","RandA",9,1,"random")],          250),

    ("B2-S5: 5-snake (4 Simple enemies)",        25,
     [us(x=5,y=9),
      enemy("e1","S1",1,9,"simple"),
      enemy("e2","S2",9,9,"simple"),
      enemy("e3","S3",1,1,"simple"),
      enemy("e4","S4",9,1,"simple")],             250),
],

# ======================================================
# BATCH 3 — Edge Conditions
# ======================================================
3: [
    ("B3-S1: Starvation start (hp=20)",          31,
     [us(x=5,y=5,health=20),
      enemy("e1","SimpleA",1,1,"simple"),
      enemy("e2","SimpleB",9,9,"simple")],        250),

    ("B3-S2: Corner trap — us in corner, enemy nearby",  32,
     [us(x=0,y=0),
      enemy("e1","AggA",2,0,"aggressive"),
      enemy("e2","AggB",0,2,"aggressive")],       250),

    ("B3-S3: We start longer (len=7 vs len=3)",  33,
     [us_long("our","MoguzBot",5,9,7,"right"),
      enemy("e1","SimpleA",1,1,"simple"),
      enemy("e2","SimpleB",9,1,"simple")],        250),

    ("B3-S4: Surrounded — 3 enemies on adjacent sides",  34,
     [us(x=5,y=5),
      enemy("e1","SA",5,7,"simple"),
      enemy("e2","SB",7,5,"simple"),
      enemy("e3","SC",5,3,"simple")],             250),

    ("B3-S5: Low-health recovery (hp=15)",        35,
     [us(x=5,y=5,health=15),
      enemy("e1","SimpleA",9,9,"simple")],        250),
],

# ======================================================
# BATCH 4 — Strategic Depth
# ======================================================
4: [
    ("B4-S1: Kill opportunity — we're longer",   41,
     [us_long("our","MoguzBot",1,9,6,"right"),
      enemy("e1","SmallA",9,9,"simple"),
      enemy("e2","SmallB",9,1,"simple")],         250),

    ("B4-S2: Enemy longer — must avoid kills",   42,
     [us(x=5,y=5),
      enemy_long("e1","BigA",1,9,8,"right","hungry"),
      enemy_long("e2","BigB",9,9,8,"left","simple")], 250),

    ("B4-S3: Long endurance solo (400t)",        43,
     [us(x=5,y=5)],                              400),

    ("B4-S4: 2v1 — two equal enemies",           44,
     [us(x=5,y=5),
      enemy("e1","MidA",2,9,"hungry"),
      enemy("e2","MidB",8,9,"hungry")],           250),

    ("B4-S5: Clone duel center — both hp=100",   45,
     [us(x=3,y=5),
      enemy("e1","CloneA",7,5,"clone")],          250),
],

# ======================================================
# BATCH 5 — Adversarial / Advanced
# ======================================================
5: [
    ("B5-S1: 4 Clones vs us",                   52,
     [us(x=5,y=5),
      enemy("e1","ClA",1,9,"clone"),
      enemy("e2","ClB",9,9,"clone"),
      enemy("e3","ClC",1,1,"clone"),
      enemy("e4","ClD",9,1,"clone")],             250),

    ("B5-S2: 3 Aggressive enemies",              52,
     [us(x=5,y=5),
      enemy("e1","AggA",1,9,"aggressive"),
      enemy("e2","AggB",9,9,"aggressive"),
      enemy("e3","AggC",9,1,"aggressive")],       250),

    ("B5-S3: Outnumbered — large enemies",       53,
     [us(x=5,y=5),
      enemy_long("e1","BigA",1,9,7,"right","hungry"),
      enemy_long("e2","BigB",9,9,7,"left","hungry")], 250),

    ("B5-S4: Chaos — 4 enemies mixed AIs",      54,
     [us(x=5,y=9),
      enemy("e1","CloA",1,9,"clone"),
      enemy("e2","HngA",9,9,"hungry"),
      enemy("e3","AggA",1,1,"aggressive"),
      enemy("e4","RndA",9,1,"random")],           250),

    ("B5-S5: Late-game — both grown (len=8)",    55,
     [us_long("our","MoguzBot",1,9,8,"right"),
      enemy_long("e1","CloneA",9,9,8,"left","clone")], 250),
],
}

# PASS condition: survived > 50 turns OR won
def passed(turns, alive):
    return alive or turns >= 50

# ------------------------------------------------------------------
# BATCH RUNNER
# ------------------------------------------------------------------
def run_batch(batch_num, verbose=True):
    scenarios = BATCHES[batch_num]
    results   = []
    print(f"\n{'#'*64}")
    print(f"#  BATCH {batch_num}  ({len(scenarios)} scenarios)")
    print(f"{'#'*64}")

    for name, seed, cfgs, max_t in scenarios:
        random.seed(seed)
        turns, alive, reason = run_scenario(name, seed, cfgs, max_t, verbose)
        ok = passed(turns, alive)
        results.append((name, turns, alive, reason, ok))

    print(f"\n{'='*64}")
    print(f"  BATCH {batch_num} SUMMARY")
    print(f"{'='*64}")
    passes = 0
    for name, turns, alive, reason, ok in results:
        tag  = "PASS" if ok else "FAIL"
        fate = "alive" if alive else "dead "
        print(f"  {tag}  {name:<46}  t={turns:4d}  {fate}  ({reason})")
        if ok:
            passes += 1
    print(f"{'='*64}")
    print(f"  {passes}/{len(scenarios)} passed in batch {batch_num}")
    print(f"{'='*64}")
    return results

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    if arg == "all":
        all_results = {}
        for b in range(1, 6):
            all_results[b] = run_batch(b)
        print(f"\n{'#'*64}")
        print("#  OVERALL RESULTS")
        print(f"{'#'*64}")
        total_pass = 0
        for b, res in all_results.items():
            p = sum(1 for _,_,_,_,ok in res if ok)
            total_pass += p
            print(f"  Batch {b}: {p}/{len(res)}")
        print(f"  Total: {total_pass}/25")
        print(f"{'#'*64}")
    else:
        run_batch(int(arg))
