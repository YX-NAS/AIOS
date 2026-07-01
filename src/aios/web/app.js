const state = {
  status: null,
  tasks: [],
  packs: [],
  handoffs: [],
  selectedTaskId: null,
};

const elements = {
  rootPath: document.getElementById("rootPath"),
  statusText: document.getElementById("statusText"),
  statusPill: document.getElementById("statusPill"),
  metricTasks: document.getElementById("metricTasks"),
  metricOpen: document.getElementById("metricOpen"),
  metricDone: document.getElementById("metricDone"),
  metricFiles: document.getElementById("metricFiles"),
  initEmptyState: document.getElementById("initEmptyState"),
  projectStatus: document.getElementById("projectStatus"),
  languageTags: document.getElementById("languageTags"),
  frameworkTags: document.getElementById("frameworkTags"),
  taskTableBody: document.getElementById("taskTableBody"),
  taskEmpty: document.getElementById("taskEmpty"),
  taskInspector: document.getElementById("taskInspector"),
  taskTitle: document.getElementById("taskTitle"),
  taskMeta: document.getElementById("taskMeta"),
  acceptanceList: document.getElementById("acceptanceList"),
  routeCard: document.getElementById("routeCard"),
  packList: document.getElementById("packList"),
  activityLog: document.getElementById("activityLog"),
  refreshButton: document.getElementById("refreshButton"),
  scanButton: document.getElementById("scanButton"),
  copyCurrentPackButton: document.getElementById("copyCurrentPackButton"),
  copyHandoffButton: document.getElementById("copyHandoffButton"),
  initForm: document.getElementById("initForm"),
  goalPlanForm: document.getElementById("goalPlanForm"),
  taskForm: document.getElementById("taskForm"),
  packForm: document.getElementById("packForm"),
  completeForm: document.getElementById("completeForm"),
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

async function runAction(action, fallbackMessage) {
  try {
    await action();
  } catch (error) {
    setActivity(error.message || fallbackMessage);
  }
}

function setActivity(message) {
  elements.activityLog.textContent = message;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const helper = document.createElement("textarea");
  helper.value = text;
  helper.setAttribute("readonly", "true");
  helper.style.position = "absolute";
  helper.style.left = "-9999px";
  document.body.appendChild(helper);
  helper.select();
  document.execCommand("copy");
  helper.remove();
}

function renderStatus() {
  const status = state.status;
  elements.rootPath.textContent = status.root;
  elements.metricTasks.textContent = String(status.task_count);
  elements.metricOpen.textContent = String(status.open_tasks);
  elements.metricDone.textContent = String(status.done_tasks);
  elements.metricFiles.textContent = String(status.file_count);

  if (status.initialized) {
    elements.statusPill.textContent = "Initialized";
    elements.statusPill.className = "status-pill ready";
    elements.statusText.textContent = `已接管 ${status.root}，当前已索引 ${status.file_count} 个文件。`;
    elements.initEmptyState.classList.add("hidden");
    elements.projectStatus.classList.remove("hidden");
    elements.scanButton.disabled = false;
  } else {
    elements.statusPill.textContent = "Needs Init";
    elements.statusPill.className = "status-pill empty";
    elements.statusText.textContent = "当前目录还没有 .aios 项目元数据，先初始化再继续。";
    elements.projectStatus.classList.add("hidden");
    elements.initEmptyState.classList.remove("hidden");
    elements.scanButton.disabled = true;
  }

  elements.languageTags.innerHTML = (status.languages || [])
    .map((item) => `<span class="tag">${item}</span>`)
    .join("");
  elements.frameworkTags.innerHTML = (status.frameworks || [])
    .map((item) => `<span class="tag">${item}</span>`)
    .join("");
}

function renderTasks() {
  if (!state.tasks.length) {
    elements.taskTableBody.innerHTML = `<tr><td colspan="4">暂无任务。</td></tr>`;
    return;
  }

  elements.taskTableBody.innerHTML = state.tasks
    .map((task) => {
      const isActive = task.id === state.selectedTaskId ? "active" : "";
      return `
        <tr class="task-row ${isActive}" data-task-id="${task.id}">
          <td>${task.id}<br><strong>${task.title}</strong></td>
          <td>${task.status}</td>
          <td>${task.type}</td>
          <td>${task.recommended_model}</td>
        </tr>
      `;
    })
    .join("");

  document.querySelectorAll(".task-row").forEach((row) => {
    row.addEventListener("click", async () => {
      state.selectedTaskId = row.dataset.taskId;
      renderTasks();
      await loadTaskInspector();
    });
  });
}

function renderPacks() {
  if (!state.packs.length) {
    elements.packList.innerHTML = `<div class="empty-state compact"><p>还没有生成 Context Pack。</p></div>`;
    return;
  }
  elements.packList.innerHTML = state.packs
    .map(
      (pack) => `
        <div class="pack-item">
          <div class="pack-name">${pack.name}</div>
          <div class="pack-path">${pack.path}</div>
          <div class="pack-actions">
            <button type="button" class="button subtle copy-pack-button" data-pack-name="${pack.name}">复制内容</button>
            <button type="button" class="button secondary copy-pack-path-button" data-pack-path="${pack.path}">复制路径</button>
          </div>
        </div>
      `,
    )
    .join("");

  document.querySelectorAll(".copy-pack-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        const data = await api(`/api/packs/content/${encodeURIComponent(button.dataset.packName)}`);
        await copyText(data.pack.content);
        setActivity(`已复制 ${data.pack.name} 的内容。`);
      }, "复制 Context Pack 失败。");
    });
  });

  document.querySelectorAll(".copy-pack-path-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await runAction(async () => {
        await copyText(button.dataset.packPath);
        setActivity(`已复制路径：${button.dataset.packPath}`);
      }, "复制路径失败。");
    });
  });
}

