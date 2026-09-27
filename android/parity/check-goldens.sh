#!/usr/bin/env bash
# Regenerates the web-parity goldens from the website's own modules and
# fails if they differ from the committed ones (the web module changed
# and the Android port hasn't been checked against it). Then runs the
# Kotlin parity tests.
#
#   android/parity/check-goldens.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

ln -sfn ../../web/node_modules "$here/node_modules"
"$repo/web/node_modules/.bin/vitest" run --config "$here/vitest.config.mts"

if ! git -C "$repo" diff --quiet -- android/app/src/test/resources/parity; then
  echo "The goldens changed: the web module's outputs differ from the committed ones."
  echo "Review the diff, port the change to Kotlin, and commit the new goldens."
  git -C "$repo" diff --stat -- android/app/src/test/resources/parity
  exit 1
fi

cd "$here/.."
./gradlew :app:testLocalDebugUnitTest --tests 'com.debatecoach.app.visual.parity.*'
