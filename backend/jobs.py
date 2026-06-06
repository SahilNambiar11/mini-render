import docker

from database import SessionLocal
from models import Deployment



def deploy_container_job(deployment_id: int, image: str, container_port: int, name: str):
    db = SessionLocal()
    client = docker.from_env()

    try:
        deployment = (
            db.query(Deployment)
            .filter(Deployment.id == deployment_id)
            .first()
        )

        if not deployment:
            return

        deployment.status = "deploying"
        db.commit()

        port_key = f"{container_port}/tcp"

        container = client.containers.run(
            image,
            detach=True,
            ports={port_key: None},
            name=name
        )

        container.reload()

        deployment.container_id = container.id
        deployment.status = container.status
        db.commit()

    except Exception:
        deployment = (
            db.query(Deployment)
            .filter(Deployment.id == deployment_id)
            .first()
        )

        if deployment:
            deployment.status = "failed"
            db.commit()

        raise

    finally:
        db.close()