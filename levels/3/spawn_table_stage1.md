# Stage 1 spawn schedule

Walked by `spawn_check_step` (CODE `&208A`) each time the
scroll counter advances. Both `lev_spawn_col` and
`lev_spawn_attr` are walked together until `&FF`.

| Idx | Col | Attr | Type | Y-row | V-flip | Notes |
|----:|----:|-----:|-----:|------:|:------:|-------|
|   0 | `&06` | `&4D` | 13 | 2 | n     |  |
|   1 | `&07` | `&4E` | 14 | 2 | n     |  |
|   2 | `&0B` | `&41` |  1 | 2 | n     |  |
|   3 | `&0C` | `&42` |  2 | 2 | n     |  |
|   4 | `&24` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|   5 | `&27` | `&26` |  6 | 1 | n     | CODE2 spawn_enemy_missile |
|   6 | `&27` | `&4A` | 10 | 2 | n     |  |
|   7 | `&2A` | `&4C` | 12 | 2 | n     |  |
|   8 | `&3A` | `&26` |  6 | 1 | n     | CODE2 spawn_enemy_missile |
|   9 | `&3A` | `&4A` | 10 | 2 | n     |  |
|  10 | `&40` | `&4B` | 11 | 2 | n     |  |
|  11 | `&42` | `&4B` | 11 | 2 | n     |  |
|  12 | `&49` | `&4B` | 11 | 2 | n     |  |
|  13 | `&4B` | `&4B` | 11 | 2 | n     |  |
|  14 | `&5E` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  15 | `&6E` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  16 | `&6E` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  17 | `&74` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  18 | `&74` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  19 | `&7E` | `&4C` | 12 | 2 | n     |  |
|  20 | `&7F` | `&4C` | 12 | 2 | n     |  |
|  21 | `&86` | `&4C` | 12 | 2 | n     |  |
|  22 | `&87` | `&4C` | 12 | 2 | n     |  |
|  23 | `&A2` | `&44` |  4 | 2 | n     | multi-shot |
|  24 | `&A3` | `&51` | 17 | 2 | n     |  |
|  25 | `&A4` | `&52` | 18 | 2 | n     |  |
|  26 | `&BD` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  27 | `&C6` | `&43` |  3 | 2 | n     |  |
|  28 | `&CC` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  29 | `&CC` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  30 | `&D4` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  31 | `&D4` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  32 | `&DB` | `&88` |  8 | 0 | Y     | high-HP variant |
|  33 | `&DB` | `&48` |  8 | 2 | n     | high-HP variant |
|  34 | `&DD` | `&81` |  1 | 0 | Y     |  |
|  35 | `&DD` | `&42` |  2 | 2 | n     |  |
|  36 | `&DE` | `&81` |  1 | 0 | Y     |  |
|  37 | `&DE` | `&42` |  2 | 2 | n     |  |
|  38 | `&EB` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  39 | `&EC` | `&44` |  4 | 2 | n     | multi-shot |
|  40 | `&ED` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  41 | `&ED` | `&24` |  4 | 1 | n     | multi-shot |
|  42 | `&ED` | `&45` |  5 | 2 | n     |  |
|  43 | `&EE` | `&04` |  4 | 0 | n     | multi-shot |
|  44 | `&EE` | `&25` |  5 | 1 | n     |  |
|  45 | `&EE` | `&4F` | 15 | 2 | n     |  |
| ... | `&FF` | — | — | — | — | terminator at slot 46 (46 active) |
