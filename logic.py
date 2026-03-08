import math
import time
import heapq
from collections import deque

# =================================================================
#  OPPONENT PROFILER STATE
#
#  Persists across HTTP requests for the lifetime of the process.
#  Keyed: profile_state[game_id][snake_id] = profile_dict
#
#  Each profile_dict is a small fixed-size dict — O(1) memory per
#  snake, O(1) update per turn. No historical board states stored.
# =================================================================

profile_state: dict = {}   # { game_id: { snake_id: profile_dict } }

_PROFILE_MIN_TURNS  = 15   # turns required before any archetype is assigned
_INTERACTION_RADIUS = 6    # manhattan distance; overlay inactive beyond this


def _get_or_init_profile(game_id: str, snake_id: str) -> dict:
    """Return (creating if absent) the mutable profile for one snake in one game."""
    if game_id not in profile_state:
        profile_state[game_id] = {}
    game = profile_state[game_id]
    if snake_id not in game:
        game[snake_id] = {
            'turn_count':       0,
            'prev_head':        None,
            'prev_food_dist':   None,    # closest food manhattan dist last turn
            'prev_thunga_dist': None,    # manhattan dist to our head last turn
            # Behaviour counters — integers, O(1) update
            'vacuum_count':     0,       # moved toward closest food
            'wall_count':       0,       # head on board perimeter
            'aggro_count':      0,       # chased Thunga while ignoring food
            'center_count':     0,       # head inside central 5×5 region
            # Classification output
            'archetype':        None,
            'confidence':       0.0,
        }
    return game[snake_id]


def _classify_archetype(p: dict):
    """
    Pure function: given a completed profile dict, return (archetype, confidence).
    Returns (None, 0.0) when fewer than _PROFILE_MIN_TURNS turns have been seen.
    Precedence order: vacuum → camper → aggressor → area_control → erratic.
    """
    n = p['turn_count']
    if n < _PROFILE_MIN_TURNS:
        return (None, 0.0)

    v = p['vacuum_count'] / n    # ratio: moved toward food
    w = p['wall_count']   / n    # ratio: head on perimeter
    a = p['aggro_count']  / n    # ratio: chased Thunga (ignoring food)
    c = p['center_count'] / n    # ratio: head in centre region

    if v > 0.85: return ('vacuum',       v)
    if w > 0.80: return ('camper',       w)
    if a > 0.60: return ('aggressor',    a)
    if c > 0.75: return ('area_control', c)

    # Erratic: no single metric reaches 50% — confidence rises as max falls
    max_ratio = max(v, w, a, c)
    if max_ratio < 0.50:
        return ('erratic', 1.0 - max_ratio)

    return (None, 0.0)   # ambiguous — insufficient signal


def update_profiles(game_state: dict, start_time: float = 0.0) -> None:
    """
    Update every enemy snake's profile for the current turn.
    Called ONCE at the very top of choose_best_move.
    Complexity: O(E × F) — enemy count × food count, both tiny constants.

    start_time: value of time.perf_counter() at the start of choose_move.
    If the 50ms profiling budget is exhausted, the loop aborts early and
    retains each snake's previous profile data unchanged.
    """
    game_id   = game_state['game']['id']
    board     = game_state['board']
    bw        = board['width']
    bh        = board['height']
    cx        = bw // 2          # board centre x
    cy        = bh // 2          # board centre y
    my_snake  = game_state['you']
    my_head   = my_snake['head']
    my_length = my_snake['length']
    food_list = board['food']

    for snake in board['snakes']:
        if snake['id'] == my_snake['id']:
            continue

        # ── Time-Cop (50ms profiling budget) ─────────────────────────
        # All metrics are pure manhattan math, so this guard only fires
        # if there are an unusual number of snakes or the server is under
        # load. Old profile data is kept intact for any skipped snakes.
        if time.perf_counter() - start_time > 0.050:
            break

        p  = _get_or_init_profile(game_id, snake['id'])
        hx = snake['head']['x']
        hy = snake['head']['y']

        # ── Compute current-turn metrics ──────────────────────────────
        cur_food_dist = min(
            (abs(hx - f['x']) + abs(hy - f['y']) for f in food_list),
            default=999
        )
        cur_thunga_dist = abs(hx - my_head['x']) + abs(hy - my_head['y'])

        # ── Increment counters (only once we have a prior observation) ─
        if p['prev_head'] is not None:
            moved_toward_food   = (cur_food_dist   < p['prev_food_dist'])
            moved_toward_thunga = (cur_thunga_dist < p['prev_thunga_dist'])
            is_larger           = (snake['length'] > my_length)

            # Vacuum: closed gap to nearest food
            if moved_toward_food:
                p['vacuum_count'] += 1

            # Camper: head on board perimeter
            if hx == 0 or hx == bw - 1 or hy == 0 or hy == bh - 1:
                p['wall_count'] += 1

            # Aggressor: moved toward Thunga, ignored food, and is bigger
            if moved_toward_thunga and not moved_toward_food and is_larger:
                p['aggro_count'] += 1

            # Area-Control: head in central 5×5 (scales with board size)
            if (cx - 2 <= hx <= cx + 2) and (cy - 2 <= hy <= cy + 2):
                p['center_count'] += 1

            p['turn_count'] += 1

        # ── Persist state for next turn ───────────────────────────────
        p['prev_head']        = {'x': hx, 'y': hy}
        p['prev_food_dist']   = cur_food_dist
        p['prev_thunga_dist'] = cur_thunga_dist

        # ── Reclassify every turn with latest data ────────────────────
        archetype, confidence = _classify_archetype(p)
        p['archetype']        = archetype
        p['confidence']       = confidence


