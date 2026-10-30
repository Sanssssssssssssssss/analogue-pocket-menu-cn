#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
work="$root/.build/native"
if [ -e "$work" ]; then
  printf 'Build directory exists; retain it as a versioned backup before a new build.\n' >&2
  exit 2
fi
compiler=${QUARTUS_SH:-quartus_sh}
command -v "$compiler" >/dev/null
mkdir -p "$work"
cp -R "$root/core/src" "$work/src"
cd "$work/src"
"$compiler" --flow compile ap_core.qpf > "$work/quartus.log" 2>&1
printf 'Compilation finished. Review fitter and full timing reports in .build/native/src/output_files.\n'
