#!/usr/bin/env bash
# Mint a fake-sat cashu token against testnut (or MINT_URL) using the nucula
# rig's payer. Writes the token to the file given as $1 (default stdout is
# suppressed; the token is a bearer asset — keep it in files, not logs).
#
# FEE HEADROOM RULE (bench-proven 2026-10-22): the testnut sat keyset charges
# input_fee_ppk=100 — a 1-sat token's value is entirely consumed by the input
# fee on redeem (cdk mint: TransactionUnbalanced(0,0,0) = empty OUTPUTS).
# Always mint >= 2 sats for receive flows; 21 is the house default.
set -euo pipefail

SATS="${HIL_MINT_SATS:-21}"
MINT="${MINT_URL:-https://testnut.cashu.space}"
OUT="${1:?usage: mint_token.sh <outfile> [sats]}"
[ "${2:-}" ] && SATS="$2"

RIG_DIR="${RIG_DIR:-/opt/bench/nucula-rig/rig}"
TARGET_DIR="${RIG_TARGET_DIR:-/tmp/opencode/phone-hil/nucula/rig/target-hil}"

cd "$RIG_DIR"
env PATH=/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV= MINT_URL="$MINT" HIL_MINT_SATS="$SATS" \
    CARGO_TARGET_DIR="$TARGET_DIR" \
    cargo test --features payer mints_a_token_from_the_running_mint -- --ignored --nocapture \
    > /tmp/mint-token-run.log 2>&1 || { tail -5 /tmp/mint-token-run.log; exit 1; }

grep -o 'TOKEN=[^ ]*' /tmp/mint-token-run.log | sed 's/^TOKEN=//' | head -1 > "$OUT"
[ -s "$OUT" ] || { echo "no token in output" >&2; exit 1; }
echo "minted $(wc -c < "$OUT") char token for ${SATS} sats -> $OUT"