def get_game_profiles(game_state: dict) -> dict:
    """Return the full {snake_id: profile} map for the current game."""
    return profile_state.get(game_state['game']['id'], {})


# =================================================================
#  ENTRY POINT
# =================================================================

def choose_move(data):
    # Clock starts the instant the request is received — everything
    # downstream is measured against this single reference point.
    start_time = time.perf_counter()
    return choose_best_move(data, start_time=start_time)


# =================================================================
#  BOARD VISUALIZER
# =================================================================

def print_board(game_state):
    board      = game_state['board']
    my_snake   = game_state['you']
    width      = board['width']
    height     = board['height']

    grid = [["." for _ in range(width)] for _ in range(height)]

    for food in board['food']:
        grid[food['y']][food['x']] = "F"

    for snake in board['snakes']:
        if snake['id'] == my_snake['id']:
            continue
        for part in snake['body']:
            grid[part['y']][part['x']] = "e"
        grid[snake['head']['y']][snake['head']['x']] = "E"

    for part in my_snake['body']:
        grid[part['y']][part['x']] = "s"
    grid[my_snake['head']['y']][my_snake['head']['x']] = "S"

    print("\n" + "=" * (width * 2))
    for row in reversed(grid):
        print(" ".join(row))
    print("=" * (width * 2))
    print(f"  Turn: {game_state['turn']}  |  Health: {my_snake['health']}  |  Length: {my_snake['length']}  |  Snakes alive: {len(board['snakes'])}")
    print("=" * (width * 2))
    print("  S=you  s=body  E=enemy  e=enemy body  F=food")


# =================================================================
#  MAIN DECISION FUNCTION
# =================================================================

DEBUG = False   # Set True locally; never True in production


def choose_best_move(game_state, start_time: float = 0.0):

    print_board(game_state)

    # ── PROFILER: update observations before any decision is made ────
    # Pass start_time so the profiler can self-abort at its 50ms budget.
    update_profiles(game_state, start_time=start_time)
    game_profiles = get_game_profiles(game_state)

    safe_moves = get_safe_moves(game_state)
    in_risky_fallback = False

    if not safe_moves:
        # Absolute fallback — all moves hit walls or bodies
        return "up"

    all_moves = ["up", "down", "left", "right"]
    my_head   = game_state['you']['head']
    board_w   = game_state['board']['width']
    board_h   = game_state['board']['height']
    my_length = game_state['you']['length']

    occupied = set()
    for snake in game_state['board']['snakes']:
        tail_stays = _tail_will_stay(snake, game_state['board'])
        for i, part in enumerate(snake['body']):
            if not tail_stays and i == len(snake['body']) - 1:
                continue
            occupied.add((part['x'], part['y']))

    danger_squares = set()
    for snake in game_state['board']['snakes']:
        if snake['id'] == game_state['you']['id']:
            continue
        if snake['length'] >= my_length:
            for move in all_moves:
                nc = get_next_coord(snake['head'], move)
                nx, ny = nc['x'], nc['y']
                if 0 <= nx < board_w and 0 <= ny < board_h:
                    danger_squares.add((nx, ny))

    truly_safe = []
    for move in all_moves:
        nc = get_next_coord(my_head, move)
        nx, ny = nc['x'], nc['y']
        if not (0 <= nx < board_w and 0 <= ny < board_h):
            continue
        if (nx, ny) in occupied:
            continue
        if (nx, ny) not in danger_squares:
            truly_safe.append(move)

    in_risky_fallback = (len(truly_safe) == 0)

    best_move     = safe_moves[0]   # guaranteed safe fallback if we time out
    highest_score = -math.inf

    for move in safe_moves:
        # ── Time-Cop (200ms hard deadline) ───────────────────────────
        # Check BEFORE each evaluate_move call (which contains A* and
        # Voronoi — the two most expensive operations). If we're past the
        # deadline, immediately return the best move scored so far.
        # best_move is pre-seeded to safe_moves[0], so we always return
        # something valid even if not a single move was fully evaluated.
        elapsed = time.perf_counter() - start_time
        if elapsed > 0.200:
            print(f"WARNING: Time cutoff reached at {elapsed*1000:.1f}ms, "
                  f"aborting deep evaluation (returning '{best_move}')")
            return best_move

        score = evaluate_move(move, game_state,
                              in_risky_fallback=in_risky_fallback,
                              profiles=game_profiles)
        if DEBUG:
            print(f"  {move:5} -> {score:.2f}")
        if score > highest_score:
            highest_score = score
            best_move     = move

    if DEBUG:
        print(f"  Chosen: {best_move}\n")
    return best_move


