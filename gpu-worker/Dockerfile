# Rust GPU worker — parakeet-rs (Parakeet TDT + Sortformer diarization)
# No Python, no PyTorch, no NeMo. Just Rust + ONNX Runtime + CUDA.

# ── Stage 1: Build ──
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl build-essential pkg-config libssl-dev cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build
COPY Cargo.toml ./
COPY src ./src

# Build release binary — ort downloads ONNX Runtime with CUDA support
RUN cargo build --release

# Find where ort put the ONNX Runtime shared libs
RUN find /build/target/release -name 'libonnxruntime*' -type f | head -20 > /tmp/ort_libs.txt \
    && cat /tmp/ort_libs.txt

# ── Stage 2: Download models ──
FROM python:3.12-slim AS models

RUN pip install --no-cache-dir huggingface-hub

# TDT model (encoder + decoder_joint + vocab)
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('istupakov/parakeet-tdt-0.6b-v3-onnx', local_dir='/models/tdt')"

# Sortformer v2.1 diarization model
RUN python -c "\
from huggingface_hub import hf_hub_download; \
hf_hub_download('altunenes/parakeet-rs', 'diar_streaming_sortformer_4spk-v2.1.onnx', local_dir='/models/sortformer')"

# ── Stage 3: Runtime ──
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 app && useradd -u 1001 -g app -s /bin/bash -m app

# Copy binary
COPY --from=builder /build/target/release/yt-mcp-gpu-worker /usr/local/bin/yt-mcp-gpu-worker

# Copy ONNX Runtime shared libs (ort downloads them into the build tree)
# The exact path varies — copy everything matching from the release dir
COPY --from=builder /build/target/release/libonnxruntime* /usr/local/lib/
ENV LD_LIBRARY_PATH="/usr/local/lib"

# Copy models
COPY --from=models /models /models

RUN mkdir -p /tmp/worker && chown -R app:app /tmp/worker

USER app

ENV WORKER_PORT=3001 \
    MODEL_DIR=/models \
    RUST_LOG=info

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${WORKER_PORT}/worker/healthz" >/dev/null 2>&1 || exit 1

CMD ["yt-mcp-gpu-worker"]
