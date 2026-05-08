import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import QRCode from "qrcode";
import "./style.css";

const app = document.querySelector("#app");

app.innerHTML = `
  <main class="shell">
    <header>
      <div>
        <p>TagLedger</p>
        <h1>启动器 <span id="version"></span></h1>
      </div>
      <span id="status" class="status stopped">已停止</span>
    </header>

    <section class="url-row">
      <input id="lanUrl" readonly placeholder="服务启动后显示扫码链接" />
      <button id="copyBtn" type="button">复制</button>
    </section>

    <section class="qr-wrap">
      <canvas id="qr" width="260" height="260"></canvas>
      <p id="emptyQr">启动中...</p>
    </section>

    <label id="ipSelectWrap" class="ip-select" hidden>
      局域网 IP
      <select id="ipSelect"></select>
    </label>

    <section class="actions">
      <button id="startBtn" type="button">启动</button>
      <button id="stopBtn" type="button">停止</button>
      <button id="restartBtn" type="button">重启</button>
      <button id="tokenBtn" type="button">重新生成令牌</button>
      <button id="dataBtn" type="button">打开数据目录</button>
      <button id="logBtn" type="button">打开日志目录</button>
    </section>

    <p id="error" class="error" hidden></p>

    <footer>
      <a href="https://github.com/wyl2607/tagledger/releases" target="_blank" rel="noreferrer">GitHub releases</a>
      <span>未签名 beta — 请仅在内网使用</span>
    </footer>
  </main>
`;

const els = {
  version: document.querySelector("#version"),
  status: document.querySelector("#status"),
  lanUrl: document.querySelector("#lanUrl"),
  copyBtn: document.querySelector("#copyBtn"),
  qr: document.querySelector("#qr"),
  emptyQr: document.querySelector("#emptyQr"),
  ipSelectWrap: document.querySelector("#ipSelectWrap"),
  ipSelect: document.querySelector("#ipSelect"),
  startBtn: document.querySelector("#startBtn"),
  stopBtn: document.querySelector("#stopBtn"),
  restartBtn: document.querySelector("#restartBtn"),
  tokenBtn: document.querySelector("#tokenBtn"),
  dataBtn: document.querySelector("#dataBtn"),
  logBtn: document.querySelector("#logBtn"),
  error: document.querySelector("#error"),
};

const labels = {
  stopped: "已停止",
  starting: "启动中",
  running: "运行中",
  error: "错误",
};

let currentState = null;

function setBusy(button, busy) {
  button.disabled = busy;
}

async function render(state) {
  currentState = state;
  els.version.textContent = `v${state.version}`;
  els.status.textContent = labels[state.status] || state.status;
  els.status.className = `status ${state.status}`;
  els.lanUrl.value = state.lan_url || "";
  els.copyBtn.disabled = !state.lan_url;
  els.startBtn.disabled = state.status === "running" || state.status === "starting";
  els.stopBtn.disabled = state.status !== "running";
  els.restartBtn.disabled = state.status === "starting";
  els.tokenBtn.disabled = state.status !== "running";
  els.error.hidden = !state.error;
  els.error.textContent = state.error || "";

  const ctx = els.qr.getContext("2d");
  ctx.clearRect(0, 0, els.qr.width, els.qr.height);
  if (state.lan_url) {
    els.emptyQr.hidden = true;
    await QRCode.toCanvas(els.qr, state.lan_url, {
      width: 260,
      margin: 1,
      color: { dark: "#111827", light: "#ffffff" },
    });
  } else {
    els.emptyQr.hidden = false;
  }
}

async function refresh() {
  await render(await invoke("get_state"));
}

async function loadLanIps() {
  const items = await invoke("list_lan_ips");
  els.ipSelect.innerHTML = "";
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.ip;
    option.textContent = `${item.ip} (${item.name})`;
    els.ipSelect.append(option);
  }
  els.ipSelectWrap.hidden = items.length < 2;
}

async function run(button, command) {
  setBusy(button, true);
  try {
    const result = await invoke(command);
    if (result) await render(result);
  } catch (error) {
    const state = await invoke("get_state");
    state.error = String(error);
    await render(state);
  } finally {
    setBusy(button, false);
  }
}

els.startBtn.addEventListener("click", () => run(els.startBtn, "start_sidecar"));
els.stopBtn.addEventListener("click", () => run(els.stopBtn, "stop_sidecar"));
els.restartBtn.addEventListener("click", () => run(els.restartBtn, "restart_sidecar"));
els.tokenBtn.addEventListener("click", async () => {
  setBusy(els.tokenBtn, true);
  try {
    await invoke("regenerate_pair_token");
    await refresh();
  } catch (error) {
    const state = await invoke("get_state");
    state.error = String(error);
    await render(state);
  } finally {
    setBusy(els.tokenBtn, false);
  }
});
els.dataBtn.addEventListener("click", () => run(els.dataBtn, "open_data_dir"));
els.logBtn.addEventListener("click", () => run(els.logBtn, "open_log_dir"));
els.copyBtn.addEventListener("click", async () => {
  if (currentState?.lan_url) {
    await navigator.clipboard.writeText(currentState.lan_url);
  }
});
els.ipSelect.addEventListener("change", async () => {
  await invoke("select_lan_ip", { ip: els.ipSelect.value });
  await refresh();
});

await listen("sidecar_state_changed", (event) => render(event.payload));
await loadLanIps();
await refresh();
await run(els.startBtn, "start_sidecar");
