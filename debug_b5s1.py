"""Debug script for B5-S1: 4 clones vs us."""
import random, sys, io, contextlib
sys.path.insert(0, '.')

import simulate25 as sim
import contextlib

@contextlib.contextmanager
def no_suppress():
    yield

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

random.seed(51)
cfgs = [
    sim.us(x=5, y=5),
    sim.enemy('e1', 'ClA', 1, 9, 'clone'),
    sim.enemy('e2', 'ClB', 9, 9, 'clone'),
    sim.enemy('e3', 'ClC', 1, 1, 'clone'),
    sim.enemy('e4', 'ClD', 9, 1, 'clone'),
]
sim.run_scenario('B5-S1 DEBUG', 51, cfgs, 20, verbose=True)
