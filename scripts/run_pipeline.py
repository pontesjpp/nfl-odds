#!/usr/bin/env python3
"""
NFL Odds EV Pipeline CLI Entrypoint.
Delegates execution to the core pipeline module in src/nfl_odds/pipeline.py.
"""
import sys
from nfl_odds.pipeline import main

if __name__ == "__main__":
    main()
