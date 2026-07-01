const state = {
  projects: [],
  models: [],
  modelTaskTypes: [],
};

const AUTO_REFRESH_MS = 5000;
let refreshTimer = null;

const elements = {
  projectForm: document.getElementById("projectForm"),
  projectList: document.getElementById("projectList"),
  activityLog: document.getElementById("activityLog"),
  modelCreateForm: document.getElementById("modelCreateForm"),
  resetModelsButton: document.getElementById("resetModelsButton"),
  refreshButton: document.getElementById("refreshButton"),
  refreshMeta: document.getElementById("refreshMeta"),
  modelList: document.getElementById("modelList"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
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

  elements.projectList.innerHTML = state.projects
    .map(
      (project) => `
        <div class="project-card">
          <div class="project-card-header">
            <div>
              <div class="project-name">${project.name}</div>
              <div class="project-root">${project.root}</div>
            </div>
            <div class="status-tag-row">
              <span class="tag ${project.status}">${statusLabel(project.status)}</span>
              <span class="tag">${project.initialized ? "Initialized" : "Needs Init"}</span>
            </div>
          </div>
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
          </div>
          <div class="project-context">
            <div><strong>最近目标：</strong>${project.latest_goal || "暂无"}</div>
            <div><strong>最近任务：</strong>${project.latest_task_title || "暂无"}</div>
            <div><strong>技术栈：</strong>${formatList(project.languages)} / ${formatList(project.frameworks)}</div>
            <div class="small-note">最近端口：${project.port || project.last_port || "-"} | 最近任务更新时间：${project.last_task_updated_at || "-"}</div>
          </div>
          <div class="project-actions">
            <button type="button" class="button primary open-project-button" data-project-id="${project.project_id}">打开项目</button>
            <button type="button" class="button secondary scan-project-button" data-project-id="${project.project_id}">扫描项目</button>
            <button type="button" class="button ghost refresh-project-button" data-project-id="${project.project_id}">刷新状态</button>
            <button type="button" class="button warn stop-project-button" data-project-id="${project.project_id}">停止</button>
          </div>
        </div>
      `,
    )
    .join("");

  document.querySelectorAll(".open-project-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api("/api/projects/open", {
          method: "POST",
          body: JSON.stringify({ project_id: button.dataset.projectId }),
        });
        await refreshProjects();
        setActivity(`已打开项目：${data.project.name}\n${data.url}`);
        window.open(data.url, "_blank", "noopener");
      }, "打开项目失败。");
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

function renderModels() {
  if (!state.models.length) {
    elements.modelList.innerHTML = `<div class="empty-state">还没有全局模型配置。</div>`;
    return;
  }

  elements.modelList.innerHTML = state.models
    .map(
      (model) => `
        <form class="model-item" data-model-id="${model.id}">
          <div class="model-item-header">
            <div>
              <div class="model-name">${model.label}</div>
              <div class="model-meta">${model.id} / ${model.provider}</div>
            </div>
            <label class="model-toggle">
              <input type="checkbox" name="enabled" ${model.enabled ? "checked" : ""} />
              <span>启用</span>
            </label>
          </div>
          <label>
            <span>模型 ID</span>
            <input name="modelId" value="${model.id}" required />
          </label>
          <label>
            <span>显示名称</span>
            <input name="label" value="${model.label}" />
          </label>
          <label>
            <span>提供方</span>
            <input name="provider" value="${model.provider}" placeholder="例如：openai" />
          </label>
          <label>
            <span>适合任务类型</span>
            <input name="taskTypes" value="${model.task_types.join(", ")}" placeholder="例如：bug_fix, testing" />
          </label>
          <label>
            <span>推荐优先级</span>
            <input name="rank" type="number" min="1" value="${model.rank}" />
          </label>
          <div class="model-item-actions">
            <button type="submit" class="button secondary">保存</button>
            <button type="button" class="button warn delete-model-button" data-model-id="${model.id}">删除</button>
          </div>
        </form>
      `,
    )
    .join("");

  document.querySelectorAll(".model-item").forEach((formElement) => {
    formElement.addEventListener("submit", async (event) => {
      event.preventDefault();
      await runAction(async () => {
        const form = new FormData(formElement);
        const payload = {
          current_model_id: formElement.dataset.modelId,
          model_id: String(form.get("modelId") || "").trim(),
          label: String(form.get("label") || "").trim(),
          provider: String(form.get("provider") || "").trim(),
          enabled: form.get("enabled") === "on",
          rank: Number(form.get("rank") || 1),
          task_types: parseTaskTypes(form.get("taskTypes")),
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

function formatList(items) {
  return items && items.length ? items.join(", ") : "未识别";
}

function parseTaskTypes(rawValue) {
  return String(rawValue || "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => state.modelTaskTypes.includes(item));
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
  renderModels();
}

async function refreshAll() {
  await Promise.all([refreshProjects(), refreshModels()]);
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

elements.modelCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const payload = {
      model_id: String(form.get("model_id") || "").trim(),
      label: String(form.get("label") || "").trim(),
      provider: String(form.get("provider") || "").trim(),
      enabled: form.get("enabled") === "on",
      rank: Number(form.get("rank") || 1),
      task_types: parseTaskTypes(form.get("taskTypes")),
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
