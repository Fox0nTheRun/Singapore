"""Allow direct script commands without changing D's shared packaging files."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
