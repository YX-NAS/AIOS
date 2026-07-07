const state = {
  projects: [],
  models: [],
  modelTaskTypes: [],
  workbench: null,
  productionProjects: [],
};

const AUTO_REFRESH_MS = 5000;
let refreshTimer = null;

const elements = {
  projectForm: document.getElementById("projectForm"),
  projectRoot: document.getElementById("projectRoot"),
  projectName: document.getElementById("projectName"),
  pickFolderButton: document.getElementById("pickFolderButton"),
  projectList: document.getElementById("projectList"),
  activityLog: document.getElementById("activityLog"),
  modelCreateForm: document.getElementById("modelCreateForm"),
  resetModelsButton: document.getElementById("resetModelsButton"),
  refreshButton: document.getElementById("refreshButton"),
  refreshMeta: document.getElementById("refreshMeta"),
  modelList: document.getElementById("modelList"),
  workbenchStats: document.getElementById("workbenchStats"),
  todayFocus: document.getElementById("todayFocus"),
  productionProjectList: document.getElementById("productionProjectList"),
  readyQueue: document.getElementById("readyQueue"),
  takeoverQueue: document.getElementById("takeoverQueue"),
  reviewQueue: document.getElementById("reviewQueue"),
  activeRuns: document.getElementById("activeRuns"),
  infraSummary: document.getElementById("infraSummary"),
  recentActivity: document.getElementById("recentActivity"),
};

