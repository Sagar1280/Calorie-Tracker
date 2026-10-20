import os
import tempfile
from pathlib import Path

_TEST_DIR = Path(tempfile.mkdtemp(prefix="calorie-tracker-tests-"))
os.environ["CALORIE_DB_PATH"] = str(_TEST_DIR / "test.db")
