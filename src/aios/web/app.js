const ITEMS_PER_PAGE = 10;

const state = {
  status: null,
  tasks: [],
  taskFilter: "all",
  taskPage: 1,
  packs: [],
  packPage: 1,
  handoffs: [],
  currentExecution: null,
  planPreview: null,
  selectedTaskId: null,
};

const elements = {
  rootPath: document.getElementById("rootPath"),
  projectBadge: document.getElementById("projectBadge"),
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
  executionCard: document.getElementById("executionCard"),
  packList: document.getElementById("packList"),
  activityLog: document.getElementById("activityLog"),
  refreshButton: document.getElementById("refreshButton"),
  taskFilterBar: document.getElementById("taskFilterBar"),
  taskPagination: document.getElementById("taskPagination"),
  packPagination: document.getElementById("packPagination"),
  scanButton: document.getElementById("scanButton"),
  startExecutionButton: document.getElementById("startExecutionButton"),
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
  const projectName = status.root.split(/[\\/]/).filter(Boolean).pop() || status.root;
  elements.rootPath.textContent = status.root;
  elements.projectBadge.textContent = projectName;
  elements.metricTasks.textContent = String(status.task_count);
  elements.metricOpen.textContent = String(status.open_tasks);
  elements.metricDone.textContent = String(status.done_tasks);
  elements.metricFiles.textContent = String(status.file_count);

  if (status.initialized) {
    elements.statusPill.textContent = "Initialized";
    elements.statusPill.className = "status-pill ready";
    elements.projectBadge.classList.remove("hidden");
    elements.statusText.textContent = `项目路径：${status.root}`;
    elements.initEmptyState.classList.add("hidden");
    elements.projectStatus.classList.remove("hidden");
    elements.scanButton.disabled = false;
  } else {
    elements.statusPill.textContent = "Needs Init";
    elements.statusPill.className = "status-pill empty";
    elements.projectBadge.classList.remove("hidden");
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

function sortByLatest(items) {
  return [...items].sort((a, b) => {
    const bTimestamp = Date.parse(b.updated_at || b.created_at || "");
    const aTimestamp = Date.parse(a.updated_at || a.created_at || "");
    if (!Number.isNaN(aTimestamp) && !Number.isNaN(bTimestamp) && aTimestamp !== bTimestamp) {
      return bTimestamp - aTimestamp;
    }
    const bKey = b.id || b.name || b.updated_at || b.created_at || "";
    const aKey = a.id || a.name || a.updated_at || a.created_at || "";
    return String(bKey).localeCompare(String(aKey));
  });
}

function pageItems(items, page) {
  const start = (page - 1) * ITEMS_PER_PAGE;
  return items.slice(start, start + ITEMS_PER_PAGE);
}

function clampPage(page, totalItems) {
  const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));
  return Math.min(Math.max(1, page), totalPages);
}

function renderPagination(element, totalItems, currentPage, onPageChange) {
  if (!element) return;
  if (totalItems <= ITEMS_PER_PAGE) {
    element.innerHTML = "";
    return;
  }
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
  const start = (currentPage - 1) * ITEMS_PER_PAGE + 1;
  const end = Math.min(currentPage * ITEMS_PER_PAGE, totalItems);
  element.innerHTML = `
    <div class="pagination-summary">显示 ${start}-${end} / ${totalItems}</div>
    <div class="pagination-actions">
      <button type="button" class="button secondary pagination-button" data-page="prev" ${currentPage === 1 ? "disabled" : ""}>上一页</button>
      <span class="pagination-page">${currentPage} / ${totalPages}</span>
      <button type="button" class="button secondary pagination-button" data-page="next" ${currentPage === totalPages ? "disabled" : ""}>下一页</button>
    </div>
  `;
  element.querySelectorAll(".pagination-button").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = button.dataset.page === "prev" ? currentPage - 1 : currentPage + 1;
      onPageChange(nextPage);
    });
  });
}

function renderTasks() {
  const filtered = state.taskFilter === "all"
    ? state.tasks
    : state.tasks.filter((t) => state.taskFilter === "todo" ? t.status !== "done" : t.status === state.taskFilter);
  const sorted = sortByLatest(filtered);
  state.taskPage = clampPage(state.taskPage, sorted.length);
  const visibleTasks = pageItems(sorted, state.taskPage);

  renderTaskFilter();

  if (!sorted.length) {
    elements.taskTableBody.innerHTML = `<tr><td colspan="4">${state.tasks.length ? "当前筛选无匹配任务。" : "暂无任务。"}</td></tr>`;
    renderPagination(elements.taskPagination, 0, 1, () => {});
    return;
  }

  elements.taskTableBody.innerHTML = visibleTasks
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

  renderPagination(elements.taskPagination, sorted.length, state.taskPage, (page) => {
    state.taskPage = page;
    renderTasks();
  });
}

function renderTaskFilter() {
  const counts = { all: state.tasks.length, todo: 0, running: 0, done: 0 };
  for (const t of state.tasks) {
    if (t.status !== "done") counts.todo++;
    if (t.status === "running") counts.running++;
    if (t.status === "done") counts.done++;
  }
  const filters = [
    { key: "all", label: "全部" },
    { key: "todo", label: "未完成" },
    { key: "running", label: "执行中" },
    { key: "done", label: "已完成" },
  ];
  elements.taskFilterBar.innerHTML = filters
    .map((f) => {
      const active = state.taskFilter === f.key ? "filter-active" : "";
      return `<button type="button" class="filter-btn ${active}" data-filter="${f.key}">${f.label} (${counts[f.key]})</button>`;
    })
    .join("");
  elements.taskFilterBar.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.taskFilter = btn.dataset.filter;
      state.taskPage = 1;
      renderTasks();
    });
  });
}

