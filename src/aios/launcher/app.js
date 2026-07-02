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
        <div class="project-card ${collapsed}" data-project-id="${project.project_id}">
          <div class="project-card-header" data-toggle="expand">
            <div>
              <div class="project-name">${project.name}</div>
              <div class="project-root">${project.root}</div>
            </div>
            <div class="status-tag-row">
              <span class="tag ${project.status}">${statusLabel(project.status)}</span>
              <span class="tag">${project.initialized ? "Initialized" : "Needs Init"}</span>
              ${shouldCollapse ? '<button type="button" class="button ghost toggle-expand-button">展开</button>' : ""}
            </div>
          </div>
          <div class="project-card-body">
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
              <div class="metric-value">${project.active_execution_count}</div>
              <div class="metric-label">活跃执行</div>
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
            <div class="small-note">待复核：${project.review_pending_count || 0} | 执行失败：${project.failed_count || 0} | 下一步：${project.scheduler_next_action || "-"}</div>
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
  const emptyEl = document.getElementById("modelEmpty");
  if (!state.models.length) {
    elements.modelList.innerHTML = "";
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  elements.modelList.innerHTML = state.models
    .map(
      (model) => `
        <tr class="model-row" data-model-id="${model.id}">
          <td><input name="modelId" value="${model.id}" required /></td>
          <td><input name="label" value="${model.label}" /></td>
          <td><input name="provider" value="${model.provider}" placeholder="例如：openai" /></td>
          <td class="td-task-types"><div class="task-type-checkboxes" data-task-types="${model.task_types.join(",")}"></div></td>
          <td><input name="rank" type="number" min="1" value="${model.rank}" class="rank-input" /></td>
          <td class="td-checkbox"><label class="model-toggle"><input type="checkbox" name="enabled" ${model.enabled ? "checked" : ""} /><span></span></label></td>
          <td class="td-actions">
            <button type="button" class="button secondary save-model-button" data-model-id="${model.id}">保存</button>
            <button type="button" class="button warn delete-model-button" data-model-id="${model.id}">删除</button>
          </td>
        </tr>
      `,
    )
    .join("");

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

  document.querySelectorAll(".save-model-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest(".model-row");
      await runAction(async () => {
        const enabledCheckbox = row.querySelector('input[name="enabled"]');
        const payload = {
          current_model_id: row.dataset.modelId,
          model_id: String(row.querySelector('input[name="modelId"]').value || "").trim(),
          label: String(row.querySelector('input[name="label"]').value || "").trim(),
          provider: String(row.querySelector('input[name="provider"]').value || "").trim(),
          enabled: enabledCheckbox.checked,
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
