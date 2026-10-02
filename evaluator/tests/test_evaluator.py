import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluate import Event, freeze, standings, validate_file
from sandbox import BotFault, validate_action


@pytest.mark.parametrize("action", [[1, 0, 0, 0, 0], [0, -1, 999, 3, 1], [2, 3, 4, 0, 0]])
def test_valid_action(action):
    assert validate_action(action) == action


@pytest.mark.parametrize("action", [None, [], [1, 0, 0], [True, 0, 0, 0, 0],
                                   [1, 0.0, 0, 0, 0], [0, 0, 0, 4, 0],
                                   [3, 0, 0, 0, 0], [0, 2**31, 0, 0, 0]])
def test_malformed_actions(action):
    with pytest.raises(BotFault):
        validate_action(action)


def test_validation_never_executes_and_freezes(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("raise Exception('do not execute on host')\ndef act(obs): return [1,0,0,0,0]\n")
    assert validate_file(p)
    out = tmp_path / "out"
    out.mkdir()
    data = freeze([p], out)
    p.write_text("changed")
    assert hashlib.sha256(Path(data['a']['path']).read_bytes()).hexdigest() == data['a']['sha256']


def test_file_constraints(tmp_path):
    p = tmp_path / "entry.py"
    for text in ["", "not python!", "x = 1", "async def act(obs): pass", "#"*1048577]:
        p.write_text(text)
        with pytest.raises(ValueError):
            validate_file(p)


def test_standings_head_to_head_then_wins():
    # A and B tie overall; A won their head-to-head, even though B has more wins.
    games = [dict(players=['A','B'], scores=[1,0]), dict(players=['A','C'], scores=[.5,.5]),
             dict(players=['A','C'], scores=[.5,.5]), dict(players=['B','C'], scores=[1,0]),
             dict(players=['B','C'], scores=[1,0])]
    table = standings(['A','B','C'], games, 'published')
    assert [x['participant'] for x in table] == ['A','B','C']
    assert table[0]['points'] == table[1]['points'] == 2


def test_multiway_tie_and_double_forfeit():
    games = [dict(players=['A','B'], scores=[0,0]), dict(players=['A','C'], scores=[.5,.5]),
             dict(players=['B','C'], scores=[.5,.5])]
    a = standings(['A','B','C'], games, 'seed')
    b = standings(['C','B','A'], games, 'seed')
    assert a == b
    assert sum(r['points'] for r in a) == 2


def test_series_one_extra_pair_then_seed():
    obj = Event.__new__(Event)
    counter = []
    def fake(a, b, stage):
        counter.append((a,b))
        return dict(players=[a,b], scores=[.5,.5], game_id=len(counter))
    obj.match = fake
    result = obj.series('low', 'high', 4, 'test', {'high':1, 'low':2})
    assert result['winner'] == 'high'
    assert len(counter) == 6
    assert counter == [('low','high'),('high','low')]*3
    assert result['decided_by_league_seed']


def test_engine_observation_fog_and_relative_owner():
    from engine import initial, observation
    state = initial(42)
    a, b = observation(state, 0), observation(state, 1)
    assert 18 <= a['height'] <= 21 and 18 <= a['width'] <= 21
    for obs in (a,b):
        assert sum(x == 1 for row in obs['owner'] for x in row) == 1
        assert any(0 in row for row in obs['type'])
        assert all(x == 0 for tr, ar in zip(obs['type'],obs['army']) for t,x in zip(tr,ar) if t == 0)


def test_illegal_board_action_is_pass():
    import numpy as np
    from engine import initial, step
    state = initial(42)
    passed, _ = step(state, [[1,0,0,0,0]]*2)
    illegal, _ = step(state, [[0,-500,999,0,0],[2,-999,999,0,0]])
    assert np.array_equal(passed.armies, illegal.armies)
    assert np.array_equal(passed.ownership, illegal.ownership)
