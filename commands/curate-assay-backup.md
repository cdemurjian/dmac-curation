---
description: Write a dated, verified tarball of the ruling store
---

The user wants the ruling store backed up by hand. `curate-assay-review` does
this automatically on every ingest; this command exists for use outside that —
before a risky operation, or after a session that ruled a lot.

```bash
PYTHONPATH=scripts uv run --with pandas python -c "
from pathlib import Path
from assay_hygiene.store_backup import back_up
made = back_up(Path('assets/rulings'), Path('~/backups').expanduser(),
               '<YYYYMMDD-HHMM>')
print('wrote', made)
"
```

`back_up` opens the archive it just wrote and asserts the store's files are
inside before returning. An exit code describes the call; the archive describes
the backup. On 2026-08-27 a backup command exited 0 having written a 0-byte
file, and only a sanity `ls` caught it.

Backing up an absent store **refuses** rather than producing an empty archive
that reports success — that is worse than no backup, because it looks like one.

## Restoring

```bash
tar -xzf ~/backups/rulings-<stamp>.tar.gz -C assets/
```

The archive holds the store directory itself, so it restores to
`assets/rulings/` without further moving. `curate-assay-init` refuses to open a
run when the store is missing and names this command, which is what makes the
backup load-bearing rather than decorative.

## The limit, recorded rather than smoothed over

Backups live on the same machine as the store. A lost machine is a lost
curation campaign. That is the accepted cost of keeping identifiers out of a
PUBLIC repository — everything under `assets/` is gitignored because this
repository has previously carried real sample identifiers, protocol
identifiers, and bare `<YYMMDD><LAB>` batch stamps in tracked files.

If the operator wants off-machine protection, that is a decision about where
identifying data may live, and it belongs to them rather than to this command.
