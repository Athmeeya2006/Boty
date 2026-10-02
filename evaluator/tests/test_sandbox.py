"""Actual Docker integration tests. Run after evaluate.py build."""
import os
from pathlib import Path
import subprocess

import pytest

from sandbox import Bot, BotFault, Docker


@pytest.fixture
def make_bot(tmp_path):
    try:
        subprocess.run(['docker','image','inspect','codebot-python:1'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('Build codebot-python:1 and start Docker to run integration tests')
    bots = []
    def create(source):
        path = tmp_path / (str(len(bots)) + '.py')
        path.write_text(source)
        path.chmod(0o644)
        bot = Bot(Docker(), path, 'codebot-python:1', min(os.sched_getaffinity(0)),
                  tmp_path / (path.stem + '.stderr'))
        bots.append(bot)
        return bot
    yield create
    for b in bots:
        b.close()


def test_offline_cpu_permissions_and_lifecycle(make_bot):
    bot = make_bot('''
import os, socket
count = 0
def act(obs):
    global count
    assert os.getuid() == 65534
    assert len(os.sched_getaffinity(0)) == 1
    assert not os.path.exists('/var/run/docker.sock')
    assert not os.path.exists('/opt/codebot/engine.py')
    s = socket.socket()
    s.settimeout(0.1)
    try:
        s.connect(('1.1.1.1', 53))
        raise AssertionError('network unexpectedly reachable')
    except OSError:
        pass
    finally:
        s.close()
    try:
        open('/submission/bot.py', 'a')
        raise AssertionError('submission unexpectedly writable')
    except OSError:
        pass
    count += 1
    print('diagnostic')
    return [1,count,0,0,0]
''')
    first, _ = bot.act({'turn':0}, first=True)
    second, _ = bot.act({'turn':1})
    assert first[1] == 1 and second[1] == 2
    info = bot.docker.api('GET', f'/containers/{bot.name}/json')
    assert info['State']['Paused']
    assert info['HostConfig']['Memory'] == 2*1024**3
    assert info['HostConfig']['MemorySwap'] == 2*1024**3
    assert info['HostConfig']['PidsLimit'] == 32
    assert info['HostConfig']['NetworkMode'] == 'none'


@pytest.mark.parametrize('source', [
    'def act(obs): raise ValueError("broken")',
    'def act(obs): return [True,0,0,0,0]',
    'import os\ndef act(obs): os._exit(1)',
    'def act(obs): return [0,0,0,9,0]',
    'import requests\ndef act(obs): return [1,0,0,0,0]',
])
def test_faults_forfeit(make_bot, source):
    bot = make_bot(source)
    with pytest.raises(BotFault):
        bot.act({'turn':0}, first=True)


def test_external_timeout_kills_descendants(make_bot):
    bot = make_bot('def act(obs):\n    while True: pass\n')
    with pytest.raises(BotFault, match='deadline'):
        bot.act({'turn':0}, move_ms=50)
    result = subprocess.run(['docker','inspect',bot.name], capture_output=True)
    assert result.returncode != 0


def test_huge_output_is_bounded(make_bot):
    bot = make_bot('import os\ndef act(obs):\n    os.write(1,b"x"*10000)\n    return [1,0,0,0,0]\n')
    with pytest.raises(BotFault, match='output'):
        bot.act({'turn':0}, first=True)
