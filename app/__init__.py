from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
VAR_DIR = ROOT_DIR / "var"
DATA_DIR = ROOT_DIR / "data"

VAR_DIR.mkdir(parents=True, exist_ok=True)
