# Vercel's Python builder specifically looks for Serverless Functions inside
# the /api directory -- a root-level main.py isn't picked up by the
# `functions` config (see: https://vercel.link/unmatched-function-pattern).
# This file just re-exports the real Flask app from ../main.py so Vercel has
# an api/*.py file to build, while main.py itself stays the actual app
# (unchanged root_path, so static/ and templates/ still resolve correctly).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402,F401
