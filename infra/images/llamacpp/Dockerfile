# Local inference image — llama.cpp server + a pinned, licensed model.
# The model's sha256 is verified at build; the tag carries the pin.
# Model: google/gemma-2-2b-it (gemma license), via the local ollama
# store — no download at build or runtime.
FROM ghcr.io/ggml-org/llama.cpp:server
ARG MODEL_SHA256=c1864a5eb19305c40519da12cc543519e48a0697ecd30e15d5ac228644957d12
COPY model.gguf /models/model.gguf
RUN echo "$MODEL_SHA256  /models/model.gguf" | sha256sum -c -
