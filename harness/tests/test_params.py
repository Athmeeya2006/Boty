"""Static check: every PARAMS["KEY"] used in the bot is defined in the PARAMS dict, and no
DEBUG print path is enabled. Run: python3 harness/tests/test_params.py BOT"""
import ast
import re
import sys

src = open(sys.argv[1]).read()
tree = ast.parse(src)
defined = set()
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets):
        defined = {k.value for k in node.value.keys}
used = set(re.findall(r'PARAMS\["([A-Z0-9_]+)"\]', src))
missing = sorted(used - defined)
unused = sorted(defined - used)
debug_on = re.search(r"^DEBUG\s*=\s*True", src, re.M) is not None
print(f"{len(used)} params used, {len(defined)} defined; missing: {missing}; unused: {unused}; DEBUG on: {debug_on}")
sys.exit(1 if missing or debug_on else 0)
