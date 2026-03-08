"""Debug I-hp8-blocked and F-all-aggressive-5."""
import random, sys, io, contextlib
sys.path.insert(0, '.')
import simulate25 as sim
import contextlib

@contextlib.contextmanager
def no_suppress():
    yield

sim.suppress_output = no_suppress

from logic import get_safe_moves, evaluate_move, get_next_coord
import logic as L

orig_best = L.choose_best_move

def debug_choose(gs):
    me = gs['you']
    board = gs['board']
    safe = get_safe_moves(gs)
    scores = {mv: round(evaluate_move(mv, gs), 1) for mv in safe}
    enemy_info = [(s['name'], s['head']['x'], s['head']['y'], s['length'])
                  for s in board['snakes'] if s['id'] != me['id']]
    print(f"T{gs['turn']} head=({me['head']['x']},{me['head']['y']}) hp={me['health']} len={me['length']}")
    print(f"  enemies={enemy_info}")
    print(f"  safe={safe} scores={scores}")
    result = orig_best(gs)
    print(f"  => {result}")
    return result

L.choose_best_move = debug_choose

print("=== I-hp8-blocked (seed=902) ===")
random.seed(902)
cfgs = [
    sim.us(x=5, y=5, health=8),
    sim.enemy('e1', 'A1', 4, 5, 'aggressive'),
    sim.enemy('e2', 'A2', 6, 5, 'aggressive'),
]
t, alive, r = sim.run_scenario('I-hp8-blocked', 902, cfgs, 12, verbose=True)
print(f"Result: t={t} alive={alive} ({r})")

print("\n=== F-all-aggressive-5 (seed=605) ===")
random.seed(605)
cfgs2 = [
    sim.us(x=5, y=5),
    sim.enemy('e1', 'A1', 0, 9, 'aggressive'),
    sim.enemy('e2', 'A2', 9, 9, 'aggressive'),
    sim.enemy('e3', 'A3', 0, 0, 'aggressive'),
    sim.enemy('e4', 'A4', 9, 0, 'aggressive'),
]
t2, alive2, r2 = sim.run_scenario('F-all-aggressive-5', 605, cfgs2, 20, verbose=True)
print(f"Result: t={t2} alive={alive2} ({r2})")
