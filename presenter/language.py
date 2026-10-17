"""Small shared lexical primitives; no model work in the prepared cue path."""
import re

STOP = set("a an the of to in is it and or for with this that we you our can are as be from on at by have has what how why now let about explain first then through before after they these those did do does not so which more alone using".split())


def tokens(s):
    words = (t.lower() for t in re.findall(r"[A-Za-z0-9]+", s))
    return {w[:-1] if w.endswith('s') and not w.endswith(('ss','us','is')) else w
            for w in words if len(w) > 2 and w not in STOP}


def sequence(s):
    return [word for raw in re.findall(r"[A-Za-z0-9]+", s) for word in tokens(raw)]
