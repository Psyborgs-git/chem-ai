FROM python:3.12.14-slim
ENV OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends libxrender1 libxext6 libexpat1 \
 && rm -rf /var/lib/apt/lists/*
COPY workers/optimization/property_models/chemprop/requirements.lock /requirements.lock
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /requirements.lock
COPY packages/engine-adapters/chemprop/engine_adapter_chemprop /opt/studio/engine_adapter_chemprop
COPY workers/__init__.py /opt/studio/workers/__init__.py
# Intermediate packages resolve as namespace packages — the heavy
# property_models package init (which imports studio modules) is
# deliberately absent from the worker image.
COPY workers/optimization/property_models/chemprop/runner.py /opt/studio/workers/optimization/property_models/chemprop/runner.py
ENV PYTHONPATH=/opt/studio
CMD ["python", "-m", "workers.optimization.property_models.chemprop.runner"]
