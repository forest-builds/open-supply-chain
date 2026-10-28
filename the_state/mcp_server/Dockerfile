FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY . .

ENV THE_STATE_MCP_TRANSPORT=streamable-http
ENV THE_STATE_MCP_HOST=0.0.0.0
ENV THE_STATE_MCP_PORT=8765

CMD ["the-state-mcp"]
