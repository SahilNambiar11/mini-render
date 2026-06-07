# Self-Hosted Kubernetes Deployment Platform

A self-hosted deployment platform inspired by Render and Heroku. It allows users to deploy, manage, monitor, and access containerized applications on their own cloud infrastructure.

The platform is built on AWS EC2 using Kubernetes, FastAPI, React, PostgreSQL, Redis, Nginx, and GitHub Actions.

## Live Demo

Live Demo: `http://YOUR_EC2_PUBLIC_IP`

## Overview

This project was built to understand how modern cloud platforms deploy and operate applications under the hood.

Users can:

* Deploy containerized applications
* Stop, restart, and delete deployments
* View deployment status
* Stream live application logs
* View historical logs
* Monitor health status
* Monitor CPU and memory usage
* Configure CPU and memory requests
* Configure CPU and memory limits
* Access deployed applications through generated public URLs

## Architecture

```text
                         ┌──────────────────────┐
                         │      React Frontend   │
                         │   Deployment Dashboard│
                         └───────────┬──────────┘
                                     │
                                     │ HTTP / WebSocket
                                     ▼
                         ┌──────────────────────┐
                         │     Nginx Reverse     │
                         │        Proxy          │
                         └───────────┬──────────┘
                                     │
                         ┌───────────┴───────────┐
                         │                       │
                         ▼                       ▼
              ┌──────────────────┐     ┌──────────────────┐
              │   FastAPI API     │     │  Deployed Apps   │
              │ Deployment Logic  │     │ Public App URLs  │
              └─────────┬────────┘     └──────────────────┘
                        │
          ┌─────────────┼─────────────────────┐
          │             │                     │
          ▼             ▼                     ▼
 ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
 │ PostgreSQL DB  │ │ Redis Queue  │ │ Kubernetes API   │
 │ Deployment     │ │ RQ Jobs      │ │ k3s Cluster      │
 │ Persistence    │ │ Background   │ │                  │
 └────────────────┘ │ Workers      │ └─────────┬────────┘
                    └──────────────┘           │
                                               ▼
                                  ┌────────────────────────┐
                                  │ Kubernetes Resources   │
                                  │ Deployments            │
                                  │ Services               │
                                  │ Pods                   │
                                  │ RBAC                   │
                                  │ Metrics Server         │
                                  └────────────────────────┘
```

## Tech Stack

### Frontend

* React
* Vite
* WebSockets

### Backend

* Python
* FastAPI
* SQLAlchemy
* PostgreSQL
* Redis
* RQ Workers

### Infrastructure

* AWS EC2
* Amazon Linux 2023
* Kubernetes with k3s
* Docker
* Nginx
* GitHub Actions
* Metrics Server

### Kubernetes Features

* Deployments
* Services
* Pods
* RBAC
* ServiceAccounts
* Roles
* RoleBindings
* Resource requests
* Resource limits
* Pod logs
* Metrics API

## Core Features

### Container Deployment

Users can deploy applications by providing:

* Service name
* Docker image
* Container port
* CPU request
* Memory request
* CPU limit
* Memory limit

The backend dynamically creates Kubernetes Deployment and Service resources.

### Deployment Management

Supported actions:

* Create deployment
* Stop deployment
* Restart deployment
* Delete deployment
* View deployment status
* View creation and deletion timestamps

### Public Application URLs

Each running application receives a generated public URL through the platform.

Example:

```text
http://YOUR_EC2_PUBLIC_IP/api/apps/my-service/
```

Requests are routed through the backend and Kubernetes service layer to the running application.

### Live Logs

The platform supports real-time log streaming using:

* WebSockets
* Kubernetes pod log streaming
* FastAPI WebSocket endpoints
* Nginx WebSocket proxying

Users can open a live log viewer and watch container output stream in real time.

### Historical Logs

Users can fetch recent logs from Kubernetes pods using the Kubernetes API.

### Health Monitoring

The platform tracks application health and status, including:

* Running
* Stopped
* Failed
* Healthy

### Metrics Dashboard

The dashboard displays Kubernetes resource usage for running deployments:

* CPU usage
* Memory usage
* CPU requests
* Memory requests
* CPU limits
* Memory limits

Metrics are collected through Kubernetes Metrics Server.

### Resource Limits

Users can configure Kubernetes resource requests and limits during deployment.

Example:

```text
CPU Request: 100m
Memory Request: 128Mi
CPU Limit: 500m
Memory Limit: 512Mi
```

These values are injected into generated Kubernetes deployment manifests.

### Background Workers

Redis and RQ workers support asynchronous background processing for deployment tasks and future orchestration workflows.

### CI/CD Pipeline

GitHub Actions automates production deployment.

Pipeline flow:

```text
git push
    ↓
GitHub Actions
    ↓
SSH into EC2
    ↓
Pull latest code
    ↓
Build backend Docker image
    ↓
Import image into k3s
    ↓
Apply Kubernetes manifests
    ↓
Run database migrations
    ↓
Build frontend
    ↓
Reload Nginx
```

## Kubernetes Architecture

The backend communicates directly with the Kubernetes API to manage application infrastructure.

For each deployment, the platform creates:

```text
User Request
    ↓
FastAPI Backend
    ↓
Kubernetes Deployment
    ↓
Pods
    ↓
Kubernetes Service
    ↓
Public App URL
```

The platform uses RBAC to grant the backend controlled access to:

* Deployments
* Services
* Pods
* Pod logs
* Metrics

## Major Engineering Problems Solved

### Kubernetes RBAC

Configured ServiceAccount, Role, and RoleBinding resources so the backend could securely access Kubernetes resources.

Solved permission issues such as:

```text
403 Forbidden: cannot get resource pods/log
```

### WebSocket Proxying

Configured Nginx to correctly proxy WebSocket traffic by handling:

* Upgrade headers
* Connection headers
* `/ws` routing

### Metrics Collection

Installed and configured Kubernetes Metrics Server to collect pod-level CPU and memory usage.

### Kubernetes Service Discovery

Used Kubernetes Services to provide stable internal networking between workloads.

Example:

```text
service-name.default.svc.cluster.local
```

### CI/CD Deployment

Automated deployment to EC2 using GitHub Actions, SSH, Docker image builds, k3s imports, manifest application, migrations, and Nginx reloads.

### Database Reliability

Debugged PostgreSQL startup, authentication, service discovery, and connection issues inside Kubernetes.

## What I Learned

This project covers several core infrastructure and platform engineering concepts:

* Linux server management
* SSH and EC2 operations
* Kubernetes orchestration
* Container lifecycle management
* Reverse proxying
* WebSocket networking
* RBAC and cluster permissions
* PostgreSQL persistence
* Redis-backed background jobs
* CI/CD automation
* Metrics and observability
* Resource management
* Service discovery
* Cloud deployment architecture

## Future Improvements

Potential future additions:

* Custom subdomain routing
* Kubernetes Ingress support
* HTTPS with Let's Encrypt
* User authentication
* Deployment rollbacks
* Prometheus and Grafana integration
* Multi-node Kubernetes support
* Build-from-GitHub deployment flow
* Environment variable management

## Project Status

Core platform functionality is complete.

Current supported features:

* Deploy applications
* Stop applications
* Restart applications
* Delete applications
* View deployment status
* View health
* View logs
* Stream live logs
* View CPU and memory metrics
* Configure resource requests and limits
* Access deployed apps through public URLs
* Persist deployment records
* Deploy through CI/CD
