"""Adapter to the unchanged, MIT-licensed upstream competition engine."""
from pathlib import Path
import sys
import os

os.environ.setdefault("JAX_PLATFORMS", "cpu")

ENGINE_COMMIT = "13db8f69a422380ea184d2f4ca262a38866c5fc6"
VENDOR = Path(__file__).resolve().parent / "vendor" / "generals-bots"
sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(VENDOR / "competition"))

import jax
import jax.numpy as jnp
from generals import GeneralsEnv
from generals.core import game
from matchup import make_board, make_transition
from protocol import encode_observation

ENV = GeneralsEnv(mode="competition")
TRANSITION = jax.jit(make_transition(ENV))


def observation(state, player):
    # Reuse the published perspective/fog encoder, then expose Python lists.
    rows = [[int(v) for v in line.split()] for line in
            encode_observation(game.get_observation(state, player)).splitlines()]
    turn, my_land, my_army, opp_land, opp_army = rows[0]
    h, w = state.armies.shape
    return dict(turn=turn, height=h, width=w, player_id=player,
                my_land=my_land, my_army=my_army, opp_land=opp_land, opp_army=opp_army,
                type=rows[1:1+h], owner=rows[1+h:1+2*h], army=rows[1+2*h:1+3*h])


def initial(seed):
    state = make_board(ENV, seed)
    # Compile the exact board shape and observation paths before bot clocks run.
    warm, _ = TRANSITION(state, jnp.array([[1, 0, 0, 0, 0]] * 2, dtype=jnp.int32))
    warm.armies.block_until_ready()
    observation(state, 0)
    observation(state, 1)
    return state


def step(state, actions):
    return TRANSITION(state, jnp.array(actions, dtype=jnp.int32))


def snapshot(state):
    return {name: getattr(state, name).tolist() for name in
            ("armies", "ownership", "generals", "castles", "passable", "time", "winner")}