async function api(path, options = {}) {
  const fetchOptions = { ...options };
  if (fetchOptions.method === "POST" || fetchOptions.body) {
    fetchOptions.headers = { "Content-Type": "application/json", ...(fetchOptions.headers || {}) };
  }
  const response = await fetch(path, fetchOptions);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function setActivity(message) {
  elements.activityLog.textContent = message;
}

async function runAction(action, fallbackMessage) {
  try {
    await action();
  } catch (error) {
    setActivity(error.message || fallbackMessage);
  }
}

function renderProjects() {
  if (!state.projects.length) {
    elements.projectList.innerHTML = `<div class="empty-state">还没有登记项目。先在左侧添加一个项目目录。</div>`;
    return;
  }

  const shouldCollapse = state.projects.length > 3;

  elements.projectList.innerHTML = state.projects
    .map(
      (project, index) => {
        const collapsed = shouldCollapse && index !== 0 ? "collapsed" : "";
        return `
        <div class="project-card ${collapsed} health-${project.health_state || "unknown"}" data-project-id="${project.project_id}">
          <div class="project-card-header" data-toggle="expand">
            <div>
              <div class="project-name-row">
                <div class="project-name">${project.name}</div>
                <span class="health-pill ${project.health_state || "unknown"}">${project.health_label || "未知"}</span>
              </div>
              <div class="project-root">${project.root}</div>
            </div>
            <div class="status-tag-row">
              <span class="tag ${project.status}">${statusLabel(project.status)}</span>
              <span class="tag">${project.initialized ? "Initialized" : "Needs Init"}</span>
              ${shouldCollapse ? '<button type="button" class="button ghost toggle-expand-button">展开</button>' : ""}
            </div>
          </div>
          <div class="project-card-body">
          <div class="health-reasons">${formatReasons(project.health_reasons)}</div>
          <div class="project-url">${project.url || "未启动"}</div>
          <div class="project-metrics">
            <div class="metric-tile">
              <div class="metric-value">${project.task_count}</div>
              <div class="metric-label">任务总数</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.open_tasks}</div>
              <div class="metric-label">未完成</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.done_tasks}</div>
              <div class="metric-label">已完成</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.file_count}</div>
              <div class="metric-label">已索引文件</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.enabled_model_count}</div>
              <div class="metric-label">启用模型</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.provider_ready_count || 0}</div>
              <div class="metric-label">Provider 就绪</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.available_executor_count || 0}</div>
              <div class="metric-label">可用执行器</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.active_execution_count}</div>
              <div class="metric-label">活跃执行</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.pending_takeover_count || 0}</div>
              <div class="metric-label">待接管</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${formatCost(project.total_estimated_cost, project.cost_currency)}</div>
              <div class="metric-label">累计估算成本</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.ready_count || 0}</div>
              <div class="metric-label">可执行</div>
            </div>
            <div class="metric-tile">
              <div class="metric-value">${project.blocked_count || 0}</div>
              <div class="metric-label">被阻塞</div>
            </div>
          </div>
          <div class="project-context">
            <div><strong>最近目标：</strong>${project.latest_goal || "暂无"}</div>
            <div><strong>最近任务：</strong>${project.latest_task_title || "暂无"}</div>
            <div><strong>技术栈：</strong>${formatList(project.languages)} / ${formatList(project.frameworks)}</div>
            <div class="small-note">最近端口：${project.port || project.last_port || "-"} | 最近任务更新时间：${project.last_task_updated_at || "-"}</div>
            <div class="small-note">最近执行状态：${project.latest_execution_status || "-"} | 最近执行更新时间：${project.last_execution_updated_at || "-"}</div>
            <div class="small-note">累计 Token：${project.total_token_estimate || 0} | 平均执行时长：${formatDuration(project.average_duration_seconds)} | 最近执行时长：${formatDuration(project.latest_execution_duration_seconds)}</div>
            <div class="small-note">待复核：${project.review_pending_count || 0} | 执行失败：${project.failed_count || 0} | 下一步：${project.scheduler_next_action || "-"}</div>
            <div class="small-note">Provider 握手：${project.provider_handshake_ready_count || 0} 正常 / ${project.provider_handshake_failed_count || 0} 失败 | API 权限：${project.provider_api_verified_count || 0} 通过 / ${project.provider_api_failed_count || 0} 失败</div>
            <div class="small-note">调度策略：${project.runtime_policy_dispatch_strategy || "default"} | 剩余预算：${formatCost(project.remaining_total_budget, project.cost_currency)} | 单次上限：${formatCost(project.runtime_policy_max_single_execution_cost, project.cost_currency)}</div>
            <div class="small-note">下一条任务：${project.scheduler_next_task_title || "-"}</div>
          </div>
            <div class="project-actions">
              <button type="button" class="button primary open-project-button" data-project-id="${project.project_id}">打开项目</button>
              <button type="button" class="button secondary scan-project-button" data-project-id="${project.project_id}">扫描项目</button>
              <button type="button" class="button ghost refresh-project-button" data-project-id="${project.project_id}">刷新状态</button>
              <button type="button" class="button warn stop-project-button" data-project-id="${project.project_id}">停止</button>
            </div>
          </div>
        </div>
      `;
      },
    )
    .join("");

  document.querySelectorAll(".toggle-expand-button").forEach((button) => {
    button.addEventListener("click", (e) => {
      e.stopPropagation();
      const card = button.closest(".project-card");
      card.classList.toggle("collapsed");
      button.textContent = card.classList.contains("collapsed") ? "展开" : "收起";
    });
  });

  document.querySelectorAll(".open-project-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await openProject(button.dataset.projectId);
    });
  });

  document.querySelectorAll(".refresh-project-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api(`/api/projects/${button.dataset.projectId}/status`);
        await refreshProjects();
        setActivity(`已刷新项目状态：${data.project.name} -> ${statusLabel(data.project.status)}`);
      }, "刷新项目状态失败。");
    });
  });

  document.querySelectorAll(".scan-project-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api("/api/projects/scan", {
          method: "POST",
          body: JSON.stringify({ project_id: button.dataset.projectId }),
        });
        await refreshProjects();
        setActivity(`已扫描项目：${data.project.name}\n识别 ${data.report.summary.file_count} 个文件。`);
      }, "扫描项目失败。");
    });
  });

  document.querySelectorAll(".stop-project-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api("/api/projects/stop", {
          method: "POST",
          body: JSON.stringify({ project_id: button.dataset.projectId }),
        });
        await refreshProjects();
        setActivity(`已停止项目：${data.project.name}`);
      }, "停止项目失败。");
    });
  });
}

async function openProject(projectId) {
  await runAction(async () => {
    const data = await api("/api/projects/open", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    });
    await refreshAll();
    setActivity(`已打开项目：${data.project.name}\n${data.url}`);
    window.open(data.url, "_blank", "noopener");
  }, "打开项目失败。");
}

