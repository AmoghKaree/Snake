import math
import heapq
from collections import deque

# =================================================================
#  ENTRY POINT
# =================================================================

def choose_move(data):
    return choose_best_move(data)


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

def choose_best_move(game_state):
    print_board(game_state)

    safe_moves = get_safe_moves(game_state)

    if not safe_moves:
        print("  !! No safe moves — going up and praying")
        return "up"

    best_move     = safe_moves[0]
    highest_score = -math.inf

    for move in safe_moves:
        score = evaluate_move(move, game_state)
        print(f"  {move:5} -> {score:.2f}")

        if score > highest_score:
            highest_score = score
            best_move     = move

    print(f"  Chosen: {best_move}\n")
    return best_move


# =================================================================
#  TAIL-VACATING HELPER
# =================================================================

def _tail_will_stay(snake, board):
    """
    Returns True if this snake's tail will NOT vacate this turn, meaning
    we should treat the tail square as still occupied.

    Tail stays when:
      a) Snake just ate (health == 100) — body grows, tail doesn't move, OR
      b) Snake's head is adjacent to food and could eat this turn.
         We can't know which direction the enemy will move, so we are
         conservative: if any neighbour of their head is food, keep tail.
    """
    if snake['health'] == 100:
        return True   # ate last turn, tail already staying
    food_set = {(f['x'], f['y']) for f in board['food']}
    head = snake['head']
    for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
        if (head['x'] + dx, head['y'] + dy) in food_set:
            return True   # snake can eat this turn — treat tail as staying
    return False


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
    my_head   = game_state['you']['head']
    my_length = game_state['you']['length']
    board_w   = game_state['board']['width']
    board_h   = game_state['board']['height']

    # Build occupied set — tails that WILL vacate are excluded
    occupied = set()
    for snake in game_state['board']['snakes']:
        tail_stays = _tail_will_stay(snake, game_state['board'])
        for i, part in enumerate(snake['body']):
            if not tail_stays and i == len(snake['body']) - 1:
                continue   # tail vacates this turn
            occupied.add((part['x'], part['y']))

    # Head-to-head danger squares: squares an equal/larger enemy can reach
    danger_squares = set()
    for snake in game_state['board']['snakes']:
        if snake['id'] == game_state['you']['id']:
            continue
        if snake['length'] >= my_length:
            for move in ["up", "down", "left", "right"]:
                nc = get_next_coord(snake['head'], move)
                nx, ny = nc['x'], nc['y']
                if 0 <= nx < board_w and 0 <= ny < board_h:
                    danger_squares.add((nx, ny))

    safe  = []
    risky = []   # dangerous only due to head-to-head, not wall/body

    for move in ["up", "down", "left", "right"]:
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


