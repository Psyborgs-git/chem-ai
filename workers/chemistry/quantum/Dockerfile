# Pinned quantum worker (CS-0701). xtb exists only on conda-forge, so
# the base is micromamba rather than python-slim: python 3.12 +
# xtb 6.7.1 + xtb-python 22.1, then the pip side pins QCEngine 0.51.0 /
# QCElemental 0.51.2 via requirements.lock. Psi4 is deliberately absent.
FROM mambaorg/micromamba:2-debian12-slim
USER root
RUN micromamba install -y -n base -c conda-forge \
        python=3.12 xtb=6.7.1 xtb-python=22.1 pip \
    && micromamba clean -afy
COPY workers/chemistry/quantum/requirements.lock /requirements.lock
RUN /opt/conda/bin/pip install --no-cache-dir -r /requirements.lock
COPY packages/engine-adapters/qcengine/engine_adapter_qcengine /opt/studio/engine_adapter_qcengine
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/chemistry/__init__.py /opt/studio/workers/chemistry/__init__.py
COPY workers/chemistry/quantum/__init__.py /opt/studio/workers/chemistry/quantum/__init__.py
COPY workers/chemistry/quantum/runner.py /opt/studio/workers/chemistry/quantum/runner.py
ENV PATH="/opt/conda/bin:${PATH}" \
    PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "workers.chemistry.quantum.runner"]
