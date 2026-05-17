# Dockerfile for milo-cost-auditor MCP server
# Required by Glama.ai introspection checks (per awesome-mcp-servers PR #6481).
# Builds a minimal Python 3.13 image, installs the package, exposes the MCP
# server on stdio (the canonical MCP transport).
#
# Build:  docker build -t milo-cost-auditor .
# Run:    docker run -i milo-cost-auditor   # stdio mode — feed JSON-RPC via stdin
# Test:   echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"docker-smoke","version":"0.0.0"}}}' | docker run -i milo-cost-auditor

FROM python:3.13-slim

LABEL org.opencontainers.image.title="milo-cost-auditor"
LABEL org.opencontainers.image.description="MCP server that audits LLM cost waste, suggests cheaper routing, generates LiteLLM configs."
LABEL org.opencontainers.image.source="https://github.com/miloantaeus/milo-cost-auditor-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Milo Antaeus <miloantaeus@gmail.com>"

# Don't write .pyc files; keep image small + reproducible
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only the deps first (cache layer) — copy pyproject only
COPY pyproject.toml ./

# Install the package + its runtime deps
COPY src /app/src
RUN pip install --no-cache-dir .

# Optional: bundle the dev fixture so users can run the demo audit inside the container
COPY launch/fixtures /app/fixtures

# MCP servers communicate over stdio. The console-script entry exposes `mcp-cost-auditor`.
# Glama's introspection should be able to send an `initialize` JSON-RPC frame and get
# back our serverInfo (name=milo-cost-auditor, version=0.1.x) + tool list.
CMD ["python", "-m", "milo_cost_auditor"]
