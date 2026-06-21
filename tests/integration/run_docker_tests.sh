#!/bin/bash
"""Run integration tests using Docker directly."""

set -e

echo "Building Docker image..."
docker build -t pyesb-app -f ../Dockerfile ..

echo "Starting container..."
docker run -d --name pyesb-test-container -p 9090:9090 pyesb-app

echo "Waiting for service to be ready..."
sleep 15

echo "Running tests against running container..."
python -m pytest integration/test_docker_integration.py -v --tb=short

echo "Stopping and removing container..."
docker stop pyesb-test-container
docker rm pyesb-test-container

echo "Integration tests completed!"
