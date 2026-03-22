#!/bin/bash

# Start script for the genetic health toolkit

echo "Starting Genetic Health Analysis Toolkit..."

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
fi

# Start with Docker Compose
echo "Starting services with Docker Compose..."
docker-compose up --build

echo "Services started!"
echo "Frontend: http://localhost:3000"
echo "Backend API: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"