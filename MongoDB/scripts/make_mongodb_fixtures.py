"""Create explicitly labelled engineering fixtures; not source-data preparation."""
import argparse
import sys
from pathlib import Path
import _mongo_bootstrap
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"/"mongodb"))
from fixture_release import make_fixture

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="tests/fixtures/TEST_FIXTURE_ONLY")
    args = parser.parse_args()
    destination = Path(args.out)
    if destination.exists():
        parser.error("Choose a new fixture directory; existing files are not overwritten")
    print(make_fixture(destination))
