# Worker isolation profiles

Declared profiles for run execution (handoff §13.3). The executor reads
these documents; each profile records which controls it can actually
enforce. A control that cannot be enforced is stated as such — the
profile is never silently downgraded, and a run requiring a missing
control is reported blocked rather than executed unprotected.

- `restricted.json` — container isolation: kernel-level network denial,
  read-only root filesystem, scratch-only writes, full process-tree
  kill. Unavailable when the pinned image is not present locally.
- `development-reduced.json` — subprocess isolation for public or
  synthetic workloads only: scrubbed environment, HOME redirected to a
  per-run scratch directory, killable process group, and POSIX rlimits
  where the platform honors them. It does NOT deny network egress and
  says so in `enforced.network_denied: false`.