# =================================================================
#  TAIL-VACATING HELPER
# =================================================================

def _tail_will_stay(snake, board):
    """
    Returns True if this snake's tail will NOT vacate this turn.
    Only case we can guarantee: snake just ate (health == 100) — body
    grows, tail doesn't move.
    """
    return snake['health'] == 100


# =================================================================
#  BOX-OUT DETECTOR  (O(1) geometry helper)
# =================================================================

def _detect_box_out(next_head, enemy, my_length, board_w, board_h):
    """
    Purely geometric (O(1)) test for a Wall-Pin opportunity.

    An enemy is pinnable when ALL of the following hold:

      1. Their head is on the board perimeter.
      2. They are moving PARALLEL to that wall — inferred from the
         head-to-body[1] delta, which is the direction they arrived from.
      3. Thunga's candidate next_head occupies the "inner lane": exactly
         1 tile inward from the enemy's projected next position.
      4. Thunga is strictly LONGER than the enemy, preventing the enemy
         from simply turning inward and winning a head-to-head.

    Returns (True, projected_enemy_pos_dict) when all conditions hold,
    otherwise (False, None).  No BFS, no heap — pure arithmetic.
    """
    # Condition 4: must be strictly longer — no suicidal head-to-heads
    if my_length <= enemy['length']:
        return False, None

    ehx = enemy['head']['x']
    ehy = enemy['head']['y']

    # Condition 1: enemy head on the perimeter
    on_left   = (ehx == 0)
    on_right  = (ehx == board_w - 1)
    on_bottom = (ehy == 0)
    on_top    = (ehy == board_h - 1)

    if not (on_left or on_right or on_bottom or on_top):
        return False, None

    # Need at least 2 body segments to infer direction
    if len(enemy['body']) < 2:
        return False, None

    b1 = enemy['body'][1]           # the segment the head just left
    dx = ehx - b1['x']             # +1=right, -1=left, 0=no x-movement
    dy = ehy - b1['y']             # +1=up,    -1=down,  0=no y-movement

    # Condition 2: moving PARALLEL to the wall they are pressed against.
    # Left/right wall → parallel means moving vertically (dx==0, dy!=0).
    # Top/bottom wall → parallel means moving horizontally (dy==0, dx!=0).
    parallel = (
        ((on_left or on_right)  and dx == 0 and dy != 0) or
        ((on_top  or on_bottom) and dy == 0 and dx != 0)
    )
    if not parallel:
        return False, None

    # Enemy's projected next position (stays on the perimeter)
    enx = ehx + dx
    eny = ehy + dy

    # Condition 3: next_head is exactly 1 tile inward from that projection.
    # "Inward" is always toward the board centre from the wall axis.
    nhx = next_head['x']
    nhy = next_head['y']

    matched = (
        (on_left   and nhx == enx + 1 and nhy == eny) or
        (on_right  and nhx == enx - 1 and nhy == eny) or
        (on_bottom and nhx == enx     and nhy == eny + 1) or
        (on_top    and nhx == enx     and nhy == eny - 1)
    )

    if not matched:
        return False, None

    return True, {'x': enx, 'y': eny}


# =================================================================
#  SAFE MOVE FILTER  (Layer 1 — hard constraints)
# =================================================================

