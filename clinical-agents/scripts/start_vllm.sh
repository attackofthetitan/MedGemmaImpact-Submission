#!/bin/bash

set -e

ROUTER_MODEL_PATH="${ROUTER_MODEL_PATH:-./routergemma}"
MEDICAL_MODEL_PATH="${MEDICAL_MODEL_PATH:-./medgemma-fp8}"
EMBEDDING_MODEL_PATH="${EMBEDDING_MODEL_PATH:-./embedgemma}"

ROUTER_PORT="${ROUTER_PORT:-8001}"
MEDICAL_PORT="${MEDICAL_PORT:-8002}"
EMBEDDING_PORT="${EMBEDDING_PORT:-8003}"

check_port() {
  if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Port $1 is already in use"
    return 1
  fi
  return 0
}

# # Start Router Model
# if check_port $ROUTER_PORT; then
#     echo "Starting Router Model (FunctionGemma) on port $ROUTER_PORT..."
#     vllm serve "$ROUTER_MODEL_PATH" \
#         --port $ROUTER_PORT \
#         --served-model-name router \
#         --tensor-parallel-size 1 \
#         --host 0.0.0.0 \
#         --max-model-len 4096 \
#         --gpu-memory-utilization 0.2 &
#     ROUTER_PID=$!
#     echo "Router PID: $ROUTER_PID"
#     sleep 30
# fi

TOOL_CHAT_TEMPLATE="${TOOL_CHAT_TEMPLATE:-$(dirname "$0")/tool_chat_template.jinja}"

# Start Medical Model
if check_port $MEDICAL_PORT; then
  echo "Starting Medical Model (MedGemma) on port $MEDICAL_PORT..."
  vllm serve "$MEDICAL_MODEL_PATH" \
    --port $MEDICAL_PORT \
    --served-model-name medgemma \
    --tensor-parallel-size 2 \
    --host 0.0.0.0 \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.8 \
    --enable-auto-tool-choice \
    --tool-call-parser pythonic \
    --chat-template "$TOOL_CHAT_TEMPLATE" &
  MEDICAL_PID=$!
  echo "Medical PID: $MEDICAL_PID"
  sleep 30
fi

# Start Embedding Model
if [ -d "$EMBEDDING_MODEL_PATH" ] && check_port $EMBEDDING_PORT; then
  echo "Starting Embedding Model (embedgemma) on port $EMBEDDING_PORT..."
  vllm serve "$EMBEDDING_MODEL_PATH" \
    --port $EMBEDDING_PORT \
    --served-model-name embedgemma \
    --tensor-parallel-size 1 \
    --host 0.0.0.0 \
    --max-model-len 2048 \
    --gpu-memory-utilization 0.1 &
  EMBEDDING_PID=$!
  echo "Embedding PID: $EMBEDDING_PID"
else
  echo "Embedding model not found or port in use"
fi

echo ""
echo "Servers:"
echo "  Router:    http://localhost:$ROUTER_PORT/v1"
echo "  Medical:   http://localhost:$MEDICAL_PORT/v1"
echo "  Embedding: http://localhost:$EMBEDDING_PORT/v1"
echo ""
echo "Health checks:"
echo "  curl http://localhost:$ROUTER_PORT/health"
echo "  curl http://localhost:$MEDICAL_PORT/health"
echo "  curl http://localhost:$EMBEDDING_PORT/health"
echo ""

wait
