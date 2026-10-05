FROM python:3.12.14-slim
ENV OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
COPY workers/optimization/requirements.lock /requirements.lock
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /requirements.lock
COPY packages/engine-adapters/baybe/engine_adapter_baybe /opt/studio/engine_adapter_baybe
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/optimization/runner.py /opt/studio/workers/optimization/runner.py
ENV PYTHONPATH=/opt/studio
CMD ["python", "-m", "workers.optimization.runner"]