def get_safe_moves(game_state):
    """
    Returns moves that pass hard constraints:
      1. In bounds
      2. Not colliding with any snake body (tails may vacate)
      3. Not entering a head-to-head zone against a >= snake
         (falls back to risky if all moves are dangerous)
    """
    my_snake  = game_state['you']
    my_head   = my_snake['head']
    board     = game_state['board']
    board_w   = board['width']
    board_h   = board['height']
    my_length = my_snake['length']
    all_moves = ["up", "down", "left", "right"]

    # Build occupied set — tails that WILL vacate are excluded
    occupied = set()
    for snake in board['snakes']:
        tail_stays = _tail_will_stay(snake, board)
        for i, part in enumerate(snake['body']):
            if not tail_stays and i == len(snake['body']) - 1:
                continue   # tail vacates this turn
            occupied.add((part['x'], part['y']))

    # Head-to-head danger squares: squares an equal/larger enemy can reach
    danger_squares = set()
    for snake in board['snakes']:
        if snake['id'] == my_snake['id']:
            continue
        if snake['length'] >= my_length:
            for move in all_moves:
                nc = get_next_coord(snake['head'], move)
                nx, ny = nc['x'], nc['y']
                if 0 <= nx < board_w and 0 <= ny < board_h:
                    danger_squares.add((nx, ny))

    safe  = []
    risky = []   # dangerous only due to head-to-head, not wall/body

    for move in all_moves:
        nc = get_next_coord(my_head, move)
        nx, ny = nc['x'], nc['y']

        if not (0 <= nx < board_w and 0 <= ny < board_h):
            continue
        if (nx, ny) in occupied:
            continue
        if (nx, ny) in danger_squares:
            risky.append(move)
        else:
            safe.append(move)

    return safe if safe else risky


# =================================================================
#  MOVE SCORER  (Layer 2 — heuristic evaluation)
# =================================================================

# Pre-built graduated threat table: manhattan distance -> penalty
# Applied when an enemy of equal or greater length is at that distance.
_THREAT_PENALTY = {1: -120, 2: -70, 3: -25, 4: -8}

# Box-Out (Wall-Pin) scoring constants
_BOX_OUT_BONUS = 150   # base bonus for achieving the inner-lane position
_CORNER_BONUS  =  60   # additional bonus when the enemy is near a corner


