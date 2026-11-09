"""Launch from the project root: streamlit run app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from hdb_insights.app.ui import main  # noqa: E402

if __name__ == "__main__":
    main()
