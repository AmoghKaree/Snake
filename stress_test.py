"""
Stress test: run 50 varied scenarios to find remaining weaknesses.
Tests varied seeds, opponent mixes, starting positions, and health values.
"""
import random, sys, io, contextlib, copy
sys.path.insert(0, '.')

import simulate25 as sim
from simulate25 import (us, us_long, enemy, enemy_long,
                         run_scenario, suppress_output, passed, AI_REGISTRY)

RESULTS = []

def run(name, seed, cfgs, max_t=200):
    turns, alive, reason = run_scenario(name, seed, cfgs, max_t, verbose=False)
    ok = passed(turns, alive)
    RESULTS.append((name, seed, turns, alive, reason, ok))
    status = "PASS" if ok else "FAIL"
    fate   = "alive" if alive else "dead"
    print(f"  {status}  {name:<52}  t={turns:4d}  {fate}")
    return ok

print("\n" + "#"*64)
print("#  STRESS TEST — 50 varied scenarios")
print("#"*64)

# ── GROUP A: Solo endurance across many seeds ─────────────────
print("\n[A] Solo endurance (varied seeds, 200t)")
for seed in [101, 102, 103, 104, 105]:
    run(f"A-solo-seed{seed}", seed, [us(x=5,y=5)], 200)

# ── GROUP B: 1v1 vs each AI at varied positions ───────────────
print("\n[B] 1v1 varied positions")
run("B-1v1-simple-center",  201, [us(x=5,y=5), enemy("e1","S",0,0,"simple")], 200)
run("B-1v1-hungry-close",   202, [us(x=5,y=5), enemy("e1","H",5,7,"hungry")], 200)
run("B-1v1-clone-edge",     203, [us(x=0,y=5), enemy("e1","C",10,5,"clone")], 200)
run("B-1v1-agg-adjacent",   204, [us(x=5,y=5), enemy("e1","A",5,8,"aggressive")], 200)
run("B-1v1-rand-corner",    205, [us(x=0,y=0), enemy("e1","R",10,10,"random")], 200)

# ── GROUP C: Health-stress tests ──────────────────────────────
print("\n[C] Critical health scenarios")
run("C-hp5-solo",           301, [us(x=5,y=5,health=5)], 200)
run("C-hp10-2enemy",        302, [us(x=5,y=5,health=10),
                                    enemy("e1","S1",1,1,"simple"),
                                    enemy("e2","S2",9,9,"simple")], 200)
run("C-hp25-clone",         303, [us(x=5,y=5,health=25),
                                    enemy("e1","Cl",9,9,"clone")], 200)
run("C-hp50-surrounded",    304, [us(x=5,y=5,health=50),
                                    enemy("e1","A1",3,5,"aggressive"),
                                    enemy("e2","A2",7,5,"aggressive")], 200)
run("C-hp8-escape",         306, [us(x=1,y=1,health=8),
                                    enemy("e1","S",9,9,"simple")], 200)

# ── GROUP D: Longer enemy snakes ─────────────────────────────
print("\n[D] Facing longer enemies")
run("D-vs-len6-simple",     401, [us(x=1,y=9),
                                    enemy_long("e1","Big",9,9,6,"left","simple")], 200)
run("D-vs-len8-hungry",     402, [us(x=5,y=5),
                                    enemy_long("e1","Big",1,9,8,"right","hungry")], 200)
run("D-vs-len10-clone",     403, [us(x=5,y=5),
                                    enemy_long("e1","Big",9,9,10,"left","clone")], 200)
run("D-vs-2x-len7",         404, [us(x=5,y=5),
                                    enemy_long("e1","BigA",1,9,7,"right","hungry"),
                                    enemy_long("e2","BigB",9,1,7,"left","hungry")], 200)
run("D-us-len9-vs-len9",    405, [us_long("our","Bot",1,9,9,"right"),
                                    enemy_long("e1","Opp",9,9,9,"left","clone")], 200)

# ── GROUP E: Wall & corner challenges ────────────────────────
print("\n[E] Wall/corner challenges")
run("E-start-corner-TL",    501, [us(x=0,y=10), enemy("e1","E",9,1,"simple")], 200)
run("E-start-corner-BR",    502, [us(x=10,y=0), enemy("e1","E",0,9,"simple")], 200)
run("E-wall-top",           503, [us(x=5,y=10), enemy("e1","E",5,0,"hungry")], 200)
run("E-wall-right",         504, [us(x=10,y=5), enemy("e1","E",0,5,"hungry")], 200)
run("E-two-corners-us",     505, [us(x=0,y=0),
                                    enemy("e1","EA",10,10,"aggressive"),
                                    enemy("e2","EB",10,0,"aggressive")], 200)

# ── GROUP F: Crowded boards ──────────────────────────────────
print("\n[F] Crowded boards (many snakes)")
run("F-6snakes",            601, [us(x=5,y=9),
                                    enemy("e1","A",0,9,"simple"),
                                    enemy("e2","B",9,9,"simple"),
                                    enemy("e3","C",0,0,"hungry"),
                                    enemy("e4","D",9,0,"hungry"),
                                    enemy("e5","E",5,0,"random")], 200)
run("F-5clones",            602, [us(x=5,y=5),
                                    enemy("e1","C1",0,9,"clone"),
                                    enemy("e2","C2",9,9,"clone"),
                                    enemy("e3","C3",0,0,"clone"),
                                    enemy("e4","C4",9,0,"clone")], 200)