function renderWorkbench() {
  const workbench = state.workbench || {};
  const statItems = [
    ["项目", workbench.project_count || 0],
    ["生产接入", `${workbench.registered_production_count || 0}/${workbench.production_candidate_count || 0}`],
    ["今日任务", workbench.today_open_task_count || 0],
    ["可执行", workbench.ready_task_count || 0],
    ["阻塞", workbench.blocked_task_count || 0],
    ["失败", workbench.failed_task_count || 0],
    ["执行中", workbench.active_execution_count || 0],
    ["待接管", workbench.pending_takeover_count || 0],
  ];
  elements.workbenchStats.innerHTML = statItems
    .map(
      ([label, value]) => `
        <div class="workbench-stat">
          <div class="workbench-stat-value">${value}</div>
          <div class="workbench-stat-label">${label}</div>
        </div>
      `,
    )
    .join("");

  const focusProjects = workbench.focus_projects || [];
  if (!focusProjects.length) {
    elements.todayFocus.innerHTML = `<div class="empty-state compact-empty">暂无项目状态。先接入一个真实项目。</div>`;
    return;
  }
  elements.todayFocus.innerHTML = `
    <div class="focus-title">今日优先查看</div>
    ${focusProjects
      .map(
        (project) => `
          <div class="focus-item">
            <div>
              <div class="focus-name">${project.name}</div>
              <div class="focus-meta">${project.scheduler_next_task_title || project.latest_task_title || "暂无下一条任务"}</div>
            </div>
            <div class="focus-right">
              <span class="health-pill ${project.health_state || "unknown"}">${project.health_label || "未知"}</span>
              <span class="focus-count">${project.ready_count || 0} 可执行</span>
            </div>
          </div>
        `,
      )
      .join("")}
  `;

  renderWorkbenchQueues(workbench);
  renderInfraSummary(workbench.infra_summary || {});
  renderRecentActivity(workbench.recent_activity || []);
}

function renderWorkbenchQueues(workbench) {
  renderQueueList(elements.readyQueue, workbench.actionable_ready || [], {
    empty: "暂无可直接执行的任务。",
    meta: (item) => `${item.priority || "medium"} · ${item.recommended_model || item.planned_model || "待路由"} · ${item.next_action || "run_executor"}`,
    detail: (item) => item.reason || "依赖已满足，可以开始执行。",
    actionLabel: "进入项目",
  });
  renderQueueList(elements.takeoverQueue, workbench.pending_takeovers || [], {
    empty: "暂无待接管项。",
    meta: (item) => `${item.failure_category || "unknown"} · ${item.takeover_id || "-"}`,
    detail: (item) => item.reason || item.suggested_action || "需要人工处理。",
    actionLabel: "去处理",
  });
  renderQueueList(elements.reviewQueue, workbench.review_queue || [], {
    empty: "暂无待验收任务。",
    meta: (item) => `${item.priority || "medium"} · ${item.actual_model || item.planned_model || item.recommended_model || "-"}`,
    detail: (item) => item.failure_summary || item.reason || "等待 review 与 finish。",
    actionLabel: "去验收",
  });
  renderQueueList(elements.activeRuns, workbench.active_runs || [], {
    empty: "当前没有执行中的任务。",
    meta: (item) => `${item.actual_model || item.planned_model || item.recommended_model || "-"} · ${item.execution_status || item.task_status || "-"}`,
    detail: (item) => item.reason || "任务正在执行或等待执行结果。",
    actionLabel: "去查看",
  });
}

