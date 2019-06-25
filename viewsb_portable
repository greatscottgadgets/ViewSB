#!/bin/sh
# Quick, portable runner script for ViewSB; intended to run the present
# version without install. You'll still need the dependencies.

# Run the ViewSB subcommand, but with the current path in the user's
# PYTHONPATH, so they don't have to have our module installed.
PYTHONPATH="$PYTHONPATH:$(pwd)" python3 -m viewsb.commands.viewsb $@

