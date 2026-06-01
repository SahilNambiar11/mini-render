from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database import SessionLocal
from models import Deployment
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from task_queue import deployment_queue
from jobs import deploy_container_job
from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import iterate_in_threadpool
import docker

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = docker.from_env()

class ContainerCreateRequest(BaseModel):
    image: str
    container_port: int
    name: str

@app.get("/")
def root():
    return {"message": "Mini Render Backend Running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/docker")
def docker_status():
    version = client.version()
    return {
        "status": "connected",
        "docker_version": version.get("Version")
    }

@app.post("/containers")
def create_container(request: ContainerCreateRequest):
    db = SessionLocal()

    try:
        deployment = Deployment(
            name=request.name,
            image=request.image,
            container_id=None,
            status="queued"
        )

        db.add(deployment)
        db.commit()
        db.refresh(deployment)

        deployment_queue.enqueue(
            deploy_container_job,
            deployment.id,
            request.image,
            request.container_port,
            request.name
        )

        return {
            "message": "deployment queued",
            "deployment": {
                "id": deployment.id,
                "name": deployment.name,
                "image": deployment.image,
                "container_id": deployment.container_id,
                "status": deployment.status,
                "created_at": deployment.created_at,
                "deleted_at": deployment.deleted_at
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

@app.post("/containers/nginx")
def run_nginx():
    try:
        container = client.containers.run(
            "nginx",
            detach=True,
            ports={"80/tcp": None}
        )

        container.reload()

        return {
            "id": container.id[:12],
            "name": container.name,
            "status": container.status,
            "ports": container.attrs["NetworkSettings"]["Ports"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/containers")
def list_containers():
    try:
        containers = client.containers.list(all=True)
        return [format_container(container) for container in containers]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/containers/{container_id}/stop")
def stop_container(container_id: str):
    db = SessionLocal()

    try:
        container = client.containers.get(container_id)
        full_container_id = container.id

        container.stop()
        container.reload()

        deployment = (
            db.query(Deployment)
            .filter(Deployment.container_id == full_container_id)
            .first()
        )

        if deployment:
            deployment.status = "stopped"
            db.commit()

        return {
            "message": "container stopped",
            "container": format_container(container)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.post("/containers/{container_id}/restart")
def restart_container(container_id: str):
    db = SessionLocal()

    try:
        container = client.containers.get(container_id)
        full_container_id = container.id

        container.restart()
        container.reload()

        deployment = (
            db.query(Deployment)
            .filter(Deployment.container_id == full_container_id)
            .first()
        )

        if deployment:
            deployment.status = "running"
            db.commit()

        return {
            "message": "container restarted",
            "container": format_container(container)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

@app.get("/containers/{container_id}/inspect")
def inspect_container(container_id: str):
    try:
        container = client.containers.get(container_id)
        return {
            "id": container.id[:12],
            "name": container.name,
            "status": container.status,
            "image": container.image.tags,
            "ports": container.attrs["NetworkSettings"]["Ports"],
            "created": container.attrs["Created"],
            "state": container.attrs["State"],
            "network_settings": container.attrs["NetworkSettings"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/containers/{container_id}/logs")
def get_container_logs(container_id: str):
    try:
        container = client.containers.get(container_id)
        logs = container.logs(tail=200).decode("utf-8", errors="replace")

        return {"logs": logs}

    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def format_container(container):
    return {
        "id": container.id[:12],
        "name": container.name,
        "status": container.status,
        "image": container.image.tags,
        "ports": container.attrs["NetworkSettings"]["Ports"]
    }

@app.delete("/containers/{container_id}")
def delete_container(container_id: str):
    db = SessionLocal()

    try:
        container = client.containers.get(container_id)
        full_container_id = container.id

        container.remove(force=True)

        deployment = (
            db.query(Deployment)
            .filter(Deployment.container_id == full_container_id)
            .first()
        )

        if deployment:
            deployment.status = "deleted"
            deployment.deleted_at = datetime.now(timezone.utc)
            db.commit()

        return {
            "message": "container deleted",
            "container_id": container_id[:12]
        }

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

        return [
            {
                "id": deployment.id,
                "name": deployment.name,
                "image": deployment.image,
                "container_id": deployment.container_id[:12] if deployment.container_id else None,
                "status": deployment.status,
                "created_at": deployment.created_at,
                "deleted_at": deployment.deleted_at
            }
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

        return {
            "id": deployment.id,
            "name": deployment.name,
            "image": deployment.image,
            "container_id": deployment.container_id[:12],
            "status": deployment.status,
            "created_at": deployment.created_at,
            "deleted_at": deployment.deleted_at
        }

    finally:
        db.close()

@app.websocket("/ws/containers/{container_id}/logs")
async def stream_container_logs(websocket: WebSocket, container_id: str):
    await websocket.accept()
    log_stream = None

    try:
        container = client.containers.get(container_id)
        log_stream = container.logs(stream=True, follow=True, tail=50)

        async for line in iterate_in_threadpool(log_stream):
            decoded_line = line.decode("utf-8", errors="replace")
            await websocket.send_text(decoded_line)

    except WebSocketDisconnect:
        print("Client disconnected from log stream")

    except docker.errors.NotFound:
        await websocket.send_text("Error: Container not found")
        await websocket.close()

    except Exception as e:
        await websocket.send_text(f"Error: {str(e)}")
        await websocket.close()

    finally:
        if log_stream and hasattr(log_stream, "close"):
            log_stream.close()
