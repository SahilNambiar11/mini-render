from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import SessionLocal
from models import Deployment
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from task_queue import deployment_queue
from jobs import (
    build_deployment,
    build_service,
    delete_if_exists,
    deploy_container_job,
    DEFAULT_CPU_LIMIT,
    DEFAULT_CPU_REQUEST,
    DEFAULT_MEMORY_LIMIT,
    DEFAULT_MEMORY_REQUEST,
    get_namespace,
    get_kubernetes_deployment_status,
    load_kubernetes_config,
    make_kubernetes_name,
)
from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import iterate_in_threadpool
from kubernetes import client as k8s_client
from kubernetes.client.exceptions import ApiException
import requests
import logging
import ast
import re

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_kubernetes_clients():
    load_kubernetes_config()
    return get_namespace(), k8s_client.AppsV1Api(), k8s_client.CoreV1Api()


def find_deployment_by_k8s_name(db, k8s_name: str):
    return (
        db.query(Deployment)
        .filter(Deployment.container_id == k8s_name)
        .first()
    )


def refresh_deployment_status(db, deployment):
    if not deployment.container_id:
        return deployment.status

    if (deployment.status or "").lower() == "deleted":
        return deployment.status

    try:
        refreshed_status = get_kubernetes_deployment_status(
            deployment.container_id
        )
    except Exception:
        logger.exception(
            "Failed to refresh Kubernetes status for deployment %s",
            deployment.id,
        )
        return deployment.status

    if deployment.status != refreshed_status:
        logger.info(
            "Refreshed deployment %s status from %s to %s",
            deployment.id,
            deployment.status,
            refreshed_status,
        )
        deployment.status = refreshed_status
        db.commit()

    return deployment.status


def get_deployment_status(k8s_deployment):
    try:
        return get_kubernetes_deployment_status(k8s_deployment.metadata.name)
    except Exception:
        logger.exception(
            "Failed to get pod-aware status for Kubernetes deployment %s",
            k8s_deployment.metadata.name,
        )

    desired = k8s_deployment.spec.replicas or 0
    ready = k8s_deployment.status.ready_replicas or 0

    if desired == 0:
        return "stopped"
    if ready >= desired:
        return "running"

    return "deploying"


def format_kubernetes_deployment(k8s_deployment, service=None):
    return {
        "id": k8s_deployment.metadata.name,
        "name": k8s_deployment.metadata.name,
        "status": get_deployment_status(k8s_deployment),
        "image": [
            container.image
            for container in k8s_deployment.spec.template.spec.containers
        ],
        "ports": [
            {
                "port": port.port,
                "target_port": port.target_port,
                "type": service.spec.type if service else None,
            }
            for port in service.spec.ports
        ] if service else [],
    }


def get_first_pod_for_deployment(core_api, namespace: str, name: str):
    pods = core_api.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"app={name}",
    )

    if not pods.items:
        raise HTTPException(status_code=404, detail="Pod not found")

    return pods.items[0]


def iter_log_lines(log_stream):
    for chunk in log_stream:
        text = normalize_log_text(chunk)

        if not text:
            continue

        for line in text.splitlines(True):
            if line:
                yield line


def normalize_log_text(value):
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if isinstance(value, str):
        stripped = value.strip()

        if stripped.startswith(("b'", 'b"')):
            try:
                parsed = ast.literal_eval(stripped)

                if isinstance(parsed, bytes):
                    return parsed.decode("utf-8", errors="replace")
            except (SyntaxError, ValueError):
                pass

        return value

    return str(value)


class ContainerCreateRequest(BaseModel):
    image: str
    container_port: int
    name: str
    cpu_request: str = DEFAULT_CPU_REQUEST
    memory_request: str = DEFAULT_MEMORY_REQUEST
    cpu_limit: str = DEFAULT_CPU_LIMIT
    memory_limit: str = DEFAULT_MEMORY_LIMIT


def validate_resource_quantity(value: str, field_name: str, pattern: str):
    if not value or not value.strip():
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} cannot be empty",
        )

    if not re.fullmatch(pattern, value.strip()):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} has an invalid Kubernetes quantity",
        )

    return value.strip()


