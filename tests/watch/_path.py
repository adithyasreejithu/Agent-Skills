import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / '.agents' / 'skills' / 'watch' / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
