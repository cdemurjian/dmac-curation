---
description: Report which assay-hygiene run is open and where it has got to
---

The user wants to know where this campaign stands. This command writes nothing.

```bash
PYTHONPATH=scripts uv run python -c "
from pathlib import Path
from assay_hygiene.runstate import read
state = read(Path('assets'))
if not state:
    print('no run has been opened')
else:
    print(f\"run {state['run']}  open={state['open']}  step={state['step']}\")
    print(f\"  extract   {state['extract_sha']}\")
    print(f\"  carried   {state['carried_pairs']} pairs from run {state['carried_from_run']}\")
    w = state['write']
    print(f\"  write     chunks_done={w['chunks_done']} \"
          f\"rollback={w['rollback_id']} backup_verified={w['backup_verified']}\")
"
```

Also report the ruling store, since it is the thing that outlives runs:

```bash
PYTHONPATH=scripts uv run --with pandas python -c "
from collections import Counter
from pathlib import Path
from assay_hygiene.rulings import load
store = load(Path('assets/rulings'))
print(f'{len(store):,} rulings in the store')
for verdict, n in sorted(Counter(r.verdict for r in store.values()).items()):
    print(f'  {verdict:12} {n:>5,}')
"
```

And the newest backup, because a store with no recent backup is one machine
away from being lost:

```bash
ls -lt ~/backups/rulings-*.tar.gz 2>/dev/null | head -3 || echo "NO BACKUPS"
```

If a run reports `open=True` but nobody is working it, the previous session did
not close it. `runstate.close` releases it; check nothing is mid-write first,
because the lock is what stops two write phases from overwriting each other's
rows.
