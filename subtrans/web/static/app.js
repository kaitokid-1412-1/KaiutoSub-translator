// SubTrans Auto Frontend Application Logic

(function () {
  let authToken = "";

  // 1. Extract Token from URL or Cookie
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has("token")) {
    authToken = urlParams.get("token");
  } else {
    const cookies = document.cookie.split(";");
    for (let c of cookies) {
      const [k, v] = c.trim().split("=");
      if (k === "subtrans_token") {
        authToken = v;
        break;
      }
    }
  }

  function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (authToken) {
      options.headers["X-SubTrans-Token"] = authToken;
    }
    return fetch(url, options);
  }

  // 2. Tab Navigation
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });

  // 3. UI Element References
  const inputPath = document.getElementById("input-path");
  const btnBrowse = document.getElementById("btn-browse");
  const btnScan = document.getElementById("btn-scan");
  const scanSummary = document.getElementById("scan-summary");
  const scanCountText = document.getElementById("scan-count-text");
  const scannedTableBody = document.querySelector("#scanned-files-table tbody");

  const btnStart = document.getElementById("btn-start");
  const btnPause = document.getElementById("btn-pause");
  const btnResume = document.getElementById("btn-resume");
  const btnEstimate = document.getElementById("btn-estimate");
  const estimateResult = document.getElementById("estimate-result");

  const jobStatusPill = document.getElementById("job-status-pill");
  const globalProgressBar = document.getElementById("global-progress-bar");
  const progressPercent = document.getElementById("progress-percent");
  const progressDetail = document.getElementById("progress-detail");
  const queueTbody = document.getElementById("queue-tbody");
  const logConsole = document.getElementById("log-console");
  const btnClearLogs = document.getElementById("btn-clear-logs");

  const connectionIndicator = document.querySelector(".status-indicator");
  const gatewayStatusText = document.getElementById("gateway-status-text");

  // Settings elements
  const cfgBaseUrl = document.getElementById("cfg-base-url");
  const cfgApiKey = document.getElementById("cfg-api-key");
  const cfgModel = document.getElementById("cfg-model");
  const cfgModelSelect = document.getElementById("cfg-model-select");
  const btnFetchModels = document.getElementById("btn-fetch-models");
  const btnTestConn = document.getElementById("btn-test-conn");
  const cfgTone = document.getElementById("cfg-tone");
  const cfgBidi = document.getElementById("cfg-bidi");
  const cfgBatchLines = document.getElementById("cfg-batch-lines");
  const cfgOverwrite = document.getElementById("cfg-overwrite");
  const cfgCustomPrompt = document.getElementById("cfg-custom-prompt");
  const cfgOcrEngine = document.getElementById("cfg-ocr-engine");
  const cfgOcrMode = document.getElementById("cfg-ocr-mode");
  const cfgOcrEnabled = document.getElementById("cfg-ocr-enabled");
  const cfgGlossaryTerms = document.getElementById("cfg-glossary-terms");
  const cfgGlossaryKeep = document.getElementById("cfg-glossary-keep");
  const cfgSeriesSynopsis = document.getElementById("cfg-series-synopsis");
  const settingsForm = document.getElementById("settings-form");
  const saveSettingsMsg = document.getElementById("save-settings-msg");

  // 4. Log Console Helper
  function appendLog(line) {
    const el = document.createElement("div");
    el.className = "log-line";
    el.textContent = line;
    logConsole.appendChild(el);
    logConsole.scrollTop = logConsole.scrollHeight;
  }

  btnClearLogs.addEventListener("click", () => {
    logConsole.innerHTML = "";
  });

  // 5. Load Settings
  async function loadSettings() {
    try {
      const res = await apiFetch("/api/config");
      if (res.ok) {
        const data = await res.json();
        cfgBaseUrl.value = data.provider?.base_url || "";
        cfgApiKey.value = data.provider?.api_key || "";
        cfgModel.value = data.provider?.model || "";
        cfgTone.value = data.translate?.tone_preset || "movie_tv";
        cfgBidi.value = data.persian?.bidi_mode || "rle";
        cfgBatchLines.value = data.translate?.batch_lines || 30;
        cfgOverwrite.checked = !!data.general?.overwrite_existing;
        cfgCustomPrompt.value = data.translate?.custom_prompt || "";
        cfgOcrEngine.value = data.ocr?.engine || "paddleocr";
        cfgOcrMode.value = (data.ocr?.use_gpu !== false) ? "gpu" : "cpu";
        cfgOcrEnabled.checked = data.ocr?.enabled !== false;
      }
    } catch (e) {
      console.error("Error loading settings:", e);
    }
  }

  settingsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const updated = {
      provider: {
        base_url: cfgBaseUrl.value.trim(),
        api_key: cfgApiKey.value.trim(),
        model: cfgModel.value.trim(),
      },
      translate: {
        tone_preset: cfgTone.value,
        batch_lines: parseInt(cfgBatchLines.value, 10) || 30,
        custom_prompt: cfgCustomPrompt.value.trim() || null,
      },
      persian: {
        bidi_mode: cfgBidi.value,
      },
      ocr: {
        enabled: cfgOcrEnabled.checked,
        engine: cfgOcrEngine.value,
        use_gpu: cfgOcrMode.value === "gpu",
      },
      general: {
        overwrite_existing: cfgOverwrite.checked,
      },
    };

    try {
      const res = await apiFetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updated),
      });
      if (res.ok) {
        saveSettingsMsg.classList.remove("hidden");
        setTimeout(() => saveSettingsMsg.classList.add("hidden"), 3000);
      }
    } catch (e) {
      alert("خطا در ذخیره تنظیمات: " + e.message);
    }
  });

  // 6. Test Gateway Connection
  async function testGateway() {
    gatewayStatusText.textContent = "در حال بررسی...";
    try {
      const res = await apiFetch("/api/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: cfgBaseUrl.value.trim(),
          api_key: cfgApiKey.value.trim(),
        }),
      });
      const data = await res.json();
      if (data.ok) {
        connectionIndicator.className = "status-indicator online";
        gatewayStatusText.textContent = "اتصال برقرار است";
      } else {
        connectionIndicator.className = "status-indicator offline";
        gatewayStatusText.textContent = "خطا در اتصال به گیت‌وی";
      }
    } catch (e) {
      connectionIndicator.className = "status-indicator offline";
      gatewayStatusText.textContent = "عدم دسترسی به سرور";
    }
  }

  btnTestConn.addEventListener("click", async () => {
    await testGateway();
    alert(gatewayStatusText.textContent);
  });

  // 7. Fetch Models
  btnFetchModels.addEventListener("click", async () => {
    btnFetchModels.disabled = true;
    btnFetchModels.textContent = "در حال دریافت...";
    try {
      const res = await apiFetch("/api/fetch-models", { method: "POST" });
      const data = await res.json();
      if (data.models && data.models.length > 0) {
        cfgModelSelect.innerHTML = "";
        data.models.forEach((m) => {
          const opt = document.createElement("option");
          opt.value = m;
          opt.textContent = m;
          cfgModelSelect.appendChild(opt);
        });
        cfgModelSelect.classList.remove("hidden");
        cfgModelSelect.addEventListener("change", () => {
          cfgModel.value = cfgModelSelect.value;
        });
        if (!cfgModel.value) {
          cfgModel.value = data.models[0];
        }
      } else {
        alert("هیچ مدلی یافت نشد.");
      }
    } catch (e) {
      alert("خطا در دریافت مدل‌ها: " + e.message);
    } finally {
      btnFetchModels.disabled = false;
      btnFetchModels.textContent = "دریافت مدل‌ها";
    }
  });

  // 8. Folder Picker Dialog
  btnBrowse.addEventListener("click", async () => {
    btnBrowse.disabled = true;
    try {
      const res = await apiFetch("/api/pick-folder", { method: "POST" });
      const data = await res.json();
      if (data.path) {
        inputPath.value = data.path;
        await scanFolder();
      }
    } catch (e) {
      console.error(e);
    } finally {
      btnBrowse.disabled = false;
    }
  });

  // 9. Scan Folder
  async function scanFolder() {
    const p = inputPath.value.trim();
    if (!p) return;
    btnScan.disabled = true;
    btnScan.textContent = "در حال اسکن...";
    try {
      const res = await apiFetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p }),
      });
      if (res.ok) {
        const data = await res.json();
        scanCountText.textContent = `${data.count} فایل ویدیویی یا زیرنویس پیدا شد:`;
        scannedTableBody.innerHTML = "";
        data.files.forEach((f) => {
          const row = document.createElement("tr");
          const trackInfo = f.tracks && f.tracks.length > 0
            ? f.tracks.map((t) => `ترک ${t.index} (${t.codec}, ${t.lang})`).join(" | ")
            : (f.is_video ? "بدون ترک داخلی" : "فایل زیرنویس خارجی");

          row.innerHTML = `
            <td>${f.name}</td>
            <td>${f.is_video ? "ویدیو" : "زیرنویس"}</td>
            <td>${trackInfo}</td>
          `;
          scannedTableBody.appendChild(row);
        });
        scanSummary.classList.remove("hidden");
      } else {
        const err = await res.json();
        alert(err.detail || "خطا در اسکن مسیر");
      }
    } catch (e) {
      alert("خطا در اسکن: " + e.message);
    } finally {
      btnScan.disabled = false;
      btnScan.textContent = "اسکن فایل‌ها";
    }
  }

  btnScan.addEventListener("click", scanFolder);

  // 10. Estimate Dry Run
  btnEstimate.addEventListener("click", async () => {
    const p = inputPath.value.trim();
    if (!p) {
      alert("لطفاً ابتدا مسیر را انتخاب کنید.");
      return;
    }
    btnEstimate.disabled = true;
    try {
      const res = await apiFetch("/api/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p }),
      });
      if (res.ok) {
        const data = await res.json();
        estimateResult.textContent = `تخمین: ${data.message} | تخمین تقریبی تعداد درخواست‌های API: حدود ${data.estimated_calls}`;
        estimateResult.classList.remove("hidden");
      }
    } catch (e) {
      alert("خطا در تخمین: " + e.message);
    } finally {
      btnEstimate.disabled = false;
    }
  });

  // 11. Pipeline Job Controls
  btnStart.addEventListener("click", async () => {
    const p = inputPath.value.trim();
    if (!p) {
      alert("لطفاً مسیر ورودی را وارد یا انتخاب کنید.");
      return;
    }
    btnStart.disabled = true;
    btnPause.disabled = false;
    btnResume.disabled = true;
    try {
      const res = await apiFetch("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p }),
      });
      if (res.ok) {
        appendLog("فرمان شروع ارسال شد.");
      }
    } catch (e) {
      alert("خطا در شروع: " + e.message);
      btnStart.disabled = false;
    }
  });

  btnPause.addEventListener("click", async () => {
    btnPause.disabled = true;
    await apiFetch("/api/pause", { method: "POST" });
    btnResume.disabled = false;
  });

  btnResume.addEventListener("click", async () => {
    btnResume.disabled = true;
    await apiFetch("/api/resume", { method: "POST" });
    btnPause.disabled = false;
  });

  // 12. Queue Table Rendering
  function renderQueue(tasks) {
    if (!tasks || tasks.length === 0) return;
    queueTbody.innerHTML = "";
    let completedCount = 0;

    tasks.forEach((t) => {
      const row = document.createElement("tr");

      function makePill(status) {
        const s = status || "pending";
        return `<span class="pill pill-${s}">${s}</span>`;
      }

      const isDone = t.stages?.write === "success" || t.stages?.translate === "success";
      if (isDone) completedCount++;

      const lastMsg = t.error || Object.values(t.messages || {}).pop() || "در صف";

      row.innerHTML = `
        <td><strong>${t.name}</strong></td>
        <td>${makePill(t.stages?.extract)}</td>
        <td>${makePill(t.stages?.ocr)}</td>
        <td>${makePill(t.stages?.context)}</td>
        <td>${makePill(t.stages?.translate)}</td>
        <td>${makePill(t.stages?.qc)}</td>
        <td>${makePill(t.stages?.write)}</td>
        <td><small>${lastMsg}</small></td>
      `;
      queueTbody.appendChild(row);
    });

    const percent = Math.round((completedCount / tasks.length) * 100);
    globalProgressBar.style.width = percent + "%";
    progressPercent.textContent = percent + "٪";
    progressDetail.textContent = `${completedCount} از ${tasks.length} فایل تکمیل شد`;
  }

  // 13. Status Polling & SSE Real-time Updates
  function updateJobStatus(data) {
    if (!data) return;
    const status = data.status || "IDLE";
    jobStatusPill.className = `badge badge-${status.toLowerCase()}`;
    jobStatusPill.textContent = `وضعیت: ${status}`;

    if (status === "RUNNING") {
      btnStart.disabled = true;
      btnPause.disabled = false;
      btnResume.disabled = true;
    } else if (status === "PAUSED") {
      btnStart.disabled = true;
      btnPause.disabled = true;
      btnResume.disabled = false;
    } else {
      btnStart.disabled = false;
      btnPause.disabled = true;
      btnResume.disabled = true;
    }

    if (data.tasks) {
      renderQueue(data.tasks);
    }
  }

  async function pollStatus() {
    try {
      const res = await apiFetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        updateJobStatus(data);
      }
    } catch (e) {}
  }

  function initSSE() {
    const sseUrl = `/api/events${authToken ? "?token=" + authToken : ""}`;
    const evtSource = new EventSource(sseUrl);

    evtSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "init") {
          pollStatus();
        } else if (payload.type === "task_update") {
          pollStatus();
        } else if (payload.type === "job_completed" || payload.type === "job_failed") {
          pollStatus();
        }
      } catch (e) {}
    };

    evtSource.onerror = () => {
      evtSource.close();
      // Fallback: poll every 2s
      setInterval(pollStatus, 2000);
    };
  }

  // Initial Boot
  loadSettings();
  testGateway();
  pollStatus();
  initSSE();
})();

