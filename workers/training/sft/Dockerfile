# Pinned SFT worker (CS-0801, §17.4). torch 2.14.1+cpu comes from the
# pytorch CPU index (same version the repo lockfile resolves; CPU-only
# wheels keep the image small and egress-free at runtime). peft 0.21.2
# + transformers 5.18.0 + accelerate 1.15.0 match uv.lock exactly.
# The base model is constructed locally — nothing is downloaded at
# run time.
FROM python:3.12-slim
COPY workers/training/sft/requirements.lock /requirements.lock
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /requirements.lock
COPY packages/engine-adapters/sft/engine_adapter_sft /opt/studio/engine_adapter_sft
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/training/__init__.py /opt/studio/workers/training/__init__.py
COPY workers/training/sft/__init__.py /opt/studio/workers/training/sft/__init__.py
COPY workers/training/sft/runner.py /opt/studio/workers/training/sft/runner.py
ENV PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CMD ["python", "-m", "workers.training.sft.runner"]
