# Pinned model-load validator (CS-0802, §17.5). Same dependency posture
# as the SFT trainer image (torch 2.14.1+cpu, peft 0.21.2, transformers
# 5.18.0, accelerate 1.15.0, safetensors 0.8.0 — matching uv.lock) so
# adapter weights load identically to how they were trained. The base
# model is reconstructed locally from (architecture, init_seed) —
# nothing is downloaded at run time; HF offline flags are belt and
# suspenders. Runs via the container pattern (--network none,
# read-only, bounded).
FROM python:3.12-slim
COPY workers/inference/model_loading/requirements.lock /requirements.lock
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r /requirements.lock
COPY packages/engine-adapters/sft/engine_adapter_sft /opt/studio/engine_adapter_sft
COPY workers/__init__.py /opt/studio/workers/__init__.py
COPY workers/inference/__init__.py /opt/studio/workers/inference/__init__.py
COPY workers/inference/runtime.py /opt/studio/workers/inference/runtime.py
COPY workers/inference/model_loading /opt/studio/workers/inference/model_loading
ENV PYTHONPATH=/opt/studio \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CMD ["python", "-m", "workers.inference.model_loading.runner"]
