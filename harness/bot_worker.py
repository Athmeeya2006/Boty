"""Local copy of evaluator/worker.py: same JSON-lines protocol, bot path from argv.

Run as: python3.12 -I -S -B harness/bot_worker.py path/to/bot.py
-I -S keeps site-packages out, so a bot cannot import numpy or jax by accident.
"""
import contextlib
import importlib.util
import json
import sys
import traceback


def main():
    path = sys.argv[1]
    output = sys.stdout
    output.write('{"ready":true}\n')
    output.flush()
    module = None
    for line in sys.stdin:
        request = json.loads(line)
        try:
            with contextlib.redirect_stdout(sys.stderr):
                if module is None:
                    spec = importlib.util.spec_from_file_location("submission", path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                action = module.act(request["observation"])
            reply = {"id": request["id"], "action": action}
            data = json.dumps(reply, allow_nan=False)
            if len(data) > 2048:
                raise ValueError("action response is too large")
            output.write(data + "\n")
            output.flush()
        except BaseException:
            traceback.print_exc(file=sys.stderr)
            output.write(json.dumps({"id": request["id"], "error": "bot exception"}) + "\n")
            output.flush()
            return


if __name__ == "__main__":
    main()
