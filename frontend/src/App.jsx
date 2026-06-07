import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const API_BASE = "/api";
const WS_BASE = `ws://${window.location.host}/api`;;
const DEFAULT_CPU_REQUEST = "100m";
const DEFAULT_MEMORY_REQUEST = "128Mi";
const DEFAULT_CPU_LIMIT = "500m";
const DEFAULT_MEMORY_LIMIT = "512Mi";

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

function formatResources(deployment, type) {
  if (type === "requests") {
    return `${deployment.cpu_request || DEFAULT_CPU_REQUEST} / ${
      deployment.memory_request || DEFAULT_MEMORY_REQUEST
    }`;
  }

  return `${deployment.cpu_limit || DEFAULT_CPU_LIMIT} / ${
    deployment.memory_limit || DEFAULT_MEMORY_LIMIT
  }`;
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
  onLiveLogs,
  onMetrics,
  onHealth,
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
        className="button button-secondary"
        disabled={isBusy}
        type="button"
        onClick={() => onLiveLogs(deployment)}
      >
        Live Logs
      </button>
      {isRunning && (
        <button
          className="button button-secondary"
          disabled={isBusy}
          type="button"
          onClick={() => onMetrics(deployment)}
        >
          Metrics
        </button>
      )}
      {isRunning && (
        <button
          className="button button-secondary"
          disabled={isBusy}
          type="button"
          onClick={() => onHealth(deployment)}
        >
          Health
        </button>
      )}
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

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }

  return String(value);
}

function MetricsPanel({
  metrics,
  metricsError,
  metricsLoading,
  selectedMetricsName,
}) {
  return (
    <section className="panel metrics-panel" aria-label="Container metrics">
      <div className="panel-header">
        <div>
          <h2>Metrics</h2>
          <p>
            {selectedMetricsName
              ? `Showing resource usage for ${selectedMetricsName}`
              : "Choose a running deployment to view resource usage"}
          </p>
        </div>
      </div>

      <div className="metrics-content">
        {metricsLoading && <Spinner label="Fetching metrics" />}
        {!metricsLoading && metricsError && (
          <p className="metrics-error">{metricsError}</p>
        )}
        {!metricsLoading && !metricsError && metrics && (
          <div className="metrics-grid">
            <div>
              <span>CPU Usage</span>
              <strong>{formatValue(metrics.cpu_usage)}</strong>
            </div>
            <div>
              <span>Memory Usage</span>
              <strong>{formatValue(metrics.memory_usage)}</strong>
            </div>
            <div>
              <span>CPU Request</span>
              <strong>{formatValue(metrics.cpu_request)}</strong>
            </div>
            <div>
              <span>CPU Limit</span>
              <strong>{formatValue(metrics.cpu_limit)}</strong>
            </div>
            <div>
              <span>Memory Request</span>
              <strong>{formatValue(metrics.memory_request)}</strong>
            </div>
            <div>
              <span>Memory Limit</span>
              <strong>{formatValue(metrics.memory_limit)}</strong>
            </div>
          </div>
        )}
        {!metricsLoading && !metricsError && !metrics && (
          <p className="metrics-empty">Metrics will appear here.</p>
        )}
      </div>
    </section>
  );
}

function HealthPanel({ health, healthError, healthLoading, selectedHealthName }) {
  const healthStatus = (health?.health || "unknown").toLowerCase();

  return (
    <section className="panel health-panel" aria-label="Container health">
      <div className="panel-header">
        <div>
          <h2>Health</h2>
          <p>
            {selectedHealthName
              ? `Showing health check for ${selectedHealthName}`
              : "Choose a running deployment to view health status"}
          </p>
        </div>
      </div>

      <div className="metrics-content">
        {healthLoading && <Spinner label="Checking health" />}
        {!healthLoading && healthError && (
          <p className="metrics-error">{healthError}</p>
        )}
        {!healthLoading && !healthError && health && (
          <>
            <span className={`health-badge health-${healthStatus}`}>
              {healthStatus}
            </span>
            <div className="metrics-grid health-grid">
              <div>
                <span>Container Status</span>
                <strong>{formatValue(health.status)}</strong>
              </div>
              <div>
                <span>Status Code</span>
                <strong>{formatValue(health.status_code)}</strong>
              </div>
              <div>
                <span>Host Port</span>
                <strong>{formatValue(health.host_port)}</strong>
              </div>
              <div>
                <span>Container Port</span>
                <strong>{formatValue(health.container_port)}</strong>
              </div>
              <div className="health-url-cell">
                <span>Checked URL</span>
                <strong>{formatValue(health.checked_url)}</strong>
              </div>
            </div>
          </>
        )}
        {!healthLoading && !healthError && !health && (
          <p className="metrics-empty">Health details will appear here.</p>
        )}
      </div>
    </section>
  );
}