def evaluate_move(move, game_state):
    """
    Scores a candidate move across six dimensions.

      Space      0 – 100   flood-fill ratio (+ soft trap penalty)
      Food       0 –  80   urgency-scaled A* distance (competition-aware)
      Center     0 –  20   center control, scaled down when hungry
      Wall      -50 –   0  penalty per wall direction adjacent to next_head
      Threats  -120 – +25  graduated by distance; kill bonus if room
      Voronoi    0 –  30   cells we 'own' vs enemies (multi-source BFS)
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

    if space < my_length:
        return -9999   # hard trap — discard immediately

    score += space_ratio * 100                # max 100 pts

    # FIX #3 — soft-trap penalty: space close to my_length is still risky
    if space < 2 * my_length:
        tightness = 1.0 - (space / (2.0 * my_length))   # 0→1 as space→0
        score -= tightness * 40                           # up to -40 pts

    # ------------------------------------------------------------------
    # 2. FOOD — urgency-scaled, A*-distance, competition-aware
    # ------------------------------------------------------------------
    base         = (100 - health) / 100
    # FIX #5 — urgency ramps earlier (exponent 1.2 not 1.5) with higher floor
    food_urgency = 0.30 + 0.70 * (base ** 1.2)    # range [0.30, 1.00]

    best_food_score = 0
    if board['food']:
        for food in board['food']:
            path_len = astar_distance(next_head, food, game_state)
            if path_len is None:
                continue

            # FIX #2 — food competition: discount food an enemy can reach first
            my_steps = path_len + 1    # steps from our current position
            enemy_min_dist = min(
                (manhattan(s['head'], food)
                 for s in board['snakes'] if s['id'] != my_snake['id']),
                default=999
            )
            competition_factor = 0.35 if enemy_min_dist <= my_steps else 1.0

            candidate = (1 / (path_len + 1)) * food_urgency * 80 * competition_factor
            if candidate > best_food_score:
                best_food_score = candidate

    score += best_food_score                  # max  80 pts

    # Emergency starvation override — health critical: massive food bonus
    if health <= 25 and best_food_score > 0:
        score += best_food_score * 1.5        # double-weight food when near-dead

    # ------------------------------------------------------------------
    # 3. CENTER CONTROL
    # FIX #5 — center is less important when hungry
    # ------------------------------------------------------------------
    cx, cy       = board['width'] // 2, board['height'] // 2
    center_dist  = abs(next_head['x'] - cx) + abs(next_head['y'] - cy)
    max_c_dist   = cx + cy
    center_weight = 20 * max(0.3, 1.0 - food_urgency * 0.7)
    score        += (1 - center_dist / max_c_dist) * center_weight   # max ~20 pts

    # ------------------------------------------------------------------
    # 3b. WALL PROXIMITY PENALTY
    # FIX #8 — discourage hugging walls/corners; prevents funnel traps.
    # Each wall direction adjacent to next_head costs -25.
    # Scaled down when starving (need food near walls).
    # ------------------------------------------------------------------
    wall_penalty_weight = max(0.3, 1.0 - food_urgency * 0.7)  # same scale as center
    if next_head['x'] == 0 or next_head['x'] == board['width'] - 1:
        score -= 25 * wall_penalty_weight
    if next_head['y'] == 0 or next_head['y'] == board['height'] - 1:
        score -= 25 * wall_penalty_weight

    # ------------------------------------------------------------------
    # 4. ENEMY THREAT / OPPORTUNITY
    # FIX #1 — graduated penalty (not binary cliff)
    # FIX #6 — kill bonus only when we have room
    # ------------------------------------------------------------------
    for snake in board['snakes']:
        if snake['id'] == my_snake['id']:
            continue

        dist = manhattan(next_head, snake['head'])

        if snake['length'] >= my_length:
            # Threat: graduated penalty by proximity
            penalty = _THREAT_PENALTY.get(dist, 0)
            score  += penalty
        else:
            # Opportunity: adjacent smaller snake we can eliminate
            # FIX #6 — only pursue when we have sufficient space
            if dist <= 2 and space_ratio > 0.35:
                score += 25

    # ------------------------------------------------------------------
    # 5. VORONOI TERRITORY
    # FIX #9 — multi-source BFS to count cells we'd "own" vs enemies.
    # Rewards moves that give us larger territory in a competitive board.
    # Most impactful when many equal opponents are present.
    # ------------------------------------------------------------------
    voronoi = calculate_voronoi_space(next_head, game_state)
    voronoi_ratio = voronoi / board_size
    score += voronoi_ratio * 30   # up to +30 pts

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
#  VORONOI SPACE  (FIX #9)
# =================================================================

def calculate_voronoi_space(head, game_state):
    """
    Multi-source BFS race from our next_head and all enemy heads.
    Returns the number of board cells closer to our head than to
    any enemy head (ties go to neither).  This measures our 'territory'
    in a competitive game — more accurately than pure flood fill when
    multiple snakes are converging.
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

    # dist_map: pos -> (min_dist, owner)  owner='tie' means contested
    dist_map = {}
    queue    = deque()

    # Seed our next head
    our_pos = (head['x'], head['y'])
    if our_pos not in occupied:
        dist_map[our_pos] = (0, 'our')
        queue.append((0, our_pos, 'our'))

    # Seed all enemy heads
    for snake in board['snakes']:
        if snake['id'] == my_id:
            continue
        epos = (snake['head']['x'], snake['head']['y'])
        if epos in occupied:
            continue
        if epos not in dist_map:
            dist_map[epos] = (0, snake['id'])
            queue.append((0, epos, snake['id']))
        else:
            existing_d, _ = dist_map[epos]
            if existing_d == 0:
                dist_map[epos] = (0, 'tie')

    while queue:
        d, pos, owner = queue.popleft()
        existing_d, existing_owner = dist_map.get(pos, (None, None))
        if existing_d is None or d > existing_d:
            continue
        if existing_owner == 'tie':
            continue   # don't expand from contested cells

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
                queue.append((new_d, new_pos, owner))
            else:
                prev_d, prev_owner = dist_map[new_pos]
                if new_d < prev_d:
                    dist_map[new_pos] = (new_d, owner)
                    queue.append((new_d, new_pos, owner))
                elif new_d == prev_d and prev_owner != owner and prev_owner != 'tie':
                    dist_map[new_pos] = (new_d, 'tie')

    return sum(1 for (_, owner) in dist_map.values() if owner == 'our')


# =================================================================
#  A* PATHFINDING  (FIX #4 — heap-based, O(n log n) not O(n²))
# =================================================================

def astar_distance(start, goal, game_state):
    """
    Returns shortest path length from `start` to `goal`, or None.
    Uses a proper min-heap instead of list.sort() for performance.
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

    h0 = manhattan(start, goal)
    heap     = [(h0, 0, start_pos)]          # (f, g, pos)
    g_scores = {start_pos: 0}

    while heap:
        f, g, pos = heapq.heappop(heap)

        if pos == goal_pos:
            return g

        # Skip if a better path to this node was already found
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


def astar(start, goal, game_state):
    """
    Returns first move direction toward `goal`, or None.
    """
    board  = game_state['board']
    width  = board['width']
    height = board['height']

    occupied = set()
    for snake in game_state['board']['snakes']:
        for part in snake['body']:
            occupied.add((part['x'], part['y']))

    start_pos = (start['x'], start['y'])
    goal_pos  = (goal['x'],  goal['y'])

    h0    = manhattan(start, goal)
    heap  = [(h0, 0, start_pos, None)]   # (f, g, pos, first_move)
    g_scores = {start_pos: 0}

    while heap:
        f, g, pos, first_move = heapq.heappop(heap)

        if pos == goal_pos:
            return first_move

        if g > g_scores.get(pos, float('inf')):
            continue

        x, y = pos
        for move, (dx, dy) in [("up",(0,1)),("down",(0,-1)),
                                ("left",(-1,0)),("right",(1,0))]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in occupied:
                continue
            new_g = g + 1
            if new_g < g_scores.get((nx, ny), float('inf')):
                g_scores[(nx, ny)] = new_g
                new_f = new_g + manhattan({"x": nx, "y": ny}, goal)
                next_first = first_move if first_move else move
                heapq.heappush(heap, (new_f, new_g, (nx, ny), next_first))

    return None


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
