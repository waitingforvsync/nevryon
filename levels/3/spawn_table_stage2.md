# Stage 2 spawn schedule

Walked by `spawn_check_step` (CODE `&208A`) each time the
scroll counter advances. Both `lev_spawn_col` and
`lev_spawn_attr` are walked together until `&FF`.

| Idx | Col | Attr | Type | Y-row | V-flip | Notes |
|----:|----:|-----:|-----:|------:|:------:|-------|
|   0 | `&04` | `&44` |  4 | 2 | n     | multi-shot |
|   1 | `&05` | `&4B` | 11 | 2 | n     |  |
|   2 | `&05` | `&29` |  9 | 1 | n     |  |
|   3 | `&06` | `&4A` | 10 | 2 | n     |  |
|   4 | `&06` | `&2D` | 13 | 1 | n     |  |
|   5 | `&07` | `&4B` | 11 | 2 | n     |  |
|   6 | `&07` | `&2E` | 14 | 1 | n     |  |
|   7 | `&08` | `&4E` | 14 | 2 | n     |  |
|   8 | `&24` | `&4D` | 13 | 2 | n     |  |
|   9 | `&25` | `&28` |  8 | 1 | n     | high-HP variant |
|  10 | `&25` | `&4A` | 10 | 2 | n     |  |
|  11 | `&26` | `&26` |  6 | 1 | n     | CODE2 spawn_enemy_missile |
|  12 | `&26` | `&41` |  1 | 2 | n     |  |
|  13 | `&27` | `&45` |  5 | 2 | n     |  |
|  14 | `&2D` | `&4B` | 11 | 2 | n     |  |
|  15 | `&2D` | `&27` |  7 | 1 | n     | force-field (procedural, no sprite) |
|  16 | `&3E` | `&44` |  4 | 2 | n     | multi-shot |
|  17 | `&3F` | `&41` |  1 | 2 | n     |  |
|  18 | `&3F` | `&2D` | 13 | 1 | n     |  |
|  19 | `&40` | `&2B` | 11 | 1 | n     |  |
|  20 | `&40` | `&4A` | 10 | 2 | n     |  |
|  21 | `&41` | `&2E` | 14 | 1 | n     |  |
|  22 | `&41` | `&41` |  1 | 2 | n     |  |
|  23 | `&42` | `&4E` | 14 | 2 | n     |  |
|  24 | `&49` | `&48` |  8 | 2 | n     | high-HP variant |
|  25 | `&4A` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  26 | `&5E` | `&4C` | 12 | 2 | n     |  |
|  27 | `&5F` | `&27` |  7 | 1 | n     | force-field (procedural, no sprite) |
|  28 | `&5F` | `&4A` | 10 | 2 | n     |  |
|  29 | `&60` | `&45` |  5 | 2 | n     |  |
|  30 | `&6D` | `&9B` | 27 | 0 | Y     |  |
|  31 | `&6E` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  32 | `&6E` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  33 | `&70` | `&8C` | 12 | 0 | Y     |  |
|  34 | `&71` | `&8A` | 10 | 0 | Y     |  |
|  35 | `&71` | `&A9` |  9 | 1 | Y     |  |
|  36 | `&72` | `&85` |  5 | 0 | Y     |  |
|  37 | `&74` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  38 | `&74` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  39 | `&7E` | `&4D` | 13 | 2 | n     |  |
|  40 | `&7F` | `&4A` | 10 | 2 | n     |  |
|  41 | `&7F` | `&27` |  7 | 1 | n     | force-field (procedural, no sprite) |
|  42 | `&80` | `&2D` | 13 | 1 | n     |  |
|  43 | `&80` | `&41` |  1 | 2 | n     |  |
|  44 | `&81` | `&2E` | 14 | 1 | n     |  |
|  45 | `&81` | `&4B` | 11 | 2 | n     |  |
|  46 | `&82` | `&45` |  5 | 2 | n     |  |
|  47 | `&89` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  48 | `&9F` | `&4C` | 12 | 2 | n     |  |
|  49 | `&A0` | `&26` |  6 | 1 | n     | CODE2 spawn_enemy_missile |
|  50 | `&A0` | `&41` |  1 | 2 | n     |  |
|  51 | `&A1` | `&4E` | 14 | 2 | n     |  |
|  52 | `&A5` | `&4D` | 13 | 2 | n     |  |
|  53 | `&A6` | `&42` |  2 | 2 | n     |  |
|  54 | `&A7` | `&4E` | 14 | 2 | n     |  |
|  55 | `&AD` | `&4A` | 10 | 2 | n     |  |
|  56 | `&AD` | `&29` |  9 | 1 | n     |  |
|  57 | `&B5` | `&49` |  9 | 2 | n     |  |
|  58 | `&B6` | `&4B` | 11 | 2 | n     |  |
|  59 | `&B6` | `&26` |  6 | 1 | n     | CODE2 spawn_enemy_missile |
|  60 | `&BC` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  61 | `&CC` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  62 | `&CC` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  63 | `&D4` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  64 | `&D4` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  65 | `&DC` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  66 | `&DC` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  67 | `&E2` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  68 | `&EB` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  69 | `&EC` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  70 | `&ED` | `&04` |  4 | 0 | n     | multi-shot |
|  71 | `&ED` | `&33` | 19 | 1 | n     | multi-shot |
|  72 | `&ED` | `&C4` |  4 | 2 | Y     | multi-shot |
|  73 | `&EE` | `&0E` | 14 | 0 | n     |  |
|  74 | `&EE` | `&2F` | 15 | 1 | n     |  |
|  75 | `&EE` | `&CE` | 14 | 2 | Y     |  |
| ... | `&FF` | — | — | — | — | terminator at slot 76 (76 active) |
