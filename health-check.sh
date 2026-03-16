#!/bin/bash
# health-check.sh
# Script for system health checks and service initialization verification

# Function to check if a service is running
check_service() {
    service_name=$1
    if systemctl is-active --quiet $service_name; then
        echo "$service_name is running"
    else
        echo "$service_name is not running"
    fi
}

# Check essential services
check_service "nginx"
check_service "mysql"
check_service "redis"