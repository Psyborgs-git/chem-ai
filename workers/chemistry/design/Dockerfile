# Pinned molecular-design worker (CS-0903). reinvent 4.8 installs from
# the upstream git tag (it is not on PyPI); the full transitive set is
# frozen in requirements.lock. The licensed prior is fetched at build
# time only and its content hash verified — at run time the container
# has no network and never downloads anything (§16.4, U13).
FROM python:3.12-slim
# libxrender1/libxext6: rdkit Chem.Draw import chain pulls X11 libs
# even for non-drawing use (reinvent's report module imports the grid
# image helper at import time).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*
COPY workers/chemistry/design/requirements.lock /requirements.lock
RUN pip install --no-cache-dir -r /requirements.lock
RUN mkdir -p /opt/models \
    && curl -fsSL "https://zenodo.org/api/records/20701824/files/reinvent_pubchem.prior/content" \
        -o /opt/models/reinvent_pubchem.prior \
    && echo "fe8cd1678452ad292a8f93e97cb19a85959b729e17113e157180d5e69ae89ef3  /opt/models/reinvent_pubchem.prior" \
        | sha256sum -c -
COPY packages/engine-adapters/reinvent/engine_adapter_reinvent /opt/studio/engine_adapter_reinvent
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/chemistry/__init__.py /opt/studio/workers/chemistry/__init__.py
COPY workers/chemistry/design/__init__.py /opt/studio/workers/chemistry/design/__init__.py
COPY workers/chemistry/design/runner.py /opt/studio/workers/chemistry/design/runner.py
ENV PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "workers.chemistry.design.runner"]
