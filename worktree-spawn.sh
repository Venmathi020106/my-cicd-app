#!/bin/bash

WORKTREE_NAME=$1
BRANCH_NAME=$2
PORT=$3

if [ -z "$WORKTREE_NAME" ] || [ -z "$BRANCH_NAME" ] || [ -z "$PORT" ]; then
  echo "Usage: ./worktree-spawn.sh <worktree-name> <branch-name> <port-number>"
  echo "Example: ./worktree-spawn.sh worktree-analytics feat/analytics 8050"
  exit 1
fi

echo "Creating worktree: $WORKTREE_NAME on branch: $BRANCH_NAME..."
git worktree add "../$WORKTREE_NAME" -b "$BRANCH_NAME"

echo "Bootstrapping .env with PORT=$PORT..."
cp .env "../$WORKTREE_NAME/.env"
echo "PORT=$PORT" >> "../$WORKTREE_NAME/.env"

echo "Worktree $WORKTREE_NAME successfully spawned at ../$WORKTREE_NAME on PORT $PORT!"
