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
Phone on TOP of the ACR1252 antenna (the m5stick may be stacked beneath
the phone for crosstalk cells: phone > m5stick > ACR).
[photo: owner]

## off-bench
Phone away from all reader fields (idle/on charger).

Positions are SET by `matrixctl set phone.at <value>` and VERIFIED by
`matrixctl verify-state` mid-run. Drift = loud fail, never mystery red.
