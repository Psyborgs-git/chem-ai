# Pinned retrosynthesis worker (CS-0903). aizynthfinder 4.4.1 installs
# from PyPI; the full transitive set is frozen in requirements.lock.
# The licensed USPTO policy/template files and the ZINC stock list are
# fetched at build time only and their content hashes verified — at
# run time the container has no network and never downloads anything
# (§16.4, U13).
FROM python:3.12-slim
# libxrender1/libxext6: rdkit Chem.Draw import chain pulls X11 libs
# even for non-drawing use (rdchiral/aizynthfinder import them).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*
COPY workers/chemistry/synthesis/requirements.lock /requirements.lock
RUN pip install --no-cache-dir -r /requirements.lock
RUN mkdir -p /opt/models \
    && curl -fsSL "https://zenodo.org/api/records/7797465/files/uspto_model.onnx/content" \
        -o /opt/models/uspto_model.onnx \
    && curl -fsSL "https://zenodo.org/api/records/7341155/files/uspto_unique_templates.csv.gz/content" \
        -o /opt/models/uspto_unique_templates.csv.gz \
    && curl -fsSL "https://zenodo.org/api/records/7797465/files/uspto_filter_model.onnx/content" \
        -o /opt/models/uspto_filter_model.onnx \
    && curl -fsSL "https://ndownloader.figshare.com/files/23086469" \
        -o /opt/models/zinc_stock.hdf5 \
    && printf '%s\n' \
        "bd0a3cb74cd7068de474c8fb789a00a66bc42c75636d66510ccac585ebe928f8  /opt/models/uspto_model.onnx" \
        "a4f1945e90cfa195538320833d68aed38f14e2fcc2f8afb5d958bc920edcafbe  /opt/models/uspto_unique_templates.csv.gz" \
        "ad29aa32bdfcbe37065045546493806cf04899c55386c438905d83fb14bb6320  /opt/models/uspto_filter_model.onnx" \
        "99d39a6f807c3e815487500bafc2b4a9dc66a31af189e3b1776874fb0d4a188d  /opt/models/zinc_stock.hdf5" \
        | sha256sum -c -
COPY packages/engine-adapters/aizynthfinder/engine_adapter_aizynthfinder /opt/studio/engine_adapter_aizynthfinder
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/chemistry/__init__.py /opt/studio/workers/chemistry/__init__.py
COPY workers/chemistry/synthesis/__init__.py /opt/studio/workers/chemistry/synthesis/__init__.py
COPY workers/chemistry/synthesis/runner.py /opt/studio/workers/chemistry/synthesis/runner.py
ENV PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "workers.chemistry.synthesis.runner"]