function renderQueueList(container, items, config) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = `<div class="empty-state compact-empty">${config.empty}</div>`;
    return;
  }
  container.innerHTML = items
    .map(
      (item) => `
        <div class="queue-item">
          <div class="queue-main">
            <div class="queue-title-row">
              <div class="queue-title">${item.task_title || item.task_id || item.takeover_id || "未命名项"}</div>
              <span class="health-pill ${item.project_health_state || "unknown"}">${item.project_name || "未知项目"}</span>
            </div>
            <div class="queue-meta">${config.meta(item)}</div>
            <div class="queue-detail">${config.detail(item)}</div>
            <div class="queue-foot">${item.updated_at || item.created_at || "-"}</div>
          </div>
          <div class="queue-actions">
            <button type="button" class="button secondary workbench-open-button" data-project-id="${item.project_id}">${config.actionLabel}</button>
          </div>
        </div>
      `,
    )
    .join("");

  container.querySelectorAll(".workbench-open-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await openProject(button.dataset.projectId);
    });
  });
}

function renderInfraSummary(summary) {
  if (!elements.infraSummary) return;
  const alerts = summary.alerts || [];
  if (!alerts.length) {
    elements.infraSummary.innerHTML = `<div class="empty-state compact-empty">暂无基础设施摘要。</div>`;
    return;
  }
  elements.infraSummary.innerHTML = alerts
    .map(
      (item) => `
        <div class="infra-card level-${item.level || "info"}">
          <div class="infra-value">${item.value || 0}</div>
          <div class="infra-label">${item.label}</div>
          <div class="infra-detail">${item.detail || ""}</div>
        </div>
      `,
    )
    .join("");
}

function renderRecentActivity(items) {
  if (!elements.recentActivity) return;
  if (!items.length) {
    elements.recentActivity.innerHTML = `<div class="empty-state compact-empty">暂无最近活动。</div>`;
    return;
  }
  elements.recentActivity.innerHTML = items
    .map(
      (item) => `
        <div class="recent-item">
          <div class="recent-top">
            <span class="recent-kind">${activityKindLabel(item.kind)}</span>
            <span class="recent-time">${item.happened_at || "-"}</span>
          </div>
          <div class="recent-title">${item.project_name || "未知项目"} · ${item.title || "最近更新"}</div>
          <div class="recent-detail">${item.detail || "-"}</div>
        </div>
      `,
    )
    .join("");
}

function renderProductionProjects() {
  if (!state.productionProjects.length) {
    elements.productionProjectList.innerHTML = `<div class="empty-state compact-empty">暂无生产项目候选。</div>`;
    return;
  }
  elements.productionProjectList.innerHTML = state.productionProjects
    .map(
      (item) => `
        <div class="production-item">
          <div class="production-main">
            <div class="production-title-row">
              <div class="production-name">${item.name}</div>
              <span class="priority-pill">${item.priority}</span>
              <span class="health-pill ${item.health_state || "unknown"}">${item.health_label || "未知"}</span>
            </div>
            <div class="production-role">${item.role}</div>
            <div class="project-root">${item.root}</div>
            <div class="production-meta">${item.registered ? "已登记" : item.exists ? "可接入" : "目录未找到"} · ${item.initialized ? "已初始化" : "未初始化"} · ${item.open_tasks || 0} 未完成 · ${item.ready_count || 0} 可执行</div>
          </div>
          <div class="production-actions">
            ${
              item.registered
                ? `<button type="button" class="button secondary open-production-button" data-project-id="${item.project_id}">打开</button>`
                : `<button type="button" class="button primary register-production-button" data-root="${item.root}" data-name="${item.name}" ${item.exists ? "" : "disabled"}>接入</button>`
            }
          </div>
        </div>
      `,
    )
    .join("");

  document.querySelectorAll(".register-production-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api("/api/projects", {
          method: "POST",
          body: JSON.stringify({ root: button.dataset.root, name: button.dataset.name }),
        });
        await refreshAll();
        setActivity(`已接入生产项目：${data.project.name}`);
      }, "接入生产项目失败。");
    });
  });

  document.querySelectorAll(".open-production-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await openProject(button.dataset.projectId);
    });
  });
}

