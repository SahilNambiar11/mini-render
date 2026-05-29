import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

async function apiRequest(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  let data;

  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    throw new Error(data?.detail || "Request failed. Please try again.");
  }

  return data;
}

function formatDate(value) {
  if (!value) return "Not set";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Invalid date";

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function shortId(value) {
  return value ? value.slice(0, 12) : "Unavailable";
}

function Spinner({ label = "Loading" }) {
  return (
    <span className="spinner-wrap" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

function StatusBadge({ status }) {
  const normalizedStatus = (status || "unknown").toLowerCase();

  return (
    <span className={`status-badge status-${normalizedStatus}`}>
      {normalizedStatus}
    </span>
  );
}

function Toast({ toast, onDismiss }) {
  if (!toast) return null;

  return (
    <div className={`toast toast-${toast.type}`} role="status">
      <span>{toast.message}</span>
      <button className="icon-button" type="button" onClick={onDismiss}>
        Close
      </button>
    </div>
  );
}

function DeploymentActions({
  deployment,
  isBusy,
  onStop,
  onRestart,
  onDelete,
  onLogs,
}) {
  const status = (deployment.status || "").toLowerCase();
  const isDeleted = status === "deleted";
  const isRunning = status === "running";

  if (isDeleted) {
    return <span className="muted-text">No actions</span>;
  }

  return (
    <div className="action-row">
      {isRunning && (
        <button
          className="button button-secondary"
          disabled={isBusy}
          type="button"
          onClick={() => onStop(deployment)}
        >
          Stop
        </button>
      )}
      <button
        className="button button-secondary"
        disabled={isBusy}
        type="button"
        onClick={() => onRestart(deployment)}
      >
        Restart
      </button>
      <button
        className="button button-secondary"
        disabled={isBusy}
        type="button"
        onClick={() => onLogs(deployment)}
      >
        Logs
      </button>
      <button
        className="button button-danger"
        disabled={isBusy}
        type="button"
        onClick={() => onDelete(deployment)}
      >
        Delete
      </button>
    </div>
  );
}

function LogsPanel({
  logs,
  logError,
  logLoading,
  selectedDeploymentName,
  onClear,
}) {
  return (
    <section className="panel logs-panel" aria-label="Container logs">
      <div className="panel-header">
        <div>
          <h2>Logs</h2>
          <p>
            {selectedDeploymentName
              ? `Showing output for ${selectedDeploymentName}`
              : "Choose a deployment to view recent output"}
          </p>
        </div>
        <button
          className="button button-secondary"
          disabled={!logs && !logError && !selectedDeploymentName}
          type="button"
          onClick={onClear}
        >
          Clear
        </button>
      </div>

      <div className="logs-window">
        {logLoading && <Spinner label="Fetching logs" />}
        {!logLoading && logError && <p className="logs-error">{logError}</p>}
        {!logLoading && !logError && logs && <pre>{logs}</pre>}
        {!logLoading && !logError && !logs && (
          <p className="logs-empty">Logs will appear here.</p>
        )}
      </div>
    </section>
  );
}

function App() {
  const [deployments, setDeployments] = useState([]);
  const [image, setImage] = useState("nginx");
  const [containerPort, setContainerPort] = useState(80);
  const [name, setName] = useState("");
  const [logs, setLogs] = useState("");
  const [selectedDeploymentName, setSelectedDeploymentName] = useState("");
  const [loadingDeployments, setLoadingDeployments] = useState(true);
  const [logLoading, setLogLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [error, setError] = useState("");
  const [logError, setLogError] = useState("");
  const [toast, setToast] = useState(null);

  const deploymentCounts = useMemo(() => {
    return deployments.reduce(
      (counts, deployment) => {
        const status = (deployment.status || "unknown").toLowerCase();
        return {
          ...counts,
          total: counts.total + 1,
          [status]: (counts[status] || 0) + 1,
        };
      },
      { total: 0, running: 0, stopped: 0, deleted: 0 },
    );
  }, [deployments]);

  function showToast(message, type = "success") {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 3500);
  }

  async function fetchDeployments({ quiet = false } = {}) {
    if (!quiet) {
      setLoadingDeployments(true);
    }
    setError("");

    try {
      const data = await apiRequest("/deployments");
      setDeployments(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingDeployments(false);
    }
  }

  async function deployContainer(e) {
    e.preventDefault();
    setPendingAction("deploy");
    setError("");

    try {
      await apiRequest("/containers", {
        method: "POST",
        body: JSON.stringify({
          image,
          container_port: Number(containerPort),
          name,
        }),
      });

      setName("");
      await fetchDeployments({ quiet: true });
      showToast(`Deployed ${name}`);
    } catch (err) {
      setError(err.message);
      showToast("Deployment failed", "error");
    } finally {
      setPendingAction("");
    }
  }

  async function runDeploymentAction(deployment, action, request) {
    const key = `${action}-${deployment.container_id}`;
    setPendingAction(key);
    setError("");

    try {
      await request();
      await fetchDeployments({ quiet: true });
      showToast(`${deployment.name} ${action} request completed`);
    } catch (err) {
      setError(err.message);
      showToast(`Could not ${action} ${deployment.name}`, "error");
    } finally {
      setPendingAction("");
    }
  }

  async function stopContainer(deployment) {
    await runDeploymentAction(deployment, "stop", () =>
      apiRequest(`/containers/${deployment.container_id}/stop`, {
        method: "POST",
      }),
    );
  }

  async function restartContainer(deployment) {
    await runDeploymentAction(deployment, "restart", () =>
      apiRequest(`/containers/${deployment.container_id}/restart`, {
        method: "POST",
      }),
    );
  }

  async function deleteContainer(deployment) {
    const confirmed = window.confirm(
      `Delete ${deployment.name}? This removes the container.`,
    );

    if (!confirmed) return;

    await runDeploymentAction(deployment, "delete", () =>
      apiRequest(`/containers/${deployment.container_id}`, {
        method: "DELETE",
      }),
    );
  }

  async function fetchLogs(deployment) {
    setSelectedDeploymentName(deployment.name);
    setLogLoading(true);
    setLogError("");

    try {
      const data = await apiRequest(
        `/containers/${deployment.container_id}/logs`,
      );
      setLogs(data.logs || "No logs returned for this container.");
    } catch (err) {
      setLogs("");
      setLogError(
        err.message || "Logs are unavailable for this container right now.",
      );
    } finally {
      setLogLoading(false);
    }
  }

  function clearLogs() {
    setLogs("");
    setLogError("");
    setSelectedDeploymentName("");
  }

  useEffect(() => {
    // Initial server sync for the dashboard data.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchDeployments();
  }, []);

  return (
    <main className="dashboard-shell">
      <Toast toast={toast} onDismiss={() => setToast(null)} />

      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Mini Render</p>
          <h1>Deployments</h1>
        </div>
        <div className="summary-grid" aria-label="Deployment summary">
          <div>
            <span>{deploymentCounts.total}</span>
            <p>Total</p>
          </div>
          <div>
            <span>{deploymentCounts.running}</span>
            <p>Running</p>
          </div>
          <div>
            <span>{deploymentCounts.stopped}</span>
            <p>Stopped</p>
          </div>
        </div>
      </header>

      <section className="panel deploy-panel" aria-label="Deploy container">
        <div className="panel-header">
          <div>
            <h2>Deploy Container</h2>
            <p>Create a new Docker-backed deployment.</p>
          </div>
        </div>

        <form className="deploy-form" onSubmit={deployContainer}>
          <label>
            <span>Service name</span>
            <input
              placeholder="api-service"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>

          <label>
            <span>Image</span>
            <input
              placeholder="nginx"
              value={image}
              onChange={(e) => setImage(e.target.value)}
              required
            />
          </label>

          <label>
            <span>Container port</span>
            <input
              min="1"
              max="65535"
              placeholder="80"
              type="number"
              value={containerPort}
              onChange={(e) => setContainerPort(e.target.value)}
              required
            />
          </label>

          <button
            className="button button-primary"
            disabled={pendingAction === "deploy"}
            type="submit"
          >
            {pendingAction === "deploy" ? "Deploying..." : "Deploy"}
          </button>
        </form>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="panel table-panel" aria-label="Deployment table">
        <div className="panel-header">
          <div>
            <h2>Deployment List</h2>
            <p>Manage running, stopped, and deleted services.</p>
          </div>
          <button
            className="button button-secondary"
            disabled={loadingDeployments}
            type="button"
            onClick={() => fetchDeployments()}
          >
            Refresh
          </button>
        </div>

        {loadingDeployments ? (
          <div className="center-state">
            <Spinner label="Loading deployments" />
          </div>
        ) : deployments.length === 0 ? (
          <div className="center-state">
            <h3>No deployments yet</h3>
            <p>Deploy your first container to see it listed here.</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Service</th>
                  <th>Image</th>
                  <th>Status</th>
                  <th>Container ID</th>
                  <th>Created</th>
                  <th>Deleted</th>
                  <th className="actions-heading">Actions</th>
                </tr>
              </thead>
              <tbody>
                {deployments.map((deployment) => {
                  const rowActionPrefix = `-${deployment.container_id}`;
                  const isBusy =
                    pendingAction.endsWith(rowActionPrefix) ||
                    pendingAction === "deploy";

                  return (
                    <tr key={deployment.id}>
                      <td className="numeric-cell">#{deployment.id}</td>
                      <td>
                        <strong>{deployment.name}</strong>
                      </td>
                      <td>
                        <code>{deployment.image}</code>
                      </td>
                      <td>
                        <StatusBadge status={deployment.status} />
                      </td>
                      <td>
                        <code>{shortId(deployment.container_id)}</code>
                      </td>
                      <td>{formatDate(deployment.created_at)}</td>
                      <td>{formatDate(deployment.deleted_at)}</td>
                      <td>
                        <DeploymentActions
                          deployment={deployment}
                          isBusy={isBusy}
                          onDelete={deleteContainer}
                          onLogs={fetchLogs}
                          onRestart={restartContainer}
                          onStop={stopContainer}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <LogsPanel
        logs={logs}
        logError={logError}
        logLoading={logLoading}
        selectedDeploymentName={selectedDeploymentName}
        onClear={clearLogs}
      />
    </main>
  );
}

export default App;
