import sys

from app import render

out = render("<world>")
assert out == "Hello &lt;world&gt;", out
print("render ok:", out)
sys.exit(0)
