"""Console-script entry point: launch the Streamlit app.

`university-web` is sugar for `streamlit run src/university_web/app.py`; any extra CLI args
are forwarded to streamlit (e.g. `university-web --server.port 9000`).
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli as stcli

APP = Path(__file__).with_name("app.py")


def main() -> None:
    """Hand off to Streamlit's CLI with our app file as the target."""
    sys.argv = ["streamlit", "run", str(APP), *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