function renderModels() {
  const emptyEl = document.getElementById("modelEmpty");
  if (!state.models.length) {
    elements.modelList.innerHTML = "";
    emptyEl.classList.remove("hidden");
    renderModelStats();
    return;
  }
  emptyEl.classList.add("hidden");

  // ... table rows rendered below
  _renderModelRows();

  // Populate task type checkboxes in each row
  document.querySelectorAll(".task-type-checkboxes").forEach((box) => {
    const selected = (box.dataset.taskTypes || "").split(",").map((s) => s.trim()).filter(Boolean);
    box.innerHTML = state.modelTaskTypes
      .map((type) => {
        const checked = selected.includes(type) ? "checked" : "";
        return `<label class="task-type-check"><input type="checkbox" name="taskType" value="${type}" ${checked} /><span>${type}</span></label>`;
      })
      .join("");
  });

  bindModelRowEvents();
  renderModelStats();
}

function _renderModelRows() {
  elements.modelList.innerHTML = state.models
    .map(
      (model) => `
        <tr class="model-row" data-model-id="${model.id}">
          <td class="col-id"><input name="modelId" value="${model.id}" required /></td>
          <td class="col-label"><input name="label" value="${model.label}" /></td>
          <td><input name="provider" value="${model.provider}" placeholder="openai" /></td>
          <td><input name="endpoint" value="${model.endpoint || ""}" placeholder="https://api.example.com/v1" /></td>
          <td class="col-price"><div class="cost-input-wrapper"><input name="inputCostPer1m" value="${model.input_cost_per_1m ?? ""}" type="number" min="0" step="0.000001" placeholder="—" /></div></td>
          <td class="col-price"><div class="cost-input-wrapper"><input name="outputCostPer1m" value="${model.output_cost_per_1m ?? ""}" type="number" min="0" step="0.000001" placeholder="—" /></div></td>
          <td class="col-currency"><input name="costCurrency" value="${model.cost_currency || "USD"}" placeholder="USD" /></td>
          <td><input name="authEnvVars" value="${(model.auth_env_vars || []).join(", ")}" placeholder="API_KEY" /></td>
          <td class="td-task-types"><div class="task-type-checkboxes" data-task-types="${model.task_types.join(",")}"></div></td>
          <td class="td-checkbox"><input name="rank" type="number" min="1" value="${model.rank}" class="rank-input" /></td>
          <td>${renderRuntimeBadge(model.runtime)}</td>
          <td class="td-actions">
            <button type="button" class="button ghost probe-model-button" data-model-id="${model.id}">探测</button>
            <button type="button" class="button secondary save-model-button" data-model-id="${model.id}">保存</button>
            <button type="button" class="button warn delete-model-button" data-model-id="${model.id}">删除</button>
          </td>
        </tr>
      `,
    )
    .join("");
}

function renderModelStats() {
  const el = document.getElementById("modelToolbarStats");
  if (!el) return;
  const total = state.models.length;
  const ready = state.models.filter(m => m.runtime && m.runtime.ready).length;
  const priced = state.models.filter(m => m.input_cost_per_1m != null || m.output_cost_per_1m != null).length;
  el.innerHTML =
    `<span>模型 <span class="table-toolbar-stat-value">${total}</span></span>` +
    `<span>就绪 <span class="table-toolbar-stat-value">${ready}</span></span>` +
    `<span>已定价 <span class="table-toolbar-stat-value">${priced}</span></span>`;
}