def evaluate_move(move, game_state, in_risky_fallback=False, profiles=None):
    """
    Scores a candidate move across six dimensions (base) plus
    one tactical overlay dimension (profiler-driven).

      [BASE — unchanged]
      Space      0 – 100   flood-fill ratio (+ soft trap penalty)
      Food       0 –  80   urgency-scaled A* distance (competition-aware)
      Center     0 –  20   center control, scaled down when hungry
      Wall      -50 –   0  penalty per wall direction adjacent to next_head
      Threats  -120 – +25  graduated by distance; kill bonus if room
      Voronoi    0 –  30   cells we 'own' vs enemies (multi-source BFS)

      [OVERLAY — new]
      Tactical   varies    archetype-specific bonus/penalty adjustments
    """
    score      = 0
    my_snake   = game_state['you']
    board      = game_state['board']
    next_head  = get_next_coord(my_snake['head'], move)
    health     = my_snake['health']
    my_length  = my_snake['length']
    board_size = board['width'] * board['height']

    # ------------------------------------------------------------------
    # 1. FLOOD FILL — space reachable from next_head
    # ------------------------------------------------------------------
    space       = calculate_flood_fill(next_head, game_state)
    space_ratio = space / board_size          # 0.0 → 1.0

    if space == 0:
        return -9999   # completely walled in — discard immediately

    if space < my_length:
        # Trapped but not zero — scale penalty so more space = less bad.
        trap_severity = 1.0 - (space / my_length)   # 0→1 as space→0
        return -500 - trap_severity * 500            # range: -500 to -1000

    score += space_ratio * 100                # max 100 pts

    # Soft-trap penalty: space close to my_length is still risky
    if space < 2 * my_length:
        tightness = 1.0 - (space / (2.0 * my_length))   # 0→1 as space→0
        score -= tightness * 40                           # up to -40 pts

    # ------------------------------------------------------------------
    # 2. FOOD — urgency-scaled, A*-distance, competition-aware
    # ------------------------------------------------------------------
    base         = (100 - health) / 100
    food_urgency = 0.40 + 0.60 * (base ** 1.0)    # range [0.40, 1.00]

    best_food_score = 0
    if board['food']:
        board_w = board['width']
        board_h = board['height']
        next_is_danger = False
        for snake in board['snakes']:
            if snake['id'] == my_snake['id']:
                continue
            if snake['length'] >= my_length:
                for mv2 in ["up", "down", "left", "right"]:
                    nc2 = get_next_coord(snake['head'], mv2)
                    if nc2['x'] == next_head['x'] and nc2['y'] == next_head['y']:
                        next_is_danger = True
                        break

        for food in board['food']:
            path_len = astar_distance(next_head, food, game_state)
            if path_len is None:
                continue

            my_steps = path_len + 1
            enemy_min_dist = 999
            bigger_enemy_can_contest = False
            for s in board['snakes']:
                if s['id'] == my_snake['id']:
                    continue
                ed = manhattan(s['head'], food)
                if ed < enemy_min_dist:
                    enemy_min_dist = ed
                if s['length'] >= my_length and ed <= my_steps:
                    bigger_enemy_can_contest = True

            if bigger_enemy_can_contest:
                competition_factor = 0.0
            elif enemy_min_dist <= my_steps:
                competition_factor = 0.35
            else:
                competition_factor = 1.0

            food_at_next = (food['x'] == next_head['x'] and food['y'] == next_head['y'])
            if in_risky_fallback and food_at_next and next_is_danger:
                competition_factor = 0.0

            candidate = (1 / (path_len + 1)) * food_urgency * 80 * competition_factor
            if candidate > best_food_score:
                best_food_score = candidate

    score += best_food_score                  # max  80 pts

    if health <= 25 and best_food_score > 0:
        score += best_food_score * 0.5        # total food weight = 1.5x when near-dead

    # ------------------------------------------------------------------
    # 3. CENTER CONTROL
    # ------------------------------------------------------------------
    cx, cy       = board['width'] // 2, board['height'] // 2
    center_dist  = abs(next_head['x'] - cx) + abs(next_head['y'] - cy)
    max_c_dist   = cx + cy
    center_weight = 20 * max(0.3, 1.0 - food_urgency * 0.7)
    score        += (1 - center_dist / max_c_dist) * center_weight   # max ~20 pts

    # ------------------------------------------------------------------
    # 3b. WALL PROXIMITY PENALTY
    # ------------------------------------------------------------------
    wall_penalty_weight = max(0.3, 1.0 - food_urgency * 0.7)
    if next_head['x'] == 0 or next_head['x'] == board['width'] - 1:
        score -= 25 * wall_penalty_weight
    if next_head['y'] == 0 or next_head['y'] == board['height'] - 1:
        score -= 25 * wall_penalty_weight

    # ------------------------------------------------------------------
    # 4. ENEMY THREAT / OPPORTUNITY  — BASE LOGIC
    # ------------------------------------------------------------------
    for snake in board['snakes']:
        if snake['id'] == my_snake['id']:
            continue

        dist = manhattan(next_head, snake['head'])

        if snake['length'] >= my_length:
            penalty = _THREAT_PENALTY.get(dist, 0)
            score  += penalty
        else:
            if dist <= 2 and space_ratio > 0.35:
                score += 25

    # ------------------------------------------------------------------
    # 5. VORONOI TERRITORY
    # ------------------------------------------------------------------
    voronoi       = calculate_voronoi_space(next_head, game_state)
    voronoi_ratio = voronoi / board_size
    score        += voronoi_ratio * 30   # up to +30 pts

    # ==================================================================
    #  5b. OFFENSIVE OVERLAY: BOX-OUT (Wall-Pin)
    #
    #  Detects when an enemy is hugging the perimeter and moving parallel
    #  to it, and Thunga's candidate move places it in the "inner lane"
    #  (one tile inward from the enemy's projected path).  Thunga's body
    #  then acts as a second wall, compressing the enemy into a shrinking
    #  corridor with no legal inward escape.
    #
    #  All detection is O(1) coordinate arithmetic via _detect_box_out().
    #  No secondary BFS or A* is run.
    #
    #  Safety gate: if space_ratio <= 0.30, Thunga is itself cramped —
    #  the overlay is suppressed so we never box out at the cost of our
    #  own survival.
    #
    #  Scoring when triggered:
    #    • Cancel the section-4 kill-opportunity bonus (+25) that was
    #      already applied, so the Box-Out bonus is the sole signal.
    #    • Add _BOX_OUT_BONUS (+150) for achieving the inner-lane position.
    #    • Add _CORNER_BONUS  (+60)  if the enemy is ≤2 tiles from a corner
    #      (corner trap guarantees the kill faster).
    # ==================================================================
    for snake in board['snakes']:
        if snake['id'] == my_snake['id']:
            continue

        box_out, _proj = _detect_box_out(
            next_head, snake, my_length,
            board['width'], board['height']
        )

        if not box_out:
            continue

        # Safety gate: do not commit to a box-out from a cramped position
        if space_ratio <= 0.30:
            continue

        # Cancel the generic kill-opportunity bonus (+25 at dist ≤ 2)
        # already applied in section 4, so scores remain comparable.
        dist_to_enemy = manhattan(next_head, snake['head'])
        if dist_to_enemy <= 2 and space_ratio > 0.35:
            score -= 25   # exact reversal of the section-4 bonus

        # Core Box-Out bonus — overrides defensive hesitancy
        score += _BOX_OUT_BONUS

        # Corner trap bonus: enemy ≤ 2 manhattan tiles from any corner
        ex, ey = snake['head']['x'], snake['head']['y']
        bw, bh = board['width'], board['height']
        corners = [(0, 0), (0, bh - 1), (bw - 1, 0), (bw - 1, bh - 1)]
        min_corner_dist = min(
            abs(ex - crx) + abs(ey - cry) for crx, cry in corners
        )
        if min_corner_dist <= 2:
            score += _CORNER_BONUS

    # ==================================================================
    #  END BOX-OUT OVERLAY
    # ==================================================================

    # ==================================================================
    #  6. TACTICAL OVERLAY  ← NEW SECTION — Profiler-Driven Adjustments
    #
    #  This section is purely additive: it adjusts `score` after all
    #  base dimensions are finalized. No core algorithm is modified.
    #
    #  THREE GUARDS must all pass before any overlay fires:
    #    (a) profiles dict is populated (profiler has run this turn)
    #    (b) enemy has a confirmed archetype (turn_count >= 15)
    #    (c) enemy is within _INTERACTION_RADIUS manhattan tiles
    #
    #  If no guard passes, this entire block is a no-op and Thunga
    #  falls back entirely to its base heuristic — zero regression.
    # ==================================================================
    if profiles:
        for snake in board['snakes']:
            if snake['id'] == my_snake['id']:
                continue

            sid = snake['id']
            p   = profiles.get(sid)

            # Guard (b): unclassified or insufficient data — skip
            if p is None or p['archetype'] is None:
                continue

            archetype  = p['archetype']
            confidence = p['confidence']
            enemy_dist = manhattan(next_head, snake['head'])

            # Guard (c): too far away — overlay has no strategic value
            if enemy_dist >= _INTERACTION_RADIUS:
                continue

            # ── OVERLAY A: Vs VACUUM (Intercept & Shadow) ──────────────
            #
            #  A Vacuum always chases the nearest food, ignoring risk.
            #  Strategy: position Thunga adjacent to the contested food.
            #  After the Vacuum eats and grows, Thunga's body blocks the
            #  escape route, trapping the lengthened snake against itself.
            #
            #  Condition: Vacuum is ≤2 steps from food AND closer than us
            #  AND next_head is exactly 1 tile from that food (shadow slot).
            # ───────────────────────────────────────────────────────────
            if archetype == 'vacuum':
                for food in board['food']:
                    vac_dist = manhattan(snake['head'], food)
                    my_dist  = manhattan(next_head,    food)
                    if vac_dist <= 2 and vac_dist < my_dist and my_dist == 1:
                        score += 40 * confidence

            # ── OVERLAY B: Vs CAMPER (Box Them In) ─────────────────────
            #
            #  Campers hug the perimeter endlessly.
            #  Strategy: shadow them 1 tile inward, using Thunga's body as
            #  a parallel inner wall. This denies any inward turn, forcing
            #  the Camper to eventually collide with its own tail.
            #
            #  Also cancels Thunga's wall penalty — we deliberately want
            #  to be near the wall here, so the penalty is counter-productive.
            # ───────────────────────────────────────────────────────────
            elif archetype == 'camper':
                camper_hx = snake['head']['x']
                camper_hy = snake['head']['y']
                bw = board['width']
                bh = board['height']

                camper_on_wall = (
                    camper_hx == 0 or camper_hx == bw - 1 or
                    camper_hy == 0 or camper_hy == bh - 1
                )

                if camper_on_wall:
                    # Reverse the wall penalty already applied for next_head
                    if next_head['x'] == 0 or next_head['x'] == bw - 1:
                        score += 25 * wall_penalty_weight
                    if next_head['y'] == 0 or next_head['y'] == bh - 1:
                        score += 25 * wall_penalty_weight

                    # Inner perimeter square: 1 tile inward from Camper's
                    # walled axis; other axis stays the same.
                    inner_x = camper_hx
                    inner_y = camper_hy
                    if camper_hx == 0:        inner_x = 1
                    elif camper_hx == bw - 1: inner_x = bw - 2
                    if camper_hy == 0:        inner_y = 1
                    elif camper_hy == bh - 1: inner_y = bh - 2

                    if next_head['x'] == inner_x and next_head['y'] == inner_y:
                        score += 30 * confidence

            # ── OVERLAY C: Vs AGGRESSOR (Extreme Evasion + Tail Loop) ──
            #
            #  Aggressors sacrifice their own space to force a head-to-head.
            #  Strategy:
            #    1) Triple threat penalties at distances 1–2 (200% increase
            #       on top of base), so Thunga NEVER risks a head-to-head.
            #    2) When cornered (space_ratio < 0.5), bonus moves toward
            #       own vacating tail — creates a safe circuit the Aggressor
            #       cannot enter without crashing, buying starvation time.
            # ───────────────────────────────────────────────────────────
            elif archetype == 'aggressor':
                if snake['length'] >= my_length:
                    # Base already applied 1×. Add 2× more → net 3× total
                    # (a 200% magnitude increase from the original value).
                    extra = _THREAT_PENALTY.get(enemy_dist, 0) * 2
                    score += extra   # negative value → deepens avoidance

                # Tail-loop bonus when space is critically tight
                if (space_ratio < 0.5 and
                        len(my_snake['body']) > 1 and
                        not _tail_will_stay(my_snake, board)):
                    my_tail   = my_snake['body'][-1]
                    tail_dist = (abs(next_head['x'] - my_tail['x']) +
                                 abs(next_head['y'] - my_tail['y']))
                    if tail_dist <= 3:
                        score += 35 * confidence

            # ── OVERLAY D: Vs AREA-CONTROL (Early Food Aggression) ─────
            #
            #  Area-Control bots mirror Thunga's space-fill strategy exactly.
            #  Strategy: eat slightly earlier to secure +1 length advantage,
            #  instantly converting a peer threat into a kill target.
            #
            #  Implementation: shift the effective health downward by 25 pts
            #  to compute a higher food_urgency delta, then apply that delta
            #  on top of the already-scored best_food_score.
            # ───────────────────────────────────────────────────────────
            elif archetype == 'area_control':
                adjusted_health = max(0, health - 25)
                adj_base        = (100 - adjusted_health) / 100
                adj_urgency     = 0.40 + 0.60 * adj_base
                urgency_delta   = adj_urgency - food_urgency   # always >= 0
                if best_food_score > 0:
                    score += best_food_score * urgency_delta * confidence

            # ── OVERLAY E: Vs ERRATIC (Reduced Threat Radius) ──────────
            #
            #  Erratic snakes are unpredictable but pose no sustained threat.
            #  Smart snakes over-correct by yielding centre territory to dodge
            #  random heads. Strategy: only fear a 1-tile certainty (dist==1).
            #
            #  Cancel the graduated penalties at distances 2–4 that the base
            #  section already applied, reclaiming board territory that was
            #  incorrectly surrendered.
            # ───────────────────────────────────────────────────────────
            elif archetype == 'erratic':
                if snake['length'] >= my_length and 2 <= enemy_dist <= 4:
                    # _THREAT_PENALTY values are negative. Subtracting a
                    # negative adds points back — net effect is reclaiming
                    # the territory penalty.
                    cancelled = _THREAT_PENALTY.get(enemy_dist, 0)
                    score    -= cancelled   # e.g. -(-70) = +70

    # ==================================================================
    #  END TACTICAL OVERLAY
    # ==================================================================

    return score