run("F-4hungry",            603, [us(x=5,y=9),
                                    enemy("e1","H1",0,9,"hungry"),
                                    enemy("e2","H2",9,9,"hungry"),
                                    enemy("e3","H3",0,0,"hungry"),
                                    enemy("e4","H4",9,0,"hungry")], 200)
run("F-3clone-2hungry",     604, [us(x=5,y=9),
                                    enemy("e1","C1",0,9,"clone"),
                                    enemy("e2","C2",9,9,"clone"),
                                    enemy("e3","C3",5,0,"clone"),
                                    enemy("e4","H1",0,0,"hungry"),
                                    enemy("e5","H2",9,0,"hungry")], 200)
run("F-all-aggressive-5",   606, [us(x=5,y=5),
                                    enemy("e1","A1",0,9,"aggressive"),
                                    enemy("e2","A2",9,9,"aggressive"),
                                    enemy("e3","A3",0,0,"aggressive"),
                                    enemy("e4","A4",9,0,"aggressive")], 200)

# ── GROUP G: Endurance tests ─────────────────────────────────
print("\n[G] Long endurance (400t+)")
run("G-solo-400t",          701, [us(x=5,y=5)], 400)
run("G-1v1-clone-400t",     702, [us(x=1,y=9), enemy("e1","Cl",9,1,"clone")], 400)
run("G-solo-700t",          703, [us(x=5,y=5)], 700)
run("G-1v1-simple-300t",    704, [us(x=1,y=1), enemy("e1","S",9,9,"simple")], 300)
run("G-2v1-hungry-300t",    705, [us(x=5,y=5),
                                    enemy("e1","H1",0,9,"hungry"),
                                    enemy("e2","H2",9,0,"hungry")], 300)

# ── GROUP H: Specific tactical positions ─────────────────────
print("\n[H] Specific tactical positions")
run("H-us-longer-kills",    801, [us_long("our","Bot",1,9,5,"right"),
                                    enemy("e1","SmA",9,9,"simple"),
                                    enemy("e2","SmB",9,0,"simple")], 200)
run("H-head-to-head-avoid", 802, [us(x=4,y=5), enemy("e1","Eq",6,5,"clone")], 200)
run("H-food-race",          803, [us(x=0,y=0), enemy("e1","H",10,10,"hungry")], 200)
run("H-enemy-tail-trap",    804, [us(x=5,y=5),
                                    enemy_long("e1","Long",5,9,6,"right","simple")], 200)
run("H-3way-tie",           805, [us(x=5,y=5),
                                    enemy("e1","C1",2,8,"clone"),
                                    enemy("e2","C2",8,8,"clone")], 200)

# ── GROUP I: Starvation recovery ─────────────────────────────
print("\n[I] Starvation recovery")
run("I-hp10-1food",          901, [us(x=0,y=0,health=10),
                                    enemy("e1","S",9,9,"simple")], 200)
run("I-hp20-blocked",       902, [us(x=5,y=5,health=20),
                                    enemy("e1","A1",3,5,"aggressive"),
                                    enemy("e2","A2",7,5,"aggressive")], 200)
run("I-hp15-multi",         903, [us(x=5,y=5,health=15),
                                    enemy("e1","H1",1,9,"hungry"),
                                    enemy("e2","H2",9,1,"hungry")], 200)
run("I-hp20-clone-race",    904, [us(x=0,y=0,health=20),
                                    enemy("e1","Cl",10,10,"clone")], 200)
run("I-hp30-surrounded",    905, [us(x=5,y=5,health=30),
                                    enemy("e1","S1",3,5,"simple"),
                                    enemy("e2","S2",7,5,"simple"),
                                    enemy("e3","S3",5,7,"simple")], 200)

# ── GROUP J: Mixed advanced ──────────────────────────────────
print("\n[J] Advanced mixed")
run("J-5v5-chaos",         1001, [us(x=5,y=9),
                                    enemy("e1","C1",0,9,"clone"),
                                    enemy("e2","H1",9,9,"hungry"),
                                    enemy("e3","A1",0,0,"aggressive"),
                                    enemy("e4","R1",9,0,"random"),
                                    enemy("e5","S1",5,0,"simple")], 200)
run("J-us-tiny-vs-giant",  1002, [us(x=5,y=5),
                                    enemy_long("e1","G1",0,9,12,"right","hungry"),
                                    enemy_long("e2","G2",9,9,12,"left","hungry")], 200)
run("J-grow-then-fight",   1003, [us_long("our","Bot",1,5,8,"right"),
                                    enemy_long("e1","Opp",9,5,8,"left","clone")], 200)
run("J-escape-ambush",     1004, [us(x=5,y=5),
                                    enemy("e1","A1",3,7,"aggressive"),
                                    enemy("e2","A2",7,7,"aggressive"),
                                    enemy("e3","A3",3,3,"aggressive"),
                                    enemy("e4","A4",7,3,"aggressive")], 200)
run("J-late-game-crowd",   1005, [us_long("our","Bot",0,9,7,"down"),
                                    enemy_long("e1","OppA",10,9,7,"down","clone"),
                                    enemy_long("e2","OppB",5,9,7,"down","hungry")], 200)

# ── SUMMARY ──────────────────────────────────────────────────
print("\n" + "="*64)
passes = sum(1 for r in RESULTS if r[5])
fails  = [r for r in RESULTS if not r[5]]
print(f"  TOTAL: {passes}/{len(RESULTS)} passed")
if fails:
    print(f"\n  FAILURES ({len(fails)}):")
    for name, seed, turns, alive, reason, _ in fails:
        fate = "alive" if alive else "dead"
        print(f"    FAIL  {name}  seed={seed}  t={turns}  {fate}  ({reason})")
print("="*64)
