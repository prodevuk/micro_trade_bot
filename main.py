"""
DEPRECATED: This file is kept for backward compatibility only.
Please use bot.py as the entry point instead.

This file will be removed in a future version.
"""

import warnings
import sys

# Show deprecation warning
warnings.warn(
    "main.py is deprecated. Please use 'python bot.py' instead. "
    "This file will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2
)

# Print deprecation message to console
print("=" * 70)
print("WARNING: main.py is deprecated!")
print("Please use 'python bot.py' instead.")
print("=" * 70)
print()

# Import and call the main function from bot.py
from bot import main

if __name__ == "__main__":
    main()
