"""Debug script for B3-S4 failure analysis."""
import random, sys, io, contextlib
sys.path.insert(0, '.')

import simulate25 as sim
import contextlib

@contextlib.contextmanager
def no_suppress():
    yield

# Patch suppress_output to be a no-op so debug prints show through
sim.suppress_output = no_suppress

from logic import get_safe_moves, evaluate_move, calculate_flood_fill, get_next_coord
import logic as L

orig_best = L.choose_best_move

def debug_choose(gs):
    turn = gs['turn']
    me = gs['you']
    board = gs['board']
    safe = get_safe_moves(gs)
    scores = {}
    for mv in safe:
        scores[mv] = round(evaluate_move(mv, gs), 1)
    space_info = {}
    for mv in ['up', 'down', 'left', 'right']:
        nh = get_next_coord(me['head'], mv)
        space_info[mv] = calculate_flood_fill(nh, gs)
    enemy_info = [(s['name'], s['head']['x'], s['head']['y'], s['length'])
                  for s in board['snakes'] if s['id'] != me['id']]
    print(f"T{turn} head=({me['head']['x']},{me['head']['y']}) hp={me['health']} len={me['length']}")
    print(f"  enemies: {enemy_info}")
    print(f"  space: {space_info}")
    print(f"  safe={safe}  scores={scores}")
    result = orig_best(gs)
    print(f"  => {result}")
    return result

L.choose_best_move = debug_choose

random.seed(34)
cfgs = [
    sim.us(x=5, y=5),
    sim.enemy('e1', 'SA', 5, 7, 'simple'),
    sim.enemy('e2', 'SB', 7, 5, 'simple'),
    sim.enemy('e3', 'SC', 5, 3, 'simple'),
]
sim.run_scenario('B3-S4 DEBUG', 34, cfgs, 35, verbose=True)
