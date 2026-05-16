# Stage 1 spawn schedule

Walked by `spawn_check_step` (CODE `&208A`) each time the
scroll counter advances. Both `lev_spawn_col` and
`lev_spawn_attr` are walked together until `&FF`.

| Idx | Col | Attr | Type | Y-row | V-flip | Notes |
|----:|----:|-----:|-----:|------:|:------:|-------|
|   0 | `&EB` | `&01` |  1 | 0 | n     |  |
|   1 | `&EB` | `&C1` |  1 | 2 | Y     |  |
|   2 | `&EC` | `&04` |  4 | 0 | n     | multi-shot |
|   3 | `&EC` | `&C4` |  4 | 2 | Y     | multi-shot |
|   4 | `&ED` | `&86` |  6 | 0 | Y     | CODE2 spawn_enemy_missile |
|   5 | `&ED` | `&28` |  8 | 1 | n     | high-HP variant |
|   6 | `&ED` | `&46` |  6 | 2 | n     | CODE2 spawn_enemy_missile |
|   7 | `&EE` | `&25` |  5 | 1 | n     |  |
| ... | `&FF` | — | — | — | — | terminator at slot 8 (8 active) |