def validate_resource_request(request: ContainerCreateRequest):
    cpu_pattern = r"([0-9]+m|[0-9]+(\.[0-9]+)?)"
    memory_pattern = r"[0-9]+(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K)?"

    request.cpu_request = validate_resource_quantity(
        request.cpu_request,
        "cpu_request",
        cpu_pattern,
    )
    request.memory_request = validate_resource_quantity(
        request.memory_request,
        "memory_request",
        memory_pattern,
    )
    request.cpu_limit = validate_resource_quantity(
        request.cpu_limit,
        "cpu_limit",
        cpu_pattern,
    )
    request.memory_limit = validate_resource_quantity(
        request.memory_limit,
        "memory_limit",
        memory_pattern,
    )


def format_deployment_record(deployment):
    return {
        "id": deployment.id,
        "name": deployment.name,
        "image": deployment.image,
        "container_id": deployment.container_id,
        "status": deployment.status,
        "cpu_request": deployment.cpu_request,
        "memory_request": deployment.memory_request,
        "cpu_limit": deployment.cpu_limit,
        "memory_limit": deployment.memory_limit,
        "created_at": deployment.created_at,
        "deleted_at": deployment.deleted_at,
    }


def get_deployment_resource_settings(db, k8s_name: str):
    deployment = find_deployment_by_k8s_name(db, k8s_name)

    return {
        "cpu_request": deployment.cpu_request if deployment else DEFAULT_CPU_REQUEST,
        "cpu_limit": deployment.cpu_limit if deployment else DEFAULT_CPU_LIMIT,
        "memory_request": (
            deployment.memory_request if deployment else DEFAULT_MEMORY_REQUEST
        ),
        "memory_limit": deployment.memory_limit if deployment else DEFAULT_MEMORY_LIMIT,
    }

@app.get("/")
def root():
    return {"message": "Mini Render Backend Running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/docker")
def docker_status():
    _, apps_api, _ = get_kubernetes_clients()
    version = apps_api.get_api_resources()
    return {
        "status": "connected",
        "runtime": "kubernetes",
        "api_group": version.group_version,
    }