function LogsPanel({
  logs,
  logError,
  logLoading,
  logMode,
  liveLogStatus,
  selectedDeploymentName,
  onClear,
  onStopLiveLogs,
}) {
  const isLive = logMode === "live";

  return (
    <section className="panel logs-panel" aria-label="Container logs">
      <div className="panel-header">
        <div>
          <h2>Logs</h2>
          <p>
            {selectedDeploymentName
              ? `${isLive ? "Streaming" : "Showing"} output for ${selectedDeploymentName}`
              : "Choose a deployment to view recent output"}
          </p>
          {isLive && (
            <span className={`live-status live-status-${liveLogStatus}`}>
              {liveLogStatus}
            </span>
          )}
        </div>
        <div className="logs-actions">
          {isLive && liveLogStatus === "connected" && (
            <button
              className="button button-secondary"
              type="button"
              onClick={onStopLiveLogs}
            >
              Stop Live
            </button>
          )}
          <button
            className="button button-secondary"
            disabled={!logs && !logError && !selectedDeploymentName}
            type="button"
            onClick={onClear}
          >
            Clear
          </button>
        </div>
      </div>

      <div className="logs-window">
        {logLoading && (
          <Spinner label={isLive ? "Connecting to logs" : "Fetching logs"} />
        )}
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
  const [cpuRequest, setCpuRequest] = useState(DEFAULT_CPU_REQUEST);
  const [memoryRequest, setMemoryRequest] = useState(DEFAULT_MEMORY_REQUEST);
  const [cpuLimit, setCpuLimit] = useState(DEFAULT_CPU_LIMIT);
  const [memoryLimit, setMemoryLimit] = useState(DEFAULT_MEMORY_LIMIT);
  const [logs, setLogs] = useState("");
  const [logMode, setLogMode] = useState("snapshot");
  const [liveLogStatus, setLiveLogStatus] = useState("idle");
  const [selectedDeploymentName, setSelectedDeploymentName] = useState("");
  const [selectedMetricsName, setSelectedMetricsName] = useState("");
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState("");
  const [selectedHealthName, setSelectedHealthName] = useState("");
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState("");
  const [loadingDeployments, setLoadingDeployments] = useState(true);
  const [logLoading, setLogLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [error, setError] = useState("");
  const [logError, setLogError] = useState("");
  const [toast, setToast] = useState(null);
  const logSocketRef = useRef(null);

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
          cpu_request: cpuRequest,
          memory_request: memoryRequest,
          cpu_limit: cpuLimit,
          memory_limit: memoryLimit,
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

  function closeLiveLogSocket({ resetStatus = true } = {}) {
    if (logSocketRef.current) {
      logSocketRef.current.close();
      logSocketRef.current = null;
    }

    if (resetStatus) {
      setLiveLogStatus("idle");
    }
  }

  async function fetchLogs(deployment) {
    closeLiveLogSocket();
    setSelectedDeploymentName(deployment.name);
    setLogMode("snapshot");
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

  async function fetchMetrics(deployment) {
    setSelectedMetricsName(deployment.name);
    setMetrics(null);
    setMetricsLoading(true);
    setMetricsError("");

    try {
      const data = await apiRequest(
        `/containers/${deployment.container_id}/metrics`,
      );
      setMetrics(data);
    } catch (err) {
      setMetricsError(
        err.message || "Metrics are unavailable for this container right now.",
      );
    } finally {
      setMetricsLoading(false);
    }
  }

  async function fetchHealth(deployment) {
    setSelectedHealthName(deployment.name);
    setHealth(null);
    setHealthLoading(true);
    setHealthError("");

    try {
      const data = await apiRequest(
        `/containers/${deployment.container_id}/health`,
      );
      setHealth(data);
    } catch (err) {
      setHealthError(
        err.message || "Health details are unavailable for this container.",
      );
    } finally {
      setHealthLoading(false);
    }
  }

  function streamLogs(deployment) {
    closeLiveLogSocket({ resetStatus: false });
    setSelectedDeploymentName(deployment.name);
    setLogMode("live");
    setLogs("");
    setLogError("");
    setLogLoading(true);
    setLiveLogStatus("connecting");

    const socket = new WebSocket(
      `${WS_BASE}/ws/containers/${deployment.container_id}/logs`,
    );

    logSocketRef.current = socket;

    socket.onopen = () => {
      setLogLoading(false);
      setLiveLogStatus("connected");
    };

    socket.onmessage = (event) => {
      setLogs((currentLogs) => `${currentLogs}${event.data}`);
    };

    socket.onerror = () => {
      setLogLoading(false);
      setLiveLogStatus("error");
      setLogError("Live logs connection failed.");
    };

    socket.onclose = () => {
      setLogLoading(false);

      if (logSocketRef.current === socket) {
        logSocketRef.current = null;
        setLiveLogStatus((status) =>
          status === "error" ? "error" : "disconnected",
        );
      }
    };
  }

  function stopLiveLogs() {
    closeLiveLogSocket({ resetStatus: false });
    setLiveLogStatus("disconnected");
  }

  function clearLogs() {
    closeLiveLogSocket();
    setLogs("");
    setLogError("");
    setLogMode("snapshot");
    setSelectedDeploymentName("");
  }

  useEffect(() => {
    // Initial server sync for the dashboard data.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchDeployments();

    return () => closeLiveLogSocket();
  }, []);

  return (
    <main className="dashboard-shell">
      <Toast toast={toast} onDismiss={() => setToast(null)} />

      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Mini Render</p>
          <h1>Deployments CI/CD Test Number 4</h1>
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

          <label>
            <span>CPU Request</span>
            <input
              placeholder={DEFAULT_CPU_REQUEST}
              value={cpuRequest}
              onChange={(e) => setCpuRequest(e.target.value)}
              required
            />
          </label>

          <label>
            <span>Memory Request</span>
            <input
              placeholder={DEFAULT_MEMORY_REQUEST}
              value={memoryRequest}
              onChange={(e) => setMemoryRequest(e.target.value)}
              required
            />
          </label>

          <label>
            <span>CPU Limit</span>
            <input
              placeholder={DEFAULT_CPU_LIMIT}
              value={cpuLimit}
              onChange={(e) => setCpuLimit(e.target.value)}
              required
            />
          </label>

          <label>
            <span>Memory Limit</span>
            <input
              placeholder={DEFAULT_MEMORY_LIMIT}
              value={memoryLimit}
              onChange={(e) => setMemoryLimit(e.target.value)}
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
                  <th>Requests</th>
                  <th>Limits</th>
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
                      <td>
                        <code>{formatResources(deployment, "requests")}</code>
                      </td>
                      <td>
                        <code>{formatResources(deployment, "limits")}</code>
                      </td>
                      <td>{formatDate(deployment.created_at)}</td>
                      <td>{formatDate(deployment.deleted_at)}</td>
                      <td>
                        <DeploymentActions
                          deployment={deployment}
                          isBusy={isBusy}
                          onDelete={deleteContainer}
                          onHealth={fetchHealth}
                          onLiveLogs={streamLogs}
                          onLogs={fetchLogs}
                          onMetrics={fetchMetrics}
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
        logMode={logMode}
        liveLogStatus={liveLogStatus}
        selectedDeploymentName={selectedDeploymentName}
        onClear={clearLogs}
        onStopLiveLogs={stopLiveLogs}
      />

      <MetricsPanel
        metrics={metrics}
        metricsError={metricsError}
        metricsLoading={metricsLoading}
        selectedMetricsName={selectedMetricsName}
      />

      <HealthPanel
        health={health}
        healthError={healthError}
        healthLoading={healthLoading}
        selectedHealthName={selectedHealthName}
      />
    </main>
  );
}

export default App;
