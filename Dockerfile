# syntax=docker/dockerfile:1
# Install the inline script dependencies into the image so runtime commands
# do not need uv's writable cache. Git is needed for worktree operations.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

LABEL org.opencontainers.image.title="loopq" \
      org.opencontainers.image.description="Coordinate coding agents in separate Git worktrees" \
      org.opencontainers.image.source="https://github.com/alvagante/loopq" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY loopq.py /usr/local/bin/loopq

RUN chmod +x /usr/local/bin/loopq \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && uv pip install --system pyyaml==6.0.3 rich==15.0.0 \
    && python /usr/local/bin/loopq --help >/dev/null \
    && git --version

ENV LOOPQ_HOME=/data

VOLUME /data

WORKDIR /work

ENTRYPOINT ["python", "/usr/local/bin/loopq"]
CMD ["doctor"]
