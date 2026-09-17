#!/usr/bin/env bash
cd "$(dirname "$0")" && docker compose down && echo "Stopped. Your data is kept."
