import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / '.agents' / 'skills' / 'ingest' / 'scripts'
FIXTURE = Path(__file__).resolve().parent / 'sample_feed.xml'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
