"""Web demo + validation app (Streamlit) — composition root over DB layer and agent.

This is the one web-side module tree allowed to import BOTH university_db and
university_agent. The agent package itself still never imports the DB layer.
"""

from __future__ import annotations

__version__ = "0.1.0"
