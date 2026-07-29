#!/usr/bin/env bash
set -e
export PYTHONPATH="$(cd "$(dirname "$0")" && pwd)/src"
python -m streamlit run app/streamlit_app.py
