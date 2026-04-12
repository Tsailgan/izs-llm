#!/bin/bash

# Configuration: Target a specific component or scenario
# Usage: 
#   ./scripts/run_tests.sh                          # Run all tests
#   ./scripts/run_tests.sh rag                      # Run only RAG tests
#   ./scripts/run_tests.sh consultant               # Run only Consultant tests
#   ./scripts/run_tests.sh execution                # Run only Execution tests
#   ./scripts/run_tests.sh rejection                # Run only Rejection tests
#   ./scripts/run_tests.sh recreation               # Run code recreation tests
#   ./scripts/run_tests.sh all "L1_01"              # Run specific scenario by ID

TYPE=$1
FILTER=$2

# Map shorthand to file paths
case $TYPE in
    rag)        TARGET="tests/test_rag.py" ;;
    consultant) TARGET="tests/test_consultant.py" ;;
    execution)  TARGET="tests/test_execution.py" ;;
    rejection)  TARGET="tests/test_rejection.py" ;;
    recreation) TARGET="tests/test_recreation.py" ;;
    *)          TARGET="tests/" ;;
esac

# Handle filter if first arg was a filter instead of a type
if [[ -z "$FILTER" && "$TYPE" != "rag" && "$TYPE" != "consultant" && "$TYPE" != "execution" && "$TYPE" != "rejection" && "$TYPE" != "recreation" && "$TYPE" != "all" && -n "$TYPE" ]]; then
    TARGET="tests/"
    FILTER=$TYPE
fi

echo "Going to the project folder."
cd ~/izs-llm || exit 1

echo "Installing pytest and httpx in the container."
docker compose exec api pip install pytest httpx

echo "Starting the tests for: ${TARGET:-all} ${FILTER:+with filter: $FILTER}"

# Build the -k flag if filter exists
K_FLAG=""
if [ -n "$FILTER" ]; then
    K_FLAG="-k $FILTER"
fi

# No need for external networking setup!
docker compose exec \
  -e GROQ_API_KEY="key" \
  -e MISTRAL_API_KEY="key" \
  api pytest "$TARGET" -v -s $K_FLAG -W ignore::DeprecationWarning

echo "Finished running tests."
