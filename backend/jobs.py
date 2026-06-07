import os
import re
import time
import logging

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from database import SessionLocal
from models import Deployment

logger = logging.getLogger(__name__)


def load_kubernetes_config():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def get_namespace():
    namespace_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

    if os.path.exists(namespace_path):
        with open(namespace_path, "r", encoding="utf-8") as namespace_file:
            return namespace_file.read().strip()

    return "default"


def make_kubernetes_name(name: str, fallback: str):
    safe_name = re.sub(r"[^a-z0-9-]+", "-", name.lower())
    safe_name = safe_name.strip("-")
    safe_name = re.sub(r"-+", "-", safe_name)

    if not safe_name:
        safe_name = fallback

    return safe_name[:63].strip("-") or fallback


def wait_for_resource_delete(read_resource, name: str, namespace: str):
    for _ in range(30):
        try:
            read_resource(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status == 404:
                return
            raise

        time.sleep(1)

    raise TimeoutError(f"Timed out waiting for {name} to be deleted")


def delete_if_exists(delete_resource, read_resource, name: str, namespace: str):
    try:
        delete_resource(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status != 404:
            raise

    wait_for_resource_delete(read_resource, name, namespace)


def build_deployment(name: str, image: str, container_port: int):
    labels = {"app": name}

    return client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name, labels=labels),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels=labels),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name=name,
                            image=image,
                            ports=[
                                client.V1ContainerPort(
                                    container_port=container_port
                                )
                            ],
                        )
                    ]
                ),
            ),
        ),
    )


def build_service(name: str, container_port: int):
    return client.V1Service(
        metadata=client.V1ObjectMeta(name=name, labels={"app": name}),
        spec=client.V1ServiceSpec(
            type="ClusterIP",
            selector={"app": name},
            ports=[
                client.V1ServicePort(
                    port=container_port,
                    target_port=container_port,
                )
            ],
        ),
    )


def get_kubernetes_deployment_status(k8s_name: str) -> str:
    load_kubernetes_config()
    namespace = get_namespace()
    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()

    try:
        k8s_deployment = apps_api.read_namespaced_deployment(
            name=k8s_name,
            namespace=namespace,
        )
    except ApiException as exc:
        if exc.status == 404:
            return "deleted"
        raise

    desired_replicas = k8s_deployment.spec.replicas or 0
    if desired_replicas == 0:
        return "stopped"

    pods = core_api.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"app={k8s_name}",
    )

    if not pods.items:
        return "pending"

    for pod in pods.items:
        phase = (pod.status.phase or "unknown").lower()

        if phase == "failed":
            return "failed"

        for container_status in pod.status.container_statuses or []:
            waiting = (
                container_status.state.waiting
                if container_status.state
                else None
            )

            if waiting and waiting.reason in {
                "ImagePullBackOff",
                "ErrImagePull",
                "CrashLoopBackOff",
            }:
                return "failed"

            if phase == "running" and container_status.ready:
                return "running"

        if phase == "pending":
            return "pending"

    return (pods.items[0].status.phase or "unknown").lower()


def deploy_container_job(deployment_id: int, image: str, container_port: int, name: str):
    db = SessionLocal()

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
        logger.info("Deployment %s marked deploying", deployment_id)

        load_kubernetes_config()
        namespace = get_namespace()
        k8s_name = make_kubernetes_name(name, f"deployment-{deployment_id}")
        apps_api = client.AppsV1Api()
        core_api = client.CoreV1Api()
        logger.info(
            "Creating Kubernetes resources for deployment %s as %s",
            deployment_id,
            k8s_name,
        )

        delete_if_exists(
            apps_api.delete_namespaced_deployment,
            apps_api.read_namespaced_deployment,
            k8s_name,
            namespace,
        )
        delete_if_exists(
            core_api.delete_namespaced_service,
            core_api.read_namespaced_service,
            k8s_name,
            namespace,
        )

        apps_api.create_namespaced_deployment(
            namespace=namespace,
            body=build_deployment(k8s_name, image, container_port),
        )
        core_api.create_namespaced_service(
            namespace=namespace,
            body=build_service(k8s_name, container_port),
        )

        deployment.container_id = k8s_name
        deployment.status = get_kubernetes_deployment_status(k8s_name)
        db.commit()
        logger.info(
            "Deployment %s Kubernetes resources created with status %s",
            deployment_id,
            deployment.status,
        )

    except Exception:
        logger.exception("Deployment %s failed during Kubernetes creation", deployment_id)
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
