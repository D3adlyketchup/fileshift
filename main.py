"""
FileShift — Universal File Converter
Entry point: python main.py
"""

import sys
import os

# Ensure the app directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from app.ui import FileshiftApp

if __name__ == "__main__":
    app = FileshiftApp()
    app.mainloop()