function bindModelRowEvents() {
  document.querySelectorAll(".save-model-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest(".model-row");
      await runAction(async () => {
        const payload = {
          current_model_id: row.dataset.modelId,
          model_id: String(row.querySelector('input[name="modelId"]').value || "").trim(),
          label: String(row.querySelector('input[name="label"]').value || "").trim(),
          provider: String(row.querySelector('input[name="provider"]').value || "").trim(),
          endpoint: String(row.querySelector('input[name="endpoint"]').value || "").trim(),
          config_url: "",
          auth_env_vars: parseCommaList(row.querySelector('input[name="authEnvVars"]').value || ""),
          input_cost_per_1m: row.querySelector('input[name="inputCostPer1m"]').value || null,
          output_cost_per_1m: row.querySelector('input[name="outputCostPer1m"]').value || null,
          cost_currency: String(row.querySelector('input[name="costCurrency"]').value || "").trim() || "USD",
          notes: "",
          enabled: true,
          rank: Number(row.querySelector('input[name="rank"]').value || 1),
          task_types: (() => {
            const checked = row.querySelectorAll('input[name="taskType"]:checked');
            return Array.from(checked).map((cb) => cb.value);
          })(),
        };
        const data = await api("/api/models/update", { method: "POST", body: JSON.stringify(payload) });
        await refreshAll();
        setActivity(`已更新全局模型：${data.model.label}`);
      }, "保存全局模型配置失败。");
    });
  });

  document.querySelectorAll(".delete-model-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api("/api/models/delete", {
          method: "POST",
          body: JSON.stringify({ model_id: button.dataset.modelId }),
        });
        await refreshAll();
        setActivity(`已删除模型：${button.dataset.modelId}。当前剩余 ${data.models.length} 个模型。`);
      }, "删除模型失败。");
    });
  });

  document.querySelectorAll(".probe-model-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api("/api/models/probe", {
          method: "POST",
          body: JSON.stringify({ model_id: button.dataset.modelId }),
        });
        state.models = data.models;
        state.modelTaskTypes = data.task_types;
        renderModels();
        const result = (data.results || [])[0];
        setActivity(`已完成 provider 探测：${button.dataset.modelId}\n状态：${result?.status || "-"}\nHTTP：${result?.http_status ?? "-"}\n原因：${result?.reason || "-"}`);
      }, "Provider 探测失败。");
    });
  });
}


function statusLabel(status) {
  if (status === "running") {
    return "运行中";
  }
  if (status === "missing") {
    return "路径失效";
  }
  return "未运行";
}

function activityKindLabel(kind) {
  if (kind === "execution") {
    return "执行";
  }
  if (kind === "takeover") {
    return "接管";
  }
  return "任务";
}

function parseCommaList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function inferProjectNameFromRoot(root) {
  const parts = String(root || "")
    .trim()
    .replace(/[\\/]+$/, "")
    .split(/[\\/]/)
    .filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function renderRuntimeBadge(runtime) {
  const data = runtime || {};
  const ready = Boolean(data.ready);
  const authLabel =
    data.auth_status === "ready"
      ? "鉴权已就绪"
      : data.auth_status === "missing_env"
        ? `缺少变量: ${(data.missing_auth_env_vars || []).join(", ") || "-"}`
        : "未配置鉴权";
  const providerLabel = data.provider_config_status === "ready" ? "Provider 已配置" : "缺少 Provider 配置";
  const handshakeLabel =
    data.handshake_status === "ok"
      ? `握手正常${data.handshake_http_status != null ? ` (${data.handshake_http_status})` : ""}`
      : data.handshake_status === "failed"
        ? `握手失败${data.handshake_http_status != null ? ` (${data.handshake_http_status})` : ""}`
        : "未探测";
  const authProbeLabel =
    data.auth_probe_status === "ok"
      ? `权限验证通过${data.auth_probe_http_status != null ? ` (${data.auth_probe_http_status})` : ""}`
      : data.auth_probe_status === "failed"
        ? `权限验证失败${data.auth_probe_http_status != null ? ` (${data.auth_probe_http_status})` : ""}`
        : data.auth_probe_status === "skipped"
          ? "权限验证跳过"
          : "未验权限";
  const reason = data.reason || "可用于执行";
  return `
    <div class="runtime-state ${ready ? "ready" : "blocked"}">
      <div class="runtime-pill">${ready ? "就绪" : "未就绪"}</div>
      <div class="runtime-detail">${providerLabel}</div>
      <div class="runtime-detail">${authLabel}</div>
      <div class="runtime-detail">${handshakeLabel}</div>
      <div class="runtime-detail">${authProbeLabel}</div>
      <div class="runtime-reason">${reason}</div>
    </div>
  `;
}

function formatList(items) {
  return items && items.length ? items.join(", ") : "未识别";
}

function formatReasons(items) {
  const reasons = Array.isArray(items) && items.length ? items : ["暂无状态说明"];
  return reasons.map((item) => `<span>${item}</span>`).join("");
}

function formatCost(amount, currency) {
  const numeric = Number(amount || 0);
  return `${numeric.toFixed(numeric >= 1 ? 2 : 4)} ${currency || "USD"}`;
}

function formatDuration(seconds) {
  if (seconds == null || seconds === "") {
    return "-";
  }
  return `${Number(seconds).toFixed(2)}s`;
}

function getSelectedTaskTypes(selectEl) {
  const selected = [];
  for (const option of selectEl.selectedOptions) {
    selected.push(option.value);
  }
  return selected;
}

function populateTaskTypeOptions(selectEl) {
  selectEl.innerHTML = state.modelTaskTypes
    .map((type) => `<option value="${type}">${type}</option>`)
    .join("");
}

async function refreshProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects;
  renderProjects();
  elements.refreshMeta.textContent = `自动刷新：开启 | 最近刷新：${new Date().toLocaleTimeString()}`;
}

