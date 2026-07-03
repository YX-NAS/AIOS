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
  scheduler: null,
  planPreview: null,
  sessionSuggestions: [],
  selectedTaskId: null,
  runtimePolicy: null,
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
  metricReady: document.getElementById("metricReady"),
  metricBlocked: document.getElementById("metricBlocked"),
  initEmptyState: document.getElementById("initEmptyState"),
  projectStatus: document.getElementById("projectStatus"),
  runtimePolicyCard: document.getElementById("runtimePolicyCard"),
  runtimePolicyForm: document.getElementById("runtimePolicyForm"),
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
  schedulerCard: document.getElementById("schedulerCard"),
  sessionHistoryCard: document.getElementById("sessionHistoryCard"),
  packList: document.getElementById("packList"),
  activityLog: document.getElementById("activityLog"),
  refreshButton: document.getElementById("refreshButton"),
  taskFilterBar: document.getElementById("taskFilterBar"),
  taskPagination: document.getElementById("taskPagination"),
  packPagination: document.getElementById("packPagination"),
  scanButton: document.getElementById("scanButton"),
  dispatchNextButton: document.getElementById("dispatchNextButton"),
  startExecutionButton: document.getElementById("startExecutionButton"),
  exportCcswitchButton: document.getElementById("exportCcswitchButton"),
  copyCcswitchDeeplinkButton: document.getElementById("copyCcswitchDeeplinkButton"),
  copyCcswitchProviderDeeplinkButton: document.getElementById("copyCcswitchProviderDeeplinkButton"),
  copyCcswitchSessionHandoffButton: document.getElementById("copyCcswitchSessionHandoffButton"),
  runCcswitchBridgeButton: document.getElementById("runCcswitchBridgeButton"),
  copyCcswitchButton: document.getElementById("copyCcswitchButton"),
  copyCurrentPackButton: document.getElementById("copyCurrentPackButton"),
  copyHandoffButton: document.getElementById("copyHandoffButton"),
  sessionAttachForm: document.getElementById("sessionAttachForm"),
  copyResumeCommandButton: document.getElementById("copyResumeCommandButton"),
  openResumeInTerminalButton: document.getElementById("openResumeInTerminalButton"),
  copyHistoryResumeCommandButton: document.getElementById("copyHistoryResumeCommandButton"),
  openHistoryResumeInTerminalButton: document.getElementById("openHistoryResumeInTerminalButton"),
  copyContinueLatestCommandButton: document.getElementById("copyContinueLatestCommandButton"),
  openLatestResumeInTerminalButton: document.getElementById("openLatestResumeInTerminalButton"),
  bridgeConfirmForm: document.getElementById("bridgeConfirmForm"),
  confirmBridgeReadyButton: document.getElementById("confirmBridgeReadyButton"),
  confirmBridgeFailedButton: document.getElementById("confirmBridgeFailedButton"),
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
  state.runtimePolicy = status.runtime_policy || null;
  elements.rootPath.textContent = status.root;
  elements.projectBadge.textContent = projectName;
  elements.metricTasks.textContent = String(status.task_count);
  elements.metricOpen.textContent = String(status.open_tasks);
  elements.metricDone.textContent = String(status.done_tasks);
  elements.metricFiles.textContent = String(status.file_count);
  elements.metricReady.textContent = String(status.ready_count || 0);
  elements.metricBlocked.textContent = String(status.blocked_count || 0);

  if (status.initialized) {
    elements.statusPill.textContent = "Initialized";
    elements.statusPill.className = "status-pill ready";
    elements.projectBadge.classList.remove("hidden");
    elements.statusText.textContent = `项目路径：${status.root} | Provider 握手：${status.provider_handshake_ready_count || 0} 正常 / ${status.provider_handshake_failed_count || 0} 失败`;
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
  renderRuntimePolicy();
}