@app.post("/containers")
def create_container(request: ContainerCreateRequest):
    db = SessionLocal()

    try:
        validate_resource_request(request)

        deployment = Deployment(
            name=request.name,
            image=request.image,
            container_id=None,
            status="queued",
            cpu_request=request.cpu_request,
            memory_request=request.memory_request,
            cpu_limit=request.cpu_limit,
            memory_limit=request.memory_limit,
        )

        db.add(deployment)
        db.commit()
        db.refresh(deployment)

        deployment_queue.enqueue(
            deploy_container_job,
            deployment.id,
            request.image,
            request.container_port,
            request.name,
            request.cpu_request,
            request.memory_request,
            request.cpu_limit,
            request.memory_limit,
        )

        return {
            "message": "deployment queued",
            "deployment": format_deployment_record(deployment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

@app.post("/containers/nginx")
def run_nginx():
    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        name = make_kubernetes_name("nginx", "nginx")
        container_port = 80

        delete_if_exists(
            apps_api.delete_namespaced_deployment,
            apps_api.read_namespaced_deployment,
            name,
            namespace,
        )
        delete_if_exists(
            core_api.delete_namespaced_service,
            core_api.read_namespaced_service,
            name,
            namespace,
        )

        k8s_deployment = apps_api.create_namespaced_deployment(
            namespace=namespace,
            body=build_deployment(name, "nginx", container_port),
        )
        service = core_api.create_namespaced_service(
            namespace=namespace,
            body=build_service(name, container_port),
        )

        return {
            "id": k8s_deployment.metadata.name,
            "name": k8s_deployment.metadata.name,
            "status": get_deployment_status(k8s_deployment),
            "ports": [
                {
                    "port": port.port,
                    "target_port": port.target_port,
                    "type": service.spec.type,
                }
                for port in service.spec.ports
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/containers")
def list_containers():
    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        deployments = apps_api.list_namespaced_deployment(namespace=namespace)
        services = {
            service.metadata.name: service
            for service in core_api.list_namespaced_service(namespace=namespace).items
        }

        return [
            format_kubernetes_deployment(
                deployment,
                services.get(deployment.metadata.name),
            )
            for deployment in deployments.items
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/containers/{container_id}/stop")
def stop_container(container_id: str):
    db = SessionLocal()

    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        apps_api.patch_namespaced_deployment_scale(
            name=container_id,
            namespace=namespace,
            body={"spec": {"replicas": 0}},
        )

        deployment = find_deployment_by_k8s_name(db, container_id)

        if deployment:
            deployment.status = "stopped"
            db.commit()

        k8s_deployment = apps_api.read_namespaced_deployment(
            name=container_id,
            namespace=namespace,
        )
        service = core_api.read_namespaced_service(
            name=container_id,
            namespace=namespace,
        )

        return {
            "message": "container stopped",
            "container": format_kubernetes_deployment(k8s_deployment, service)
        }

    except ApiException as e:
        db.rollback()
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.post("/containers/{container_id}/restart")
def restart_container(container_id: str):
    db = SessionLocal()

    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        restarted_at = datetime.now(timezone.utc).isoformat()

        apps_api.patch_namespaced_deployment_scale(
            name=container_id,
            namespace=namespace,
            body={"spec": {"replicas": 1}},
        )
        k8s_deployment = apps_api.patch_namespaced_deployment(
            name=container_id,
            namespace=namespace,
            body={
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "mini-render/restarted-at": restarted_at
                            }
                        }
                    }
                }
            },
        )

        deployment = find_deployment_by_k8s_name(db, container_id)

        if deployment:
            deployment.status = "pending"
            db.commit()

        service = core_api.read_namespaced_service(
            name=container_id,
            namespace=namespace,
        )

        return {
            "message": "container restarted",
            "container": format_kubernetes_deployment(k8s_deployment, service)
        }

    except ApiException as e:
        db.rollback()
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

@app.get("/containers/{container_id}/inspect")
def inspect_container(container_id: str):
    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        k8s_deployment = apps_api.read_namespaced_deployment(
            name=container_id,
            namespace=namespace,
        )
        service = core_api.read_namespaced_service(
            name=container_id,
            namespace=namespace,
        )
        return {
            "id": k8s_deployment.metadata.name,
            "name": k8s_deployment.metadata.name,
            "status": get_deployment_status(k8s_deployment),
            "image": [
                container.image
                for container in k8s_deployment.spec.template.spec.containers
            ],
            "ports": [
                {
                    "port": port.port,
                    "target_port": port.target_port,
                    "type": service.spec.type,
                }
                for port in service.spec.ports
            ],
            "created": k8s_deployment.metadata.creation_timestamp,
            "state": k8s_deployment.status.to_dict(),
            "network_settings": service.spec.to_dict(),
        }

    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/containers/{container_id}/logs")
def get_container_logs(container_id: str):
    try:
        namespace, _, core_api = get_kubernetes_clients()
        pod = get_first_pod_for_deployment(core_api, namespace, container_id)
        logs = core_api.read_namespaced_pod_log(
            name=pod.metadata.name,
            namespace=namespace,
            tail_lines=200,
        )

        return {"logs": normalize_log_text(logs)}

    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Pod not found")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/containers/{container_id}")
def delete_container(container_id: str):
    db = SessionLocal()

    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        delete_if_exists(
            apps_api.delete_namespaced_deployment,
            apps_api.read_namespaced_deployment,
            container_id,
            namespace,
        )
        delete_if_exists(
            core_api.delete_namespaced_service,
            core_api.read_namespaced_service,
            container_id,
            namespace,
        )

        deployment = find_deployment_by_k8s_name(db, container_id)

        if deployment:
            deployment.status = "deleted"
            deployment.deleted_at = datetime.now(timezone.utc)
            db.commit()

        return {
            "message": "container deleted",
            "container_id": container_id
        }

    except ApiException as e:
        db.rollback()
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/deployments")
def list_deployments():
    db = SessionLocal()

    try:
        deployments = db.query(Deployment).all()

        for deployment in deployments:
            refresh_deployment_status(db, deployment)

        return [
            format_deployment_record(deployment)
            for deployment in deployments
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

@app.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: int):
    db = SessionLocal()

    try:
        deployment = (
            db.query(Deployment)
            .filter(Deployment.id == deployment_id)
            .first()
        )

        if not deployment:
            raise HTTPException(status_code=404, detail="Deployment not found")

        refresh_deployment_status(db, deployment)

        return format_deployment_record(deployment)

    finally:
        db.close()

