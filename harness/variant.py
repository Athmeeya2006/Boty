"""Make a parameter variant of a bot: harness/variant.py base.py out.py KEY=VALUE ...
Only PARAMS entries are changed (by exact line match), so the code stays identical."""
import re
import sys

base, out, *kv = sys.argv[1:]
src = open(base).read()
for item in kv:
    k, v = item.split("=", 1)
    pat = re.compile(r'(\n\s*"%s":\s*)([^,]+)(,)' % re.escape(k))
    if not pat.search(src):
        sys.exit(f"param {k} not found")
    src = pat.sub(lambda m: m.group(1) + v + m.group(3), src, count=1)
open(out, "w").write(src)
