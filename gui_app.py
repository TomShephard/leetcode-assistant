"""Entry point for the packaged GUI executable (PyInstaller target).

Running this file is equivalent to `leetcode gui`.
"""

import sys

from leetcode_assistant.gui import launch

if __name__ == "__main__":
    sys.exit(launch())
