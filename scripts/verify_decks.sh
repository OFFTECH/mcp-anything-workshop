#!/usr/bin/env bash
# Runs every workshop deck with the real CalculiX and Gmsh and compares the results with the analytic references.
# Only inside the workshop dev container. Options: --keep DIR (keep the run folders), --only 01|02|04.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m workshop.verify "$@"