function renderPacks() {
  if (!state.packs.length) {
    elements.packList.innerHTML = `<div class="empty-state compact"><p>还没有生成 Context Pack。</p></div>`;
    renderPagination(elements.packPagination, 0, 1, () => {});
    return;
  }
  const sortedPacks = sortByLatest(state.packs);
  state.packPage = clampPage(state.packPage, sortedPacks.length);
  const visiblePacks = pageItems(sortedPacks, state.packPage);
  elements.packList.innerHTML = visiblePacks
    .map(
      (pack) => `
        <div class="pack-item">
          <div class="pack-name">${pack.display_name || pack.name}</div>
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
        setActivity(`已复制 ${data.pack.display_name || data.pack.name} 的内容。`);
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

  renderPagination(elements.packPagination, sortedPacks.length, state.packPage, (page) => {
    state.packPage = page;
    renderPacks();
  });
}

async function loadTaskInspector() {
  if (!state.selectedTaskId) {
    elements.taskEmpty.classList.remove("hidden");
    elements.taskInspector.classList.add("hidden");
    state.currentExecution = null;
    return;
  }
  const [{ task, execution }, { route }] = await Promise.all([
    api(`/api/tasks/${state.selectedTaskId}`),
    api(`/api/route/${state.selectedTaskId}`),
  ]);
  state.currentExecution = execution;
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
  renderExecution(task, execution);

  const hasPack = state.packs.some((pack) => pack.task_id === task.id);
  elements.copyCurrentPackButton.classList.toggle("hidden", !hasPack);
}

function renderExecution(task, execution) {
  if (!execution) {
    elements.executionCard.innerHTML = `
      <strong>暂无执行记录</strong>
      <div class="muted">点击“开始执行”后会生成执行记录、Context Pack 和交接单。</div>
    `;
    return;
  }
  elements.executionCard.innerHTML = `
    <strong>${execution.execution_id} | ${execution.status}</strong>
    <div class="muted">计划模型：${execution.planned_model || task.recommended_model}</div>
    <div class="muted">实际模型：${execution.actual_model || "-"}</div>
    <div class="muted">Pack：${execution.pack_path || "-"}</div>
    <div class="muted">Handoff：${execution.handoff_path || "-"}</div>
    <div class="muted">开始时间：${execution.started_at || "-"}</div>
    <div class="muted">完成时间：${execution.finished_at || "-"}</div>
    <div class="muted">测试结果：${execution.test_result || "-"}</div>
  `;
}

function renderPlanPreview() {
  const preview = state.planPreview;
  const container = document.getElementById("planPreview");
  if (!preview || !preview.tasks.length) {
    container.classList.add("hidden");
    return;
  }
  container.classList.remove("hidden");
  const list = container.querySelector(".plan-preview-list");
  list.innerHTML = preview.tasks
    .map((task, i) => `<div class="plan-preview-item"><span class="plan-preview-type">${task.type}</span> <strong>${task.title}</strong> <span class="muted">${task.recommended_model}</span></div>`)
    .join("");
}

document.getElementById("planConfirmButton")?.addEventListener("click", async () => {
  const preview = state.planPreview;
  if (!preview) return;
  await runAction(async () => {
    const data = await api("/api/tasks/plan", {
      method: "POST",
      body: JSON.stringify({ goal: preview.goal, priority: preview.priority, confirm: true }),
    });
    state.planPreview = null;
    renderPlanPreview();
    state.selectedTaskId = data.tasks[0]?.id || state.selectedTaskId;
    await refreshDashboard();
    const summary = data.tasks.map((task) => `${task.id} | ${task.recommended_model} | ${task.title}`).join("\n");
    setActivity(`已创建 ${data.tasks.length} 条任务。\n${summary}`);
  }, "确认创建失败。");
});

document.getElementById("planCancelButton")?.addEventListener("click", () => {
  state.planPreview = null;
  renderPlanPreview();
  setActivity("已取消目标拆分。");
});

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
    state.selectedTaskId = sortByLatest(state.tasks)[0].id;
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
    // Preview first, don't create yet
    const data = await api("/api/tasks/plan", { method: "POST", body: JSON.stringify(payload) });
    state.planPreview = { goal: payload.goal, priority: payload.priority, tasks: data.tasks };
    renderPlanPreview();
    setActivity(`预览 ${data.tasks.length} 条拆分任务，确认后才会创建。`);
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

elements.startExecutionButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const task = state.tasks.find((item) => item.id === state.selectedTaskId);
    const data = await api("/api/run/manual", {
      method: "POST",
      body: JSON.stringify({
        task_id: state.selectedTaskId,
        model: task?.recommended_model || "",
        start: true,
      }),
    });
    await refreshDashboard();
    await copyText(data.handoff.content);
    setActivity(`已开始执行 ${data.task.id}。\n模型：${data.execution.planned_model}\n交接单已复制：${data.handoff.handoff_path}`);
  }, "开始执行失败。");
});

elements.completeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const payload = {
      task_id: state.selectedTaskId,
      summary: form.get("summary"),
      actual_model: form.get("actual_model"),
      test_command: form.get("test_command"),
      test_result: form.get("test_result"),
      score: form.get("score") ? Number(form.get("score")) : null,
      score_note: form.get("score_note"),
    };
    const data = await api("/api/complete", { method: "POST", body: JSON.stringify(payload) });
    formElement.reset();
    await refreshDashboard();
    setActivity(`已完成任务 ${data.task.id}。`);
  }, "完成任务失败。");
});

refreshDashboard().catch((error) => {
  setActivity(error.message);
  elements.statusText.textContent = "加载失败，请刷新页面重试。";
});
