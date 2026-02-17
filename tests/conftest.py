import sys
import pathlib

# Ensure project root on path for pytest invocation from repo folder
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mixin_system
import demo_game.patches  # register patches

mixin_system.init()