function renderRuntimePolicy() {
  const policy = state.runtimePolicy;
  if (!elements.runtimePolicyCard || !elements.runtimePolicyForm) return;
  if (!policy) {
    elements.runtimePolicyCard.innerHTML = `<strong>暂无预算策略</strong>`;
    return;
  }
  const currency = policy.cost_currency || "USD";
  elements.runtimePolicyCard.innerHTML = `
    <strong>${policy.dispatch_strategy || "default"}</strong>
    <div class="muted">项目总预算：${policy.max_total_estimated_cost != null ? `${policy.max_total_estimated_cost} ${currency}` : "-"}</div>
    <div class="muted">单次执行上限：${policy.max_single_execution_cost != null ? `${policy.max_single_execution_cost} ${currency}` : "-"}</div>
    <div class="muted">累计已用：${policy.spent_total_estimated_cost != null ? `${policy.spent_total_estimated_cost} ${currency}` : "-"}</div>
    <div class="muted">剩余预算：${policy.remaining_total_budget != null ? `${policy.remaining_total_budget} ${currency}` : "-"}</div>
    <div class="muted">未定价阻塞：${policy.block_on_unpriced_model ? "开启" : "关闭"}</div>
  `;
  elements.runtimePolicyForm.querySelector('input[name="max_total_estimated_cost"]').value = policy.max_total_estimated_cost ?? "";
  elements.runtimePolicyForm.querySelector('input[name="max_single_execution_cost"]').value = policy.max_single_execution_cost ?? "";
  elements.runtimePolicyForm.querySelector('select[name="dispatch_strategy"]').value = policy.dispatch_strategy || "default";
  elements.runtimePolicyForm.querySelector('input[name="block_on_unpriced_model"]').checked = Boolean(policy.block_on_unpriced_model);
  elements.runtimePolicyForm.querySelector('input[name="cost_currency"]').value = policy.cost_currency || "USD";
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
    state.sessionSuggestions = [];
    return;
  }
  const [{ task, execution }, { route }, { sessions }] = await Promise.all([
    api(`/api/tasks/${state.selectedTaskId}`),
    api(`/api/route/${state.selectedTaskId}`),
    api(`/api/run/sessions/${state.selectedTaskId}?limit=5`),
  ]);
  state.currentExecution = execution;
  state.sessionSuggestions = sessions || [];
  elements.taskEmpty.classList.add("hidden");
  elements.taskInspector.classList.remove("hidden");
  elements.taskTitle.textContent = task.title;
  elements.taskMeta.textContent = `${task.id} | ${task.status} | ${task.priority} | ${task.recommended_model}`;
  const dependencyText = (task.depends_on_task_ids || []).length ? ` | 依赖 ${task.depends_on_task_ids.join(", ")}` : "";
  const parentText = task.parent_task_id ? ` | 父任务 ${task.parent_task_id}` : "";
  elements.taskMeta.textContent += `${parentText}${dependencyText}`;
  elements.acceptanceList.innerHTML = task.acceptance_criteria.map((item) => `<li>${item}</li>`).join("");
  elements.routeCard.innerHTML = `
    <strong>${route.recommended_model}</strong>
    <div class="muted">Fallback: ${route.fallback_models.join(", ")}</div>
    <ul class="simple-list">${route.reason.map((item) => `<li>${item}</li>`).join("")}</ul>
  `;
  renderExecution(task, execution);
  renderScheduler(task);
  renderSessionHistory();
  if (elements.sessionAttachForm) {
    const executorInput = elements.sessionAttachForm.querySelector('input[name="executor_id"]');
    if (executorInput && execution?.executor_id) {
      executorInput.value = execution.executor_id;
    }
  }

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
    <div class="muted">执行器：${execution.executor_id || "-"}</div>
    <div class="muted">自动提交：${execution.auto_commit_status || "-"}</div>
    <div class="muted">自动 Push：${execution.auto_push_status || "-"}</div>
    <div class="muted">Draft PR：${execution.auto_pr_status || "-"}</div>
    <div class="muted">最近导出模型：${execution.ccswitch_export_model || "-"}</div>
    <div class="muted">Deep Link 应用：${execution.ccswitch_deeplink_app || "-"}</div>
    <div class="muted">Provider Deep Link：${execution.ccswitch_provider_deeplink ? "已生成" : "-"}</div>
    <div class="muted">Provider：${execution.ccswitch_provider_name || "-"}</div>
    <div class="muted">Pack：${execution.pack_path || "-"}</div>
    <div class="muted">Handoff：${execution.handoff_path || "-"}</div>
    <div class="muted">ccswitch 导出：${execution.ccswitch_export_path || "-"}</div>
    <div class="muted">ccswitch Deep Link：${execution.ccswitch_deeplink ? "已生成" : "-"}</div>
    <div class="muted">Session Handoff：${execution.ccswitch_session_handoff_path || "-"}</div>
    <div class="muted">Bridge：${execution.ccswitch_bridge_path || "-"}</div>
    <div class="muted">Bridge 模式：${execution.ccswitch_bridge_mode || "-"}</div>
    <div class="muted">Bridge 状态：${execution.ccswitch_bridge_status || "-"}</div>
    <div class="muted">Bridge 确认：${execution.ccswitch_bridge_confirmation_status || "-"}</div>
    <div class="muted">Bridge 有效确认：${execution.ccswitch_bridge_effective_confirmation_status || execution.ccswitch_bridge_confirmation_status || "-"}</div>
    <div class="muted">Bridge 确认时间：${execution.ccswitch_bridge_confirmed_at || "-"}</div>
    <div class="muted">Bridge 确认备注：${execution.ccswitch_bridge_confirmation_note || "-"}</div>
    <div class="muted">Bridge 恢复信号：${execution.ccswitch_bridge_resume_signal_status || "-"}</div>
    <div class="muted">Bridge 恢复时间：${execution.ccswitch_bridge_resume_started_at || "-"}</div>
    <div class="muted">Bridge 最后步骤：${execution.ccswitch_bridge_last_step || "-"}</div>
    <div class="muted">Bridge 错误：${execution.ccswitch_bridge_error || "-"}</div>
    <div class="muted">挂接会话：${execution.executor_session_id || execution.executor_session_name || "-"}</div>
    <div class="muted">会话来源：${execution.executor_session_auto_captured ? `自动提取 (${execution.executor_session_capture_source || "-"})` : (execution.executor_session_attached_at ? "手动挂接" : "-")}</div>
    <div class="muted">恢复命令：${execution.executor_resume_command || execution.executor_resume_last_command || "-"}</div>
    <div class="muted">最近恢复模式：${execution.executor_resume_last_mode || "-"}</div>
    <div class="muted">历史恢复来源：${execution.executor_resume_history_session_ref || "-"}</div>
    <div class="muted">历史恢复任务：${execution.executor_resume_history_task_id || "-"} ${execution.executor_resume_history_task_title || ""}</div>
    <div class="muted">继续最近会话：${execution.executor_continue_command || "-"}</div>
    <div class="muted">终端继续：${execution.executor_terminal_launch_status || "-"}</div>
    <div class="muted">终端应用：${execution.executor_terminal_launch_app || "-"}</div>
    <div class="muted">终端继续时间：${execution.executor_terminal_launch_at || "-"}</div>
    <div class="muted">开始时间：${execution.started_at || "-"}</div>
    <div class="muted">完成时间：${execution.finished_at || "-"}</div>
    <div class="muted">执行时长：${execution.duration_seconds != null ? `${Number(execution.duration_seconds).toFixed(2)}s` : "-"}</div>
    <div class="muted">Prompt Token：${execution.prompt_token_estimate || 0}</div>
    <div class="muted">输出 Token：${execution.output_token_estimate || 0}</div>
    <div class="muted">总 Token：${execution.total_token_estimate || 0}</div>
    <div class="muted">估算输入成本：${execution.estimated_input_cost != null ? `${execution.estimated_input_cost} ${execution.cost_currency || "USD"}` : "-"}</div>
    <div class="muted">估算总成本：${execution.estimated_total_cost != null ? `${execution.estimated_total_cost} ${execution.cost_currency || "USD"}` : "-"}</div>
    <div class="muted">测试结果：${execution.test_result || "-"}</div>
    <div class="muted">提交后版本：${execution.git_commit_after || "-"}</div>
    <div class="muted">Push 远端：${execution.auto_push_remote || "-"}</div>
    <div class="muted">PR 链接：${execution.auto_pr_url || "-"}</div>
  `;
}

function renderScheduler(task) {
  const summary = state.scheduler;
  const item = summary?.items?.find((entry) => entry.task_id === task.id);
  if (!item) {
    elements.schedulerCard.innerHTML = `
      <strong>暂无调度信息</strong>
      <div class="muted">任务还没有进入调度视图。</div>
    `;
    return;
  }
  const warnings = (item.pack_warnings || []).length
    ? `<ul class="simple-list">${item.pack_warnings.map((warning) => `<li>${warning}</li>`).join("")}</ul>`
    : `<div class="muted">无额外上下文提示。</div>`;
  elements.schedulerCard.innerHTML = `
    <strong>${item.scheduler_state}</strong>
    <div class="muted">下一步：${item.next_action || "-"}</div>
    <div class="muted">原因：${item.reason || "-"}</div>
    <div class="muted">预算状态：${item.budget?.status || "-"}</div>
    <div class="muted">预计 Prompt Token：${item.budget?.prompt_token_estimate ?? "-"}</div>
    <div class="muted">预计成本：${item.budget?.estimated_total_cost != null ? `${item.budget.estimated_total_cost} ${item.budget.cost_currency || "USD"}` : "-"}</div>
    <div class="muted">剩余项目预算：${item.budget?.remaining_total_budget != null ? `${item.budget.remaining_total_budget} ${item.budget.cost_currency || "USD"}` : "-"}</div>
    <div class="muted">Bridge 确认：${item.bridge_confirmation_status || "-"}</div>
    <div class="muted">Bridge 信号：${item.bridge_resume_signal_status || "-"}</div>
    <div class="muted">Pack 质量：${item.pack_quality || "-"}</div>
    <div class="muted">未满足依赖：${(item.unmet_dependencies || []).join(", ") || "-"}</div>
    ${warnings}
  `;
}

function renderSessionHistory() {
  if (!elements.sessionHistoryCard) return;
  if (!state.sessionSuggestions.length) {
    elements.sessionHistoryCard.innerHTML = `
      <strong>暂无历史会话</strong>
      <div class="muted">执行器一旦挂接或自动提取过会话，这里会出现可复用候选。</div>
    `;
    return;
  }
  elements.sessionHistoryCard.innerHTML = state.sessionSuggestions
    .map((session, index) => `
      <div class="session-candidate">
        <div><strong>${session.session_ref}</strong></div>
        <div class="muted">执行器：${session.executor_id || "-"}</div>
        <div class="muted">来源任务：${session.task_id || "-"} | ${session.task_title || "-"}</div>
        <div class="muted">模型：${session.model || "-"} | 分数：${session.match_score || 0}</div>
        <div class="muted">来源：${session.session_source || "-"} | 时间：${session.attached_at || session.updated_at || "-"}</div>
        <button type="button" class="button secondary wide attach-session-candidate" data-index="${index}">挂接此历史会话</button>
      </div>
    `)
    .join("");
  elements.sessionHistoryCard.querySelectorAll(".attach-session-candidate").forEach((button) => {
    button.addEventListener("click", async () => {
      const candidate = state.sessionSuggestions[Number(button.dataset.index)];
      if (!candidate || !state.selectedTaskId) {
        return;
      }
      await runAction(async () => {
        const data = await api("/api/run/attach", {
          method: "POST",
          body: JSON.stringify({
            task_id: state.selectedTaskId,
            executor_id: candidate.executor_id,
            session_id: candidate.session_id || "",
            session_name: candidate.session_name || "",
            session_note: `复用历史会话：${candidate.task_id || "-"} ${candidate.task_title || ""}`.trim(),
          }),
        });
        await refreshDashboard();
        setActivity(`已挂接历史会话。\n执行器：${data.executor.id}\n会话：${data.session_ref}\n恢复命令：${data.execution.executor_resume_command || "-"}`);
      }, "挂接历史会话失败。");
    });
  });
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
    .map((task) => {
      const depends = (task.depends_on_task_ids || []).length ? ` | 依赖 ${task.depends_on_task_ids.join(", ")}` : "";
      const parent = task.parent_task_id ? ` | 父任务 ${task.parent_task_id}` : "";
      return `<div class="plan-preview-item"><span class="plan-preview-type">${task.type}</span> <strong>${task.title}</strong> <span class="muted">${task.recommended_model}${parent}${depends}</span></div>`;
    })
    .join("");
}

document.getElementById("planConfirmButton")?.addEventListener("click", async () => {
  const preview = state.planPreview;
  if (!preview) return;
  await runAction(async () => {
    const data = await api("/api/tasks/plan", {
      method: "POST",
      body: JSON.stringify({ goal: preview.goal, priority: preview.priority, confirm: true, draft_id: preview.draftId }),
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
  runAction(async () => {
    if (state.planPreview?.draftId) {
      await api(`/api/task-plans/${encodeURIComponent(state.planPreview.draftId)}`, { method: "DELETE" });
    }
    state.planPreview = null;
    renderPlanPreview();
    setActivity("已取消目标拆分。");
  }, "取消拆分草案失败。");
});

async function refreshDashboard() {
  const [statusData, tasksData, packsData, handoffsData, schedulerData] = await Promise.all([
    api("/api/status"),
    api("/api/tasks"),
    api("/api/packs"),
    api("/api/handoffs"),
    api("/api/scheduler"),
  ]);
  state.status = statusData;
  state.tasks = tasksData.tasks;
  state.packs = packsData.packs;
  state.handoffs = handoffsData.handoffs;
  state.scheduler = schedulerData;
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
    state.planPreview = { goal: payload.goal, priority: payload.priority, tasks: data.tasks, draftId: data.draft_id };
    renderPlanPreview();
    setActivity(`已生成拆分草案 ${data.draft_id}，预览 ${data.tasks.length} 条任务，确认后才会创建。`);
  }, "目标拆分失败。");
});

elements.runtimePolicyForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  await runAction(async () => {
    const form = new FormData(formElement);
    const data = await api("/api/runtime-policy", {
      method: "POST",
      body: JSON.stringify({
        max_total_estimated_cost: form.get("max_total_estimated_cost") || null,
        max_single_execution_cost: form.get("max_single_execution_cost") || null,
        dispatch_strategy: form.get("dispatch_strategy"),
        block_on_unpriced_model: form.get("block_on_unpriced_model") === "on",
        cost_currency: form.get("cost_currency") || "USD",
      }),
    });
    state.runtimePolicy = data.policy;
    renderRuntimePolicy();
    await refreshDashboard();
    setActivity(`已更新预算策略。\n调度策略：${data.policy.dispatch_strategy}\n剩余预算：${data.policy.remaining_total_budget ?? "-"} ${data.policy.cost_currency || "USD"}`);
  }, "保存预算策略失败。");
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

elements.dispatchNextButton.addEventListener("click", async () => {
  await runAction(async () => {
    const completeForm = new FormData(elements.completeForm);
    const summary = (completeForm.get("summary") || "").trim();
    const verifyCommand = (completeForm.get("test_command") || "").trim();
    const actualModel = (completeForm.get("actual_model") || "").trim();
    const scoreRaw = completeForm.get("score");
    const scoreNote = (completeForm.get("score_note") || "").trim();
    const autoCommit = completeForm.get("auto_commit") === "on";
    const autoPush = completeForm.get("auto_push") === "on";
    const autoPr = completeForm.get("auto_pr") === "on";
    const autoConfirmBridgeSignal = completeForm.get("auto_confirm_bridge_signal") === "on";
    const retryOnVerifyFail = completeForm.get("retry_on_verify_fail") === "on";
    const data = await api("/api/run/dispatch", {
      method: "POST",
      body: JSON.stringify({
        auto_finish: Boolean(summary),
        summary: summary || null,
        actual_model: actualModel || null,
        verify_command: verifyCommand || null,
        score: scoreRaw ? Number(scoreRaw) : null,
        score_note: scoreNote || null,
        auto_commit: autoCommit,
        auto_push: autoPush,
        auto_pr: autoPr,
        auto_confirm_bridge_signal: autoConfirmBridgeSignal,
        retry_on_verify_fail: retryOnVerifyFail,
      }),
    });
    await refreshDashboard();
    if (!data.progressed) {
      setActivity(`未派发任务：${data.reason}`);
      return;
    }
    state.selectedTaskId = data.task?.id || state.selectedTaskId;
    await loadTaskInspector();
    const gitLine = data.git_commit
      ? (data.git_commit.committed ? `\nGit 提交：${data.git_commit.commit}` : `\nGit 提交跳过：${data.git_commit.reason}`)
      : "";
    const pushLine = data.git_push
      ? (data.git_push.pushed ? `\nGit Push：${data.git_push.remote}/${data.git_push.branch}` : `\nGit Push 跳过：${data.git_push.reason}`)
      : "";
    const prLine = data.git_pr
      ? (data.git_pr.created ? `\nDraft PR：${data.git_pr.url}` : `\nDraft PR 跳过：${data.git_pr.reason}`)
      : "";
    const retryLine = data.auto_retried
      ? `\n自动重试：已从 ${data.retry?.failed_model || "-"} 切到 ${data.retry?.retry_model || data.execution?.planned_model || "-"}`
      : "";
    if (data.auto_finished && !data.dispatched) {
      setActivity(`已自动完成 ${data.task.id}。\n状态：${data.execution.status}${data.verification ? `\n验证：${data.verification.summary}` : ""}${gitLine}${pushLine}${prLine}`);
      return;
    }
    if (data.auto_confirmed_bridge && !data.dispatched) {
      setActivity(`已自动确认 Bridge 恢复信号。\n任务：${data.task.id}\nBridge 确认：${data.execution.ccswitch_bridge_confirmation_status}\n下一步：${data.scheduler_after?.next_action || "-"}`);
      return;
    }
    const verificationLine = data.verification ? `\n验证：${data.verification.summary}` : "";
    const finishLine = data.auto_finished ? "\n任务已自动完成并回写。" : "";
    const previousVerificationLine = data.previous_verification ? `\n上一次验证：${data.previous_verification.summary}` : "";
    setActivity(`已自动派发 ${data.task.id}。\n执行器：${data.executor.id}\n模型：${data.execution.planned_model}\n状态：${data.execution.status}${verificationLine}${previousVerificationLine}${retryLine}${finishLine}${gitLine}${pushLine}${prLine}`);
  }, "自动派发下一任务失败。");
});

elements.exportCcswitchButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/ccswitch/export", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId }),
    });
    await refreshDashboard();
    setActivity(`已导出 ccswitch 适配文件：${data.export_path}\n导出模型：${data.payload.export_model}`);
  }, "导出 ccswitch 适配文件失败。");
});

elements.copyCcswitchDeeplinkButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/ccswitch/deeplink", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, app: "codex" }),
    });
    await copyText(data.deeplink);
    await refreshDashboard();
    setActivity(`已复制 ccswitch Deep Link。\n目标应用：${data.app}`);
  }, "复制 ccswitch Deep Link 失败。");
});

elements.copyCcswitchProviderDeeplinkButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/ccswitch/provider-deeplink", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, app: "codex" }),
    });
    await copyText(data.deeplink);
    await refreshDashboard();
    setActivity(`已复制 Provider Deep Link。\n目标应用：${data.app}\nProvider：${data.provider}\n模型：${data.model}`);
  }, "复制 Provider Deep Link 失败。");
});

elements.copyCcswitchSessionHandoffButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/ccswitch/session-handoff", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, app: "codex" }),
    });
    await copyText(JSON.stringify(data.handoff, null, 2));
    await refreshDashboard();
    setActivity(`已复制 Session Handoff。\n文件：${data.handoff_path}\n模型：${data.handoff.model}`);
  }, "复制 Session Handoff 失败。");
});

elements.runCcswitchBridgeButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/ccswitch/bridge", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, app: "codex", open: true }),
    });
    await refreshDashboard();
    const stepSummary = (data.bridge.steps || []).map((step) => `${step.label}:${step.status}`).join(" | ");
    const errorLine = data.bridge.bridge_error ? `\n错误：${data.bridge.bridge_error}` : "";
    setActivity(`已启动桥接执行。\n文件：${data.bridge_path}\n模式：${data.bridge.bridge_mode}\n状态：${data.bridge.bridge_status}\n步骤：${stepSummary}${errorLine}`);
  }, "启动 ccswitch 桥接执行失败。");
});

async function confirmBridge(status) {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const note = String(new FormData(elements.bridgeConfirmForm).get("confirmation_note") || "").trim();
    const data = await api("/api/ccswitch/confirm", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, status, note }),
    });
    await refreshDashboard();
    setActivity(`已确认桥接结果。\n状态：${data.bridge.bridge_confirmation_status}\n备注：${data.bridge.bridge_confirmation_note || "-"}`);
  }, "确认 bridge 状态失败。");
}

elements.confirmBridgeReadyButton.addEventListener("click", async () => {
  await confirmBridge("confirmed_ready");
});

elements.confirmBridgeFailedButton.addEventListener("click", async () => {
  await confirmBridge("confirmed_failed");
});

elements.sessionAttachForm.addEventListener("submit", async (event) => {
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
      executor_id: String(form.get("executor_id") || "").trim(),
      session_id: String(form.get("session_id") || "").trim(),
      session_name: String(form.get("session_name") || "").trim(),
      session_note: String(form.get("session_note") || "").trim(),
    };
    const data = await api("/api/run/attach", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshDashboard();
    setActivity(`已挂接会话。\n执行器：${data.executor.id}\n会话：${data.session_ref}\n恢复命令：${data.execution.executor_resume_command || "-"}`);
  }, "挂接当前会话失败。");
});

elements.copyResumeCommandButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/run/resume", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, latest: false }),
    });
    await copyText(data.command);
    await refreshDashboard();
    setActivity(`已复制恢复命令。\n模式：${data.mode}\n执行器：${data.executor.id}\n命令：${data.command}`);
  }, "复制恢复命令失败。");
});

elements.copyHistoryResumeCommandButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/run/resume", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, latest: false, history_fallback: true }),
    });
    await copyText(data.command);
    await refreshDashboard();
    setActivity(`已复制历史候选恢复命令。\n模式：${data.mode}\n执行器：${data.executor.id}\n会话：${data.session_ref || "-"}\n命令：${data.command}`);
  }, "复制历史候选恢复命令失败。");
});

elements.copyContinueLatestCommandButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/run/resume", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, latest: true }),
    });
    await copyText(data.command);
    await refreshDashboard();
    setActivity(`已复制最近会话继续命令。\n执行器：${data.executor.id}\n命令：${data.command}`);
  }, "复制最近会话继续命令失败。");
});

elements.openResumeInTerminalButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/run/resume", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, latest: false, open_terminal: true }),
    });
    await refreshDashboard();
    setActivity(`已在终端打开恢复命令。\n模式：${data.mode}\n终端：${data.terminal.app}\n命令：${data.command}`);
  }, "在终端打开恢复命令失败。");
});

elements.openHistoryResumeInTerminalButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/run/resume", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, latest: false, history_fallback: true, open_terminal: true }),
    });
    await refreshDashboard();
    setActivity(`已在终端打开历史候选恢复命令。\n模式：${data.mode}\n终端：${data.terminal.app}\n会话：${data.session_ref || "-"}\n命令：${data.command}`);
  }, "在终端打开历史候选恢复命令失败。");
});

elements.openLatestResumeInTerminalButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/run/resume", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId, latest: true, open_terminal: true }),
    });
    await refreshDashboard();
    setActivity(`已在终端打开最近会话继续命令。\n终端：${data.terminal.app}\n命令：${data.command}`);
  }, "在终端打开最近会话继续命令失败。");
});

elements.copyCcswitchButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) {
    setActivity("请先选择任务。");
    return;
  }
  await runAction(async () => {
    const data = await api("/api/ccswitch/export", {
      method: "POST",
      body: JSON.stringify({ task_id: state.selectedTaskId }),
    });
    await copyText(JSON.stringify(data.payload, null, 2));
    await refreshDashboard();
    setActivity(`已复制 ccswitch JSON：${data.payload.export_model}`);
  }, "复制 ccswitch JSON 失败。");
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
      auto_commit: form.get("auto_commit") === "on",
      auto_push: form.get("auto_push") === "on",
      auto_pr: form.get("auto_pr") === "on",
    };
    const data = await api("/api/complete", { method: "POST", body: JSON.stringify(payload) });
    formElement.reset();
    await refreshDashboard();
    const gitLine = data.git_commit
      ? (data.git_commit.committed ? `\nGit 提交：${data.git_commit.commit}` : `\nGit 提交跳过：${data.git_commit.reason}`)
      : "";
    const pushLine = data.git_push
      ? (data.git_push.pushed ? `\nGit Push：${data.git_push.remote}/${data.git_push.branch}` : `\nGit Push 跳过：${data.git_push.reason}`)
      : "";
    const prLine = data.git_pr
      ? (data.git_pr.created ? `\nDraft PR：${data.git_pr.url}` : `\nDraft PR 跳过：${data.git_pr.reason}`)
      : "";
    setActivity(`已完成任务 ${data.task.id}。${gitLine}${pushLine}${prLine}`);
  }, "完成任务失败。");
});

refreshDashboard().catch((error) => {
  setActivity(error.message);
  elements.statusText.textContent = "加载失败，请刷新页面重试。";
});
