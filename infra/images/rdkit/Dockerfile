# RDKit engine image — linux/amd64 (rdkit ships no macOS x86_64 wheel;
# docs/dependencies.lock.md platform matrix). Version is pinned to the
# lockfile's declared version — no floating latest.
FROM python:3.12-slim
RUN pip install --no-cache-dir "rdkit==2026.3.6"
ENTRYPOINT ["python"]