# =================================================================
#  FLOOD FILL
# =================================================================

def calculate_flood_fill(head, game_state):
    """
    BFS flood fill — counts reachable empty squares from `head`.
    Tails that will vacate this turn are excluded from obstacles.
    """
    board  = game_state['board']
    width  = board['width']
    height = board['height']

    occupied = set()
    for snake in game_state['board']['snakes']:
        tail_stays = _tail_will_stay(snake, board)
        for i, part in enumerate(snake['body']):
            if not tail_stays and i == len(snake['body']) - 1:
                continue   # tail vacates
            occupied.add((part['x'], part['y']))

    visited = set()
    queue   = deque([(head['x'], head['y'])])

    while queue:
        x, y = queue.popleft()
        if (x, y) in visited:
            continue
        if not (0 <= x < width and 0 <= y < height):
            continue
        if (x, y) in occupied:
            continue
        visited.add((x, y))
        queue.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])

    return len(visited)


# =================================================================
#  VORONOI SPACE
# =================================================================

def calculate_voronoi_space(head, game_state):
    """
    Multi-source Dijkstra race from our next_head and all enemy heads.
    Returns the number of board cells closer to our head than to
    any enemy head (ties go to neither). Uses a min-heap for correct
    shortest-path ordering.
    """
    board   = game_state['board']
    width   = board['width']
    height  = board['height']
    my_id   = game_state['you']['id']

    occupied = set()
    for snake in board['snakes']:
        tail_stays = _tail_will_stay(snake, board)
        for i, part in enumerate(snake['body']):
            if not tail_stays and i == len(snake['body']) - 1:
                continue
            occupied.add((part['x'], part['y']))

    dist_map = {}
    heap     = []   # (dist, pos, owner)

    our_pos = (head['x'], head['y'])
    if our_pos not in occupied:
        dist_map[our_pos] = (0, 'our')
        heapq.heappush(heap, (0, our_pos, 'our'))

    for snake in board['snakes']:
        if snake['id'] == my_id:
            continue
        epos = (snake['head']['x'], snake['head']['y'])
        if epos in occupied:
            continue
        if epos not in dist_map:
            dist_map[epos] = (0, snake['id'])
            heapq.heappush(heap, (0, epos, snake['id']))
        else:
            existing_d, existing_owner = dist_map[epos]
            if existing_d == 0 and existing_owner != snake['id']:
                dist_map[epos] = (0, 'tie')

    while heap:
        d, pos, owner = heapq.heappop(heap)

        existing_d, existing_owner = dist_map.get(pos, (None, None))
        if existing_d is None or d > existing_d:
            continue
        if existing_owner == 'tie' and owner != 'tie':
            continue

        x, y = pos
        for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in occupied:
                continue
            new_d   = d + 1
            new_pos = (nx, ny)
            if new_pos not in dist_map:
                dist_map[new_pos] = (new_d, owner)
                heapq.heappush(heap, (new_d, new_pos, owner))
            else:
                prev_d, prev_owner = dist_map[new_pos]
                if new_d < prev_d:
                    dist_map[new_pos] = (new_d, owner)
                    heapq.heappush(heap, (new_d, new_pos, owner))
                elif new_d == prev_d and prev_owner != owner and prev_owner != 'tie':
                    dist_map[new_pos] = (new_d, 'tie')

    return sum(1 for (_, owner) in dist_map.values() if owner == 'our')


