# Stage 2 spawn schedule

Walked by `spawn_check_step` (CODE `&208A`) each time the
scroll counter advances. Both `lev_spawn_col` and
`lev_spawn_attr` are walked together until `&FF`.

| Idx | Col | Attr | Type | Y-row | V-flip | Notes |
|----:|----:|-----:|-----:|------:|:------:|-------|
|   0 | `&0C` | `&8D` | 13 | 0 | Y     |  |
|   1 | `&0C` | `&4D` | 13 | 2 | n     |  |
|   2 | `&0D` | `&8E` | 14 | 0 | Y     |  |
|   3 | `&0D` | `&4E` | 14 | 2 | n     |  |
|   4 | `&0E` | `&84` |  4 | 0 | Y     | multi-shot |
|   5 | `&0E` | `&44` |  4 | 2 | n     | multi-shot |
|   6 | `&0F` | `&8C` | 12 | 0 | Y     |  |
|   7 | `&0F` | `&4C` | 12 | 2 | n     |  |
|   8 | `&1E` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|   9 | `&1E` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  10 | `&23` | `&4B` | 11 | 2 | n     |  |
|  11 | `&24` | `&4B` | 11 | 2 | n     |  |
|  12 | `&25` | `&4B` | 11 | 2 | n     |  |
|  13 | `&2E` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  14 | `&32` | `&48` |  8 | 2 | n     | high-HP variant |
|  15 | `&38` | `&33` | 19 | 1 | n     | multi-shot |
|  16 | `&39` | `&2F` | 15 | 1 | n     |  |
|  17 | `&39` | `&84` |  4 | 0 | Y     | multi-shot |
|  18 | `&3A` | `&AC` | 12 | 1 | Y     |  |
|  19 | `&3A` | `&0F` | 15 | 0 | n     |  |
|  20 | `&3B` | `&8C` | 12 | 0 | Y     |  |
|  21 | `&4A` | `&01` |  1 | 0 | n     |  |
|  22 | `&4A` | `&22` |  2 | 1 | n     |  |
|  23 | `&4A` | `&43` |  3 | 2 | n     |  |
|  24 | `&5A` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  25 | `&5A` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  26 | `&60` | `&22` |  2 | 1 | n     |  |
|  27 | `&68` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  28 | `&73` | `&13` | 19 | 0 | n     | multi-shot |
|  29 | `&74` | `&8F` | 15 | 0 | Y     |  |
|  30 | `&75` | `&8C` | 12 | 0 | Y     |  |
|  31 | `&79` | `&53` | 19 | 2 | n     | multi-shot |
|  32 | `&7A` | `&27` |  7 | 1 | n     | force-field (procedural, no sprite) |
|  33 | `&7A` | `&4F` | 15 | 2 | n     |  |
|  34 | `&7B` | `&4C` | 12 | 2 | n     |  |
|  35 | `&81` | `&88` |  8 | 0 | Y     | high-HP variant |
|  36 | `&81` | `&48` |  8 | 2 | n     | high-HP variant |
|  37 | `&88` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|  38 | `&88` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  39 | `&93` | `&88` |  8 | 0 | Y     | high-HP variant |
|  40 | `&93` | `&48` |  8 | 2 | n     | high-HP variant |
|  41 | `&9C` | `&01` |  1 | 0 | n     |  |
|  42 | `&9C` | `&22` |  2 | 1 | n     |  |
|  43 | `&9C` | `&43` |  3 | 2 | n     |  |
|  44 | `&A3` | `&88` |  8 | 0 | Y     | high-HP variant |
|  45 | `&A3` | `&48` |  8 | 2 | n     | high-HP variant |
|  46 | `&A8` | `&01` |  1 | 0 | n     |  |
|  47 | `&A8` | `&42` |  2 | 2 | n     |  |
|  48 | `&AF` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|  49 | `&B8` | `&4B` | 11 | 2 | n     |  |
|  50 | `&B9` | `&8B` | 11 | 0 | Y     |  |
|  51 | `&BA` | `&4B` | 11 | 2 | n     |  |
|  52 | `&C4` | `&87` |  7 | 0 | Y     | force-field (procedural, no sprite) |
|  53 | `&C4` | `&47` |  7 | 2 | n     | force-field (procedural, no sprite) |
|  54 | `&CB` | `&4B` | 11 | 2 | n     |  |
|  55 | `&CB` | `&48` |  8 | 2 | n     | high-HP variant |
|  56 | `&D0` | `&01` |  1 | 0 | n     |  |
|  57 | `&D0` | `&42` |  2 | 2 | n     |  |
|  58 | `&D5` | `&33` | 19 | 1 | n     | multi-shot |
|  59 | `&D6` | `&2F` | 15 | 1 | n     |  |
|  60 | `&D6` | `&44` |  4 | 2 | n     | multi-shot |
|  61 | `&D7` | `&2C` | 12 | 1 | n     |  |
|  62 | `&D7` | `&50` | 16 | 2 | n     | boss / heavy |
|  63 | `&D8` | `&4C` | 12 | 2 | n     |  |
|  64 | `&E1` | `&01` |  1 | 0 | n     |  |
|  65 | `&E1` | `&42` |  2 | 2 | n     |  |
|  66 | `&EC` | `&0D` | 13 | 0 | n     |  |
|  67 | `&EC` | `&AD` | 13 | 1 | Y     |  |
|  68 | `&ED` | `&0E` | 14 | 0 | n     |  |
|  69 | `&ED` | `&AE` | 14 | 1 | Y     |  |
|  70 | `&ED` | `&53` | 19 | 2 | n     | multi-shot |
|  71 | `&EE` | `&04` |  4 | 0 | n     | multi-shot |
|  72 | `&EE` | `&A4` |  4 | 1 | Y     | multi-shot |
|  73 | `&EE` | `&50` | 16 | 2 | n     | boss / heavy |
| ... | `&FF` | — | — | — | — | terminator at slot 74 (74 active) |
