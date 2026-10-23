# Bench geometry — phone positions (photos pending owner)

The registry's `requires.phone_at` values map to these PHYSICAL positions.
Photos land here as the owner takes them; ASCII until then.

## nucula-coil
Phone flat on the nucula-c3 board's coil area (label-up).
[photo: owner]

## m5stick-coil
Phone flat over the m5stick MFRC522 antenna (the stick's coil face).
[photo: owner]

## acr-stack
Phone DIRECTLY on the ACR1252 antenna, label up, coil area centered.
MEASURED 2026-10-23: a m5stick body between phone and ACR (phone >
m5stick > ACR) KILLS coupling — NoCard on a healthy armed phone + healthy
reader (PCB/battery shields the 13.56 MHz path). The stick goes BESIDE
the antenna, never between. The c3 board, by contrast, couples fine as a
spacer (phone > nucula > ACR worked historically).
[photo: owner]

## off-bench
Phone away from all reader fields (idle/on charger).

Positions are SET by `matrixctl set phone.at <value>` and VERIFIED by
`matrixctl verify-state` mid-run. Drift = loud fail, never mystery red.