# =================================================================
#  A* PATHFINDING
# =================================================================

def astar_distance(start, goal, game_state):
    """
    Returns shortest path length from `start` to `goal`, or None.
    Uses a proper min-heap for O(n log n) performance.
    """
    board  = game_state['board']
    width  = board['width']
    height = board['height']

    occupied = set()
    for snake in game_state['board']['snakes']:
        tail_stays = _tail_will_stay(snake, board)
        for i, part in enumerate(snake['body']):
            if not tail_stays and i == len(snake['body']) - 1:
                continue
            occupied.add((part['x'], part['y']))

    start_pos = (start['x'], start['y'])
    goal_pos  = (goal['x'],  goal['y'])

    h0       = manhattan(start, goal)
    heap     = [(h0, 0, start_pos)]          # (f, g, pos)
    g_scores = {start_pos: 0}

    while heap:
        f, g, pos = heapq.heappop(heap)

        if pos == goal_pos:
            return g

        if g > g_scores.get(pos, float('inf')):
            continue

        x, y = pos
        for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in occupied:
                continue
            new_g = g + 1
            if new_g < g_scores.get((nx, ny), float('inf')):
                g_scores[(nx, ny)] = new_g
                new_f = new_g + manhattan({"x": nx, "y": ny}, goal)
                heapq.heappush(heap, (new_f, new_g, (nx, ny)))

    return None   # unreachable


# =================================================================
#  HELPERS
# =================================================================

def get_next_coord(head, move):
    if move == "up":    return {"x": head["x"],     "y": head["y"] + 1}
    if move == "down":  return {"x": head["x"],     "y": head["y"] - 1}
    if move == "left":  return {"x": head["x"] - 1, "y": head["y"]}
    if move == "right": return {"x": head["x"] + 1, "y": head["y"]}

def manhattan(a, b):
    return abs(a['x'] - b['x']) + abs(a['y'] - b['y'])

def get_closest_food_distance(head, food_list):
    if not food_list:
        return 0
    return min(manhattan(head, food) for food in food_list)