async function refreshModels() {
  const data = await api("/api/models");
  state.models = data.models;
  state.modelTaskTypes = data.task_types;
  populateTaskTypeOptions(document.getElementById("createTaskTypes"));
  renderModels();
}

async function refreshWorkbench() {
  const data = await api("/api/workbench");
  state.workbench = data.workbench;
  state.productionProjects = data.workbench.production_projects || [];
  renderWorkbench();
  renderProductionProjects();
}

async function refreshAll() {
  await Promise.all([refreshProjects(), refreshModels(), refreshWorkbench()]);
}

elements.projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const payload = {
      root: form.get("root"),
      name: form.get("name"),
    };
    const data = await api("/api/projects", { method: "POST", body: JSON.stringify(payload) });
    formElement.reset();
    await refreshAll();
    setActivity(`已添加项目：${data.project.name}`);
  }, "添加项目失败。");
});

elements.pickFolderButton.addEventListener("click", async () => {
  await runAction(async () => {
    const data = await api("/api/projects/pick-folder", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!data.root) {
      setActivity("已取消选择文件夹。");
      return;
    }
    elements.projectRoot.value = data.root;
    if (!String(elements.projectName.value || "").trim()) {
      elements.projectName.value = inferProjectNameFromRoot(data.root);
    }
    setActivity(`已选择项目目录：${data.root}`);
  }, "打开文件夹选择器失败。");
});

elements.modelCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const payload = {
      model_id: String(form.get("model_id") || "").trim(),
      label: String(form.get("label") || "").trim(),
      provider: String(form.get("provider") || "").trim(),
      endpoint: String(form.get("endpoint") || "").trim(),
      config_url: String(form.get("config_url") || "").trim(),
      auth_env_vars: parseCommaList(form.get("auth_env_vars") || ""),
      input_cost_per_1m: form.get("input_cost_per_1m") || null,
      output_cost_per_1m: form.get("output_cost_per_1m") || null,
      cost_currency: String(form.get("cost_currency") || "").trim() || "USD",
      notes: String(form.get("notes") || "").trim(),
      enabled: form.get("enabled") === "on",
      rank: Number(form.get("rank") || 1),
      task_types: getSelectedTaskTypes(formElement.querySelector('select[name="taskTypes"]')),
    };
    const data = await api("/api/models/create", { method: "POST", body: JSON.stringify(payload) });
    formElement.reset();
    formElement.querySelector('input[name="enabled"]').checked = true;
    formElement.querySelector('input[name="rank"]').value = "1";
    await refreshAll();
    setActivity(`已新增模型：${data.model.label}`);
  }, "新增模型失败。");
});

elements.resetModelsButton.addEventListener("click", async () => {
  await runAction(async () => {
    const data = await api("/api/models/reset", { method: "POST", body: JSON.stringify({}) });
    await refreshAll();
    setActivity(`已恢复默认模型库，共 ${data.models.length} 个模型。`);
  }, "恢复默认模型库失败。");
});

elements.refreshButton.addEventListener("click", async () => {
  await runAction(async () => {
    await refreshAll();
    setActivity("已刷新项目状态和全局模型库。");
  }, "刷新失败。");
});

function startAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
  refreshTimer = window.setInterval(() => {
    refreshAll().catch(() => {});
  }, AUTO_REFRESH_MS);
}

refreshAll().catch((error) => {
  setActivity(error.message);
});
startAutoRefresh();
