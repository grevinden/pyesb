#!/bin/bash
"""Run integration tests using Docker Compose."""

set -e

echo "Building and starting services..."
docker-compose up -d --build

echo "Waiting for services to be ready..."
sleep 10

echo "Running integration tests..."
docker-compose run tests

echo "Stopping services..."
docker-compose down

echo "Integration tests completed!"