async function loadTaskInspector() {
  if (!state.selectedTaskId) {
    elements.taskEmpty.classList.remove("hidden");
    elements.taskInspector.classList.add("hidden");
    return;
  }
  const [{ task }, { route }] = await Promise.all([
    api(`/api/tasks/${state.selectedTaskId}`),
    api(`/api/route/${state.selectedTaskId}`),
  ]);
  elements.taskEmpty.classList.add("hidden");
  elements.taskInspector.classList.remove("hidden");
  elements.taskTitle.textContent = task.title;
  elements.taskMeta.textContent = `${task.id} | ${task.status} | ${task.priority} | ${task.recommended_model}`;
  elements.acceptanceList.innerHTML = task.acceptance_criteria.map((item) => `<li>${item}</li>`).join("");
  elements.routeCard.innerHTML = `
    <strong>${route.recommended_model}</strong>
    <div class="muted">Fallback: ${route.fallback_models.join(", ")}</div>
    <ul class="simple-list">${route.reason.map((item) => `<li>${item}</li>`).join("")}</ul>
  `;

  const hasPack = state.packs.some((pack) => pack.task_id === task.id);
  elements.copyCurrentPackButton.classList.toggle("hidden", !hasPack);
}

async function refreshDashboard() {
  const [statusData, tasksData, packsData, handoffsData] = await Promise.all([
    api("/api/status"),
    api("/api/tasks"),
    api("/api/packs"),
    api("/api/handoffs"),
  ]);
  state.status = statusData;
  state.tasks = tasksData.tasks;
  state.packs = packsData.packs;
  state.handoffs = handoffsData.handoffs;
  if (!state.selectedTaskId && state.tasks.length) {
    state.selectedTaskId = state.tasks[0].id;
  }
  renderStatus();
  renderTasks();
  renderPacks();
  await loadTaskInspector();
}

elements.refreshButton.addEventListener("click", async () => {
  await runAction(async () => {
    await refreshDashboard();
    setActivity("已刷新项目状态。");
  }, "刷新失败。");
});

elements.scanButton.addEventListener("click", async () => {
  await runAction(async () => {
    const data = await api("/api/scan", { method: "POST", body: JSON.stringify({}) });
    await refreshDashboard();
    setActivity(`${data.message}\n已识别 ${data.report.summary.file_count} 个文件。`);
  }, "扫描失败。");
});

elements.initForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runAction(async () => {
    const form = new FormData(event.currentTarget);
    const payload = {
      name: form.get("name"),
      type: form.get("type"),
    };
    const data = await api("/api/init", { method: "POST", body: JSON.stringify(payload) });
    await refreshDashboard();
    const createdText = data.created.length ? `\n${data.created.join("\n")}` : "";
    setActivity(`${data.message}${createdText}`);
  }, "初始化失败。");
});

elements.taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const payload = {
      title: form.get("title"),
      priority: form.get("priority"),
    };
    const data = await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
    state.selectedTaskId = data.task.id;
    formElement.reset();
    await refreshDashboard();
    setActivity(`已创建任务 ${data.task.id}。`);
  }, "创建任务失败。");
});

elements.goalPlanForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const payload = {
      goal: form.get("goal"),
      priority: form.get("priority"),
    };
    const data = await api("/api/tasks/plan", { method: "POST", body: JSON.stringify(payload) });
    state.selectedTaskId = data.tasks[0]?.id || state.selectedTaskId;
    formElement.reset();
    await refreshDashboard();
    const summary = data.tasks.map((task) => `${task.id} | ${task.recommended_model} | ${task.title}`).join("\n");
    setActivity(`已完成目标拆分，共 ${data.tasks.length} 条任务。\n${summary}`);
  }, "目标拆分失败。");
});

elements.packForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const form = new FormData(event.currentTarget);
    const payload = {
      task_id: state.selectedTaskId,
      model: form.get("model"),
    };
  const data = await api("/api/pack", { method: "POST", body: JSON.stringify(payload) });
  await refreshDashboard();
  setActivity(`已生成 Context Pack：${data.path}`);
  }, "生成 Context Pack 失败。");
});

elements.copyCurrentPackButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api(`/api/packs/by-task/${encodeURIComponent(state.selectedTaskId)}`);
    await copyText(data.pack.content);
    setActivity(`已复制 ${data.pack.name} 的内容。`);
  }, "复制当前任务 Context Pack 失败。");
});

elements.copyHandoffButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const task = state.tasks.find((item) => item.id === state.selectedTaskId);
    const data = await api("/api/handoff", {
      method: "POST",
      body: JSON.stringify({
        task_id: state.selectedTaskId,
        model: task?.recommended_model || "",
      }),
    });
    await refreshDashboard();
    await copyText(data.handoff.content);
    setActivity(`已生成并复制任务交接单：${data.handoff.handoff_path}`);
  }, "生成任务交接单失败。");
});

elements.completeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const form = new FormData(event.currentTarget);
    const payload = {
      task_id: state.selectedTaskId,
      summary: form.get("summary"),
    };
    const data = await api("/api/complete", { method: "POST", body: JSON.stringify(payload) });
    await refreshDashboard();
    setActivity(`已完成任务 ${data.task.id}。`);
  }, "完成任务失败。");
});

refreshDashboard().catch((error) => {
  setActivity(error.message);
  elements.statusText.textContent = "加载失败，请刷新页面重试。";
});