@app.websocket("/ws/containers/{container_id}/logs")
async def stream_container_logs(websocket: WebSocket, container_id: str):
    await websocket.accept()
    log_stream = None

    try:
        namespace, _, core_api = get_kubernetes_clients()
        pod = get_first_pod_for_deployment(core_api, namespace, container_id)
        log_stream = core_api.read_namespaced_pod_log(
            name=pod.metadata.name,
            namespace=namespace,
            follow=True,
            tail_lines=10,
            _preload_content=False,
        )

        async for line in iterate_in_threadpool(iter_log_lines(log_stream)):
            await websocket.send_text(line)

    except WebSocketDisconnect:
        print("Client disconnected from log stream")

    except ApiException as e:
        await websocket.send_text(f"Error: {str(e)}")
        await websocket.close()

    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")
        await websocket.close()

    finally:
        if log_stream and hasattr(log_stream, "close"):
            log_stream.close()

@app.get("/containers/{container_id}/metrics")
def get_container_metrics(container_id: str):
    db = SessionLocal()

    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        k8s_deployment = apps_api.read_namespaced_deployment(
            name=container_id,
            namespace=namespace,
        )
        pod = get_first_pod_for_deployment(core_api, namespace, container_id)
        resource_settings = get_deployment_resource_settings(db, container_id)
        response = {
            "container_id": k8s_deployment.metadata.name,
            "name": k8s_deployment.metadata.name,
            "status": get_deployment_status(k8s_deployment),
            "cpu_usage": "Unavailable",
            "memory_usage": "Unavailable",
            **resource_settings,
        }

        try:
            # Metrics Server exposes pod usage through the aggregated
            # metrics.k8s.io API, which is not part of CoreV1Api. The
            # Kubernetes client reads it through CustomObjectsApi.
            metrics_api = k8s_client.CustomObjectsApi()
            pod_metrics = metrics_api.get_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
                name=pod.metadata.name,
            )
            containers = pod_metrics.get("containers", [])

            if containers:
                usage = containers[0].get("usage", {})
                response["cpu_usage"] = usage.get("cpu", "Unavailable")
                response["memory_usage"] = usage.get("memory", "Unavailable")

        except ApiException:
            logger.exception(
                "Metrics API unavailable for pod %s",
                pod.metadata.name,
            )

        return response

    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

@app.get("/containers/{container_id}/health")
def get_container_health(container_id: str):
    try:
        namespace, apps_api, core_api = get_kubernetes_clients()
        k8s_deployment = apps_api.read_namespaced_deployment(
            name=container_id,
            namespace=namespace,
        )
        service = core_api.read_namespaced_service(
            name=container_id,
            namespace=namespace,
        )
        status = get_deployment_status(k8s_deployment)

        if status != "running":
            return {
                "container_id": k8s_deployment.metadata.name,
                "status": status,
                "health": "unhealthy",
                "reason": "Deployment does not have ready replicas",
            }

        if not service.spec.ports:
            return {
                "container_id": k8s_deployment.metadata.name,
                "status": status,
                "health": "unhealthy",
                "reason": "No service port found",
            }

        service_port = service.spec.ports[0]
        checked_url = (
            f"http://{service.metadata.name}.{namespace}.svc.cluster.local:"
            f"{service_port.port}"
        )

        try:
            response = requests.get(checked_url, timeout=3)
            is_healthy = 200 <= response.status_code < 400

            return {
                "container_id": k8s_deployment.metadata.name,
                "status": status,
                "health": "healthy" if is_healthy else "unhealthy",
                "checked_url": checked_url,
                "container_port": str(service_port.target_port),
                "host_port": str(service_port.port),
                "status_code": response.status_code,
            }

        except requests.RequestException as e:
            return {
                "container_id": k8s_deployment.metadata.name,
                "status": status,
                "health": "unhealthy",
                "checked_url": checked_url,
                "container_port": str(service_port.target_port),
                "host_port": str(service_port.port),
                "reason": str(e),
            }

    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="Deployment not found")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
