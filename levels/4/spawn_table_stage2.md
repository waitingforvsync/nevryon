# Stage 2 spawn schedule

Walked by `spawn_check_step` (CODE `&208A`) each time the
scroll counter advances. Both `lev_spawn_col` and
`lev_spawn_attr` are walked together until `&FF`.

| Idx | Col | Attr | Type | Y-row | V-flip | Notes |
|----:|----:|-----:|-----:|------:|:------:|-------|
|   0 | `&05` | `&8B` | 11 | 0 | Y     |  |
|   1 | `&05` | `&4B` | 11 | 2 | n     |  |
|   2 | `&09` | `&89` |  9 | 0 | Y     |  |
|   3 | `&0A` | `&8C` | 12 | 0 | Y     |  |
|   4 | `&13` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|   5 | `&13` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|   6 | `&14` | `&41` |  1 | 2 | n     |  |
|   7 | `&1C` | `&81` |  1 | 0 | Y     |  |
|   8 | `&1C` | `&42` |  2 | 2 | n     |  |
|   9 | `&1E` | `&41` |  1 | 2 | n     |  |
|  10 | `&23` | `&0A` | 10 | 0 | n     |  |
|  11 | `&26` | `&2A` | 10 | 1 | n     |  |
|  12 | `&28` | `&4A` | 10 | 2 | n     |  |
|  13 | `&38` | `&4A` | 10 | 2 | n     |  |
|  14 | `&38` | `&28` |  8 | 1 | n     | high-HP variant |
|  15 | `&42` | `&81` |  1 | 0 | Y     |  |
|  16 | `&42` | `&42` |  2 | 2 | n     |  |
|  17 | `&43` | `&8D` | 13 | 0 | Y     |  |
|  18 | `&43` | `&4D` | 13 | 2 | n     |  |
|  19 | `&44` | `&8E` | 14 | 0 | Y     |  |
|  20 | `&44` | `&4E` | 14 | 2 | n     |  |
|  21 | `&45` | `&81` |  1 | 0 | Y     |  |
|  22 | `&45` | `&42` |  2 | 2 | n     |  |
|  23 | `&50` | `&08` |  8 | 0 | n     | high-HP variant |
|  24 | `&50` | `&A8` |  8 | 1 | Y     | high-HP variant |
|  25 | `&60` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  26 | `&60` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  27 | `&65` | `&4A` | 10 | 2 | n     |  |
|  28 | `&65` | `&28` |  8 | 1 | n     | high-HP variant |
|  29 | `&66` | `&4C` | 12 | 2 | n     |  |
|  30 | `&69` | `&8B` | 11 | 0 | Y     |  |
|  31 | `&6F` | `&84` |  4 | 0 | Y     | multi-shot |
|  32 | `&70` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  33 | `&71` | `&91` | 17 | 0 | Y     |  |
|  34 | `&72` | `&92` | 18 | 0 | Y     |  |
|  35 | `&75` | `&81` |  1 | 0 | Y     |  |
|  36 | `&75` | `&41` |  1 | 2 | n     |  |
|  37 | `&7F` | `&4A` | 10 | 2 | n     |  |
|  38 | `&7F` | `&28` |  8 | 1 | n     | high-HP variant |
|  39 | `&86` | `&89` |  9 | 0 | Y     |  |
|  40 | `&86` | `&49` |  9 | 2 | n     |  |
|  41 | `&88` | `&8B` | 11 | 0 | Y     |  |
|  42 | `&88` | `&4B` | 11 | 2 | n     |  |
|  43 | `&8E` | `&8D` | 13 | 0 | Y     |  |
|  44 | `&8F` | `&8E` | 14 | 0 | Y     |  |
|  45 | `&95` | `&2A` | 10 | 1 | n     |  |
|  46 | `&9A` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  47 | `&9A` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  48 | `&9E` | `&4B` | 11 | 2 | n     |  |
|  49 | `&A2` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  50 | `&A2` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  51 | `&AA` | `&8B` | 11 | 0 | Y     |  |
|  52 | `&AA` | `&4C` | 12 | 2 | n     |  |
|  53 | `&AE` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  54 | `&BC` | `&4A` | 10 | 2 | n     |  |
|  55 | `&BC` | `&27` |  7 | 1 | n     | force-field (procedural, no sprite) |
|  56 | `&C5` | `&4A` | 10 | 2 | n     |  |
|  57 | `&C5` | `&29` |  9 | 1 | n     |  |
|  58 | `&CE` | `&88` |  8 | 0 | Y     | high-HP variant |
|  59 | `&CE` | `&49` |  9 | 2 | n     |  |
|  60 | `&D0` | `&8B` | 11 | 0 | Y     |  |
|  61 | `&D0` | `&4B` | 11 | 2 | n     |  |
|  62 | `&D2` | `&84` |  4 | 0 | Y     | multi-shot |
|  63 | `&D2` | `&44` |  4 | 2 | n     | multi-shot |
|  64 | `&D3` | `&91` | 17 | 0 | Y     |  |
|  65 | `&D3` | `&51` | 17 | 2 | n     |  |
|  66 | `&D4` | `&92` | 18 | 0 | Y     |  |
|  67 | `&D4` | `&52` | 18 | 2 | n     |  |
|  68 | `&DE` | `&88` |  8 | 0 | Y     | high-HP variant |
|  69 | `&DE` | `&48` |  8 | 2 | n     | high-HP variant |
|  70 | `&E4` | `&8A` | 10 | 0 | Y     |  |
|  71 | `&E4` | `&49` |  9 | 2 | n     |  |
|  72 | `&EC` | `&20` |  0 | 1 | n     |  |
|  73 | `&ED` | `&84` |  4 | 0 | Y     | multi-shot |
|  74 | `&ED` | `&33` | 19 | 1 | n     | multi-shot |
|  75 | `&ED` | `&44` |  4 | 2 | n     | multi-shot |
|  76 | `&EE` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  77 | `&EE` | `&30` | 16 | 1 | n     | boss / heavy |
|  78 | `&EE` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
| ... | `&FF` | — | — | — | — | terminator at slot 79 (79 active) |
