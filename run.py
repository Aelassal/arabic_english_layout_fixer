"""Entry point for the packaged apps (PyInstaller runs this file as a top-level script).

layoutfix/__main__.py uses a relative import, which only works with `python -m layoutfix`.
"""
from layoutfix.app import main

if __name__ == "__main__":
    main()
