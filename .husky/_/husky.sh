#!/usr/bin/env sh
if [ -f ~/.huskyrc ]; then
  . ~/.huskyrc
fi

if [ -f ~/.huskyrc.local ]; then
  . ~/.huskyrc.local
fi

HOOK_NAME="$(basename -- "$0")"
GIT_PARAMS="$*"

if [ -f "$(dirname -- "$0")/../.husky/common" ]; then
  . "$(dirname -- "$0")/../.husky/common"
fi

if [ -f "$(dirname -- "$0")/../.husky/$HOOK_NAME" ]; then
  "$(dirname -- "$0")/../.husky/$HOOK_NAME" "$@"
fi
