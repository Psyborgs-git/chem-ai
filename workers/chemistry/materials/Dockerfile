# Pinned materials/thermodynamics worker (CS-0702). Everything the
# method needs ships as pip wheels, so the base is python-slim; the
# lock file fixes thermo 0.6.1 and its full transitive set.
FROM python:3.12-slim
COPY workers/chemistry/materials/requirements.lock /requirements.lock
RUN pip install --no-cache-dir -r /requirements.lock
COPY packages/engine-adapters/materials/engine_adapter_materials /opt/studio/engine_adapter_materials
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/chemistry/__init__.py /opt/studio/workers/chemistry/__init__.py
COPY workers/chemistry/materials/__init__.py /opt/studio/workers/chemistry/materials/__init__.py
COPY workers/chemistry/materials/runner.py /opt/studio/workers/chemistry/materials/runner.py
ENV PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "workers.chemistry.materials.runner"]
