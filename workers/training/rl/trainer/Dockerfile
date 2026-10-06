# Pinned RL trainer worker (CS-0902, §19.4). torch 2.14.1+cpu from the
# pytorch CPU index (same version the repo lockfile resolves; CPU-only
# wheels keep the image small and egress-free at runtime); trl 1.14.1,
# peft 0.21.2, transformers 5.18.0, accelerate 1.15.0 and datasets
# 5.0.1 match uv.lock exactly. The base policy and the episode corpora
# are constructed/provisioned locally — nothing is downloaded at run
# time (HF_HUB_OFFLINE=1). The CS-0901 environment, reward service and
# the shared capability vocabulary ship in the image so grant
# resolution happens server-side inside the container.
FROM python:3.12-slim
COPY workers/training/rl/trainer/requirements.lock /requirements.lock
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /requirements.lock
COPY packages/engine-adapters/rl/engine_adapter_rl /opt/studio/engine_adapter_rl
COPY packages/policy/chem_studio_policy /opt/studio/chem_studio_policy
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/training/__init__.py /opt/studio/workers/training/__init__.py
COPY workers/training/rl/__init__.py /opt/studio/workers/training/rl/__init__.py
COPY workers/training/rl/corpus.py /opt/studio/workers/training/rl/corpus.py
COPY workers/training/rl/environment /opt/studio/workers/training/rl/environment
COPY workers/training/rl/rewards /opt/studio/workers/training/rl/rewards
COPY workers/training/rl/trainer /opt/studio/workers/training/rl/trainer
ENV PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CMD ["python", "-m", "workers.training.rl.trainer.runner"]
