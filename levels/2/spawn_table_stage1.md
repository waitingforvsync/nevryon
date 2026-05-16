# Stage 1 spawn schedule

Walked by `spawn_check_step` (CODE `&208A`) each time the
scroll counter advances. Both `lev_spawn_col` and
`lev_spawn_attr` are walked together until `&FF`.

| Idx | Col | Attr | Type | Y-row | V-flip | Notes |
|----:|----:|-----:|-----:|------:|:------:|-------|
|   0 | `&0C` | `&8D` | 13 | 0 | Y     |  |
|   1 | `&0C` | `&4D` | 13 | 2 | n     |  |
|   2 | `&0D` | `&8E` | 14 | 0 | Y     |  |
|   3 | `&0D` | `&4E` | 14 | 2 | n     |  |
|   4 | `&13` | `&4C` | 12 | 2 | n     |  |
|   5 | `&1B` | `&28` |  8 | 1 | n     | high-HP variant |
|   6 | `&1B` | `&4A` | 10 | 2 | n     |  |
|   7 | `&2B` | `&04` |  4 | 0 | n     | multi-shot |
|   8 | `&2B` | `&A4` |  4 | 1 | Y     | multi-shot |
|   9 | `&2C` | `&11` | 17 | 0 | n     |  |
|  10 | `&2C` | `&B1` | 17 | 1 | Y     |  |
|  11 | `&2D` | `&12` | 18 | 0 | n     |  |
|  12 | `&2D` | `&B2` | 18 | 1 | Y     |  |
|  13 | `&37` | `&0A` | 10 | 0 | n     |  |
|  14 | `&37` | `&4A` | 10 | 2 | n     |  |
|  15 | `&40` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  16 | `&45` | `&4C` | 12 | 2 | n     |  |
|  17 | `&47` | `&81` |  1 | 0 | Y     |  |
|  18 | `&47` | `&42` |  2 | 2 | n     |  |
|  19 | `&4B` | `&8D` | 13 | 0 | Y     |  |
|  20 | `&4B` | `&4D` | 13 | 2 | n     |  |
|  21 | `&4C` | `&8E` | 14 | 0 | Y     |  |
|  22 | `&4C` | `&4E` | 14 | 2 | n     |  |
|  23 | `&55` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  24 | `&55` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  25 | `&67` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  26 | `&7D` | `&88` |  8 | 0 | Y     | high-HP variant |
|  27 | `&7D` | `&49` |  9 | 2 | n     |  |
|  28 | `&94` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  29 | `&94` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  30 | `&9F` | `&0A` | 10 | 0 | n     |  |
|  31 | `&9F` | `&4A` | 10 | 2 | n     |  |
|  32 | `&A3` | `&8C` | 12 | 0 | Y     |  |
|  33 | `&B2` | `&8D` | 13 | 0 | Y     |  |
|  34 | `&B2` | `&4D` | 13 | 2 | n     |  |
|  35 | `&B3` | `&8E` | 14 | 0 | Y     |  |
|  36 | `&B3` | `&4E` | 14 | 2 | n     |  |
|  37 | `&B6` | `&8C` | 12 | 0 | Y     |  |
|  38 | `&B6` | `&4A` | 10 | 2 | n     |  |
|  39 | `&CA` | `&84` |  4 | 0 | Y     | multi-shot |
|  40 | `&CA` | `&44` |  4 | 2 | n     | multi-shot |
|  41 | `&CB` | `&91` | 17 | 0 | Y     |  |
|  42 | `&CB` | `&51` | 17 | 2 | n     |  |
|  43 | `&CC` | `&92` | 18 | 0 | Y     |  |
|  44 | `&CC` | `&52` | 18 | 2 | n     |  |
|  45 | `&DF` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  46 | `&DF` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  47 | `&EB` | `&8C` | 12 | 0 | Y     |  |
|  48 | `&EB` | `&4C` | 12 | 2 | n     |  |
|  49 | `&ED` | `&84` |  4 | 0 | Y     | multi-shot |
|  50 | `&ED` | `&33` | 19 | 1 | n     | multi-shot |
|  51 | `&ED` | `&44` |  4 | 2 | n     | multi-shot |
|  52 | `&EE` | `&85` |  5 | 0 | Y     |  |
|  53 | `&EE` | `&2F` | 15 | 1 | n     |  |
|  54 | `&EE` | `&45` |  5 | 2 | n     |  |
| ... | `&FF` | — | — | — | — | terminator at slot 55 (55 active) |
