from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parent
HTML_TEMPLATE = ROOT / "demo.html"
ARTIFACTS_DIR = ROOT / "artifacts"
RUNS_DIR = ROOT / "runs"
TRANSCRIPTS_DIR = ROOT / "transcripts"
DATA_DIR = ROOT / "data"


st.set_page_config(page_title="Research Agent Demo", layout="wide", initial_sidebar_state="expanded")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


def list_json(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def latest(paths: list[Path]) -> Path | None:
    return paths[0] if paths else None


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def safe_json_text(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return text.replace("</", "<\\/")


def load_demo_template() -> str:
    html = read_text(HTML_TEMPLATE)
    if not html:
        raise FileNotFoundError(f"Missing template: {HTML_TEMPLATE}")
    return html


def select_run_payload(selected_name: str | None) -> dict[str, Any] | None:
    if not selected_name:
        return None
    path = RUNS_DIR / selected_name
    return read_json(path, default=None)


def select_transcript_payload(selected_name: str | None) -> dict[str, Any] | None:
    if not selected_name:
        return None
    path = TRANSCRIPTS_DIR / selected_name
    return read_json(path, default=None)


def build_run_meta(version_rows: list[dict[str, str]], selected_run: dict[str, Any] | None, run_files: list[Path], transcript_files: list[Path]) -> dict[str, dict[str, Any]]:
    metas: dict[str, dict[str, Any]] = {}

    for row in version_rows:
        version = row.get("version", "")
        if not version:
            continue
        metas.setdefault(version, {
            "runId": "",
            "artifact": row.get("artifact_version", ""),
            "promptHash": row.get("prompt_hash", ""),
            "toolsHash": row.get("tools_hash", ""),
            "provider": "",
            "model": "",
            "generatedAt": "",
            "phaseSuite": "",
            "transcript": "",
        })

    for path in run_files:
        payload = read_json(path, default=None) or {}
        version = str(payload.get("version") or "").strip()
        if not version:
            continue
        metas[version] = {
            "runId": payload.get("run_id", path.stem),
            "artifact": payload.get("artifact_version", ""),
            "promptHash": payload.get("prompt_hash", ""),
            "toolsHash": payload.get("tools_hash", ""),
            "provider": payload.get("provider", ""),
            "model": payload.get("model", ""),
            "generatedAt": payload.get("generated_at", ""),
            "phaseSuite": f"{payload.get('phase', '')} / {payload.get('suite', '')}".strip(" /"),
            "transcript": "",
        }

    transcript_by_version: dict[str, str] = {}
    for path in transcript_files:
        payload = read_json(path, default=None) or {}
        version = str(payload.get("version") or "").strip()
        if version and version not in transcript_by_version:
            transcript_by_version[version] = path.name

    for version, meta in metas.items():
        meta["transcript"] = transcript_by_version.get(version, meta.get("transcript", ""))

    if selected_run:
        version = str(selected_run.get("version") or "").strip()
        if version:
            metas[version] = {
                "runId": selected_run.get("run_id", ""),
                "artifact": selected_run.get("artifact_version", ""),
                "promptHash": selected_run.get("prompt_hash", ""),
                "toolsHash": selected_run.get("tools_hash", ""),
                "provider": selected_run.get("provider", ""),
                "model": selected_run.get("model", ""),
                "generatedAt": selected_run.get("generated_at", ""),
                "phaseSuite": f"{selected_run.get('phase', '')} / {selected_run.get('suite', '')}".strip(" /"),
                "transcript": transcript_by_version.get(version, ""),
            }
    return metas


def choose_version(version_rows: list[dict[str, str]], run_payload: dict[str, Any] | None) -> str:
    if run_payload and run_payload.get("version"):
        return str(run_payload["version"])
    if version_rows:
        return str(version_rows[-1].get("version") or "v0")
    return "v0"


def derive_metrics(run_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    summary = (run_payload or {}).get("summary", {})
    version = str((run_payload or {}).get("version") or "v0")
    return [{
        "v": version,
        "case": float(summary.get("case_accuracy") or 0.0),
        "routing": float(summary.get("tool_routing_accuracy") or 0.0),
        "args": float(summary.get("argument_accuracy") or 0.0),
        "multiturn": float(summary.get("multiturn_accuracy") or 0.0),
        "errors": int(summary.get("provider_error_cases") or 0),
        "note": f"Selected run {run_payload.get('run_id', '') if run_payload else ''} from actual run JSON.",
    }]


def case_text(item: dict[str, Any]) -> str:
    return str(item.get("query") or item.get("input") or "")


def derive_scenarios(run_payload: dict[str, Any] | None, transcript_payload: dict[str, Any] | None, eval_group: dict[str, Any]) -> dict[str, Any]:
    scenarios: dict[str, Any] = {}
    results = (run_payload or {}).get("results", [])

    def build_from_result(result_item: dict[str, Any], fallback_title: str, fallback_user: str) -> dict[str, Any]:
        result = result_item.get("result", {})
        calls = result.get("actual_tool_calls") or []
        trace = []
        for index, call in enumerate(calls, start=1):
            trace.append({
                "round": index,
                "tool": call.get("name", "tool"),
                "status": "success" if result.get("passed", True) else "error",
                "duration": "1.0s",
                "args": call.get("args", {}),
                "result": "; ".join(result.get("failures") or []) or "ok",
                "desc": str(result_item.get("metadata", {}).get("what_it_tests", "")),
            })
        assistant_text = result.get("actual_text") or result.get("text") or f"Scenario for {fallback_title}"
        return {
            "user": fallback_user,
            "assistant": assistant_text,
            "trace": trace,
        }

    passing = next((item for item in results if item.get("result", {}).get("passed") and item.get("result", {}).get("actual_tool_calls")), None)
    missing = next((item for item in results if item.get("result", {}).get("failure_type") == "missing_info"), None)
    confirm = next((item for item in results if item.get("result", {}).get("actual_tool_calls") and any(call.get("name") == "clarify" for call in item["result"].get("actual_tool_calls", []))), None)
    error = next((item for item in results if item.get("result", {}).get("failure_type") == "provider_error" or any("error" in str(ev.get("result", {})).lower() for ev in item.get("tool_results", []))), None)

    if passing:
        scenarios["normal"] = build_from_result(passing, "normal", case_text(passing))
    if missing:
        scenarios["missing"] = build_from_result(missing, "missing", case_text(missing))
    if confirm:
        scenarios["confirm"] = build_from_result(confirm, "confirm", case_text(confirm))
    if error:
        scenarios["error"] = build_from_result(error, "error", case_text(error))

    if not scenarios and transcript_payload:
        turns = transcript_payload.get("turns", [])
        if turns:
            first = turns[0]
            scenarios["normal"] = {
                "user": first.get("user", ""),
                "assistant": first.get("assistant_text") or "No response available.",
                "trace": [],
            }

    group_cases = eval_group.get("cases", [])
    scenario_labels = {
        "normal": (group_cases[0].get("query") if group_cases else "Tìm tin AI hôm nay và tóm tắt 5 ý chính."),
        "missing": (group_cases[10].get("turns", [{}])[0].get("content") if len(group_cases) > 10 and group_cases[10].get("turns") else "Tóm tắt bài viết này giúp mình."),
        "confirm": "Gửi bản tổng hợp này lên Telegram giúp mình.",
        "error": "Trigger lỗi tool (demo).",
    }

    return {"scenarios": scenarios, "scenario_labels": scenario_labels}


def build_demo_data() -> dict[str, Any]:
    run_files = list_json(RUNS_DIR)
    transcript_files = list_json(TRANSCRIPTS_DIR)
    version_rows = csv_rows(ARTIFACTS_DIR / "version_log.csv")
    eval_group = read_json(DATA_DIR / "eval_group.json", default={}) or {}

    selected_run_path = latest(run_files)
    selected_transcript_path = latest(transcript_files)
    selected_run = read_json(selected_run_path, default=None) if selected_run_path else None
    selected_transcript = read_json(selected_transcript_path, default=None) if selected_transcript_path else None

    run_meta = build_run_meta(version_rows, selected_run, run_files, transcript_files)
    metrics = []
    if selected_run:
        metrics = derive_metrics(selected_run)
    else:
        metrics = [{"v": "v0", "case": 0.0, "routing": 0.0, "args": 0.0, "multiturn": 0.0, "errors": 0, "note": "No run JSON available yet."}]

    scenario_bundle = derive_scenarios(selected_run, selected_transcript, eval_group)

    return {
        "provider": (selected_run or {}).get("provider", "local"),
        "model": (selected_run or {}).get("model", "demo"),
        "selected_version": choose_version(version_rows, selected_run),
        "run_meta": run_meta,
        "metrics": metrics,
        "scenarios": scenario_bundle["scenarios"],
        "scenario_labels": scenario_bundle["scenario_labels"],
        "welcome_message": "Chào bạn. Mình là research agent. Chạy một scenario ở tab Chat để xem trace thật.",
    }


def build_runtime_script(data: dict[str, Any]) -> str:
    data_json = safe_json_text(data)
    return f"""
<script>
const DEMO_DATA = {data_json};
const RUN_META = DEMO_DATA.run_meta || {{}};
const METRICS = DEMO_DATA.metrics || [];
const SCENARIOS = DEMO_DATA.scenarios || {{}};
const INITIAL_VERSION = DEMO_DATA.selected_version || Object.keys(RUN_META)[0] || 'v0';

let state = {{ trace: [], round: 0, busy: false }};
const stream = document.getElementById('chatStream');

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}

function scrollBottom() {{ stream.scrollTop = stream.scrollHeight; }}
function setBusy(b) {{
  state.busy = b;
  document.getElementById('sendBtn').disabled = b;
  document.getElementById('composerInput').disabled = b;
  document.querySelectorAll('.scenario-btn').forEach(btn => btn.disabled = b);
}}
function addUserMsg(text) {{
  const row = document.createElement('div');
  row.className = 'msg-row user';
  row.innerHTML = `<div class="bubble">${{escapeHtml(text)}}</div><div class="avatar user">U</div>`;
  stream.appendChild(row); scrollBottom();
}}
function addAgentMsg(text) {{
  const row = document.createElement('div');
  row.className = 'msg-row agent';
  row.innerHTML = `<div class="avatar agent">A</div><div class="bubble">${{text}}</div>`;
  stream.appendChild(row); scrollBottom();
}}
function addTyping() {{
  const row = document.createElement('div');
  row.className = 'msg-row agent'; row.id = 'typingRow';
  row.innerHTML = `<div class="avatar agent">A</div><div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
  stream.appendChild(row); scrollBottom();
}}
function removeTyping() {{ const r = document.getElementById('typingRow'); if (r) r.remove(); }}

function addToolCard(tool, args, status, resultText, duration) {{
  const row = document.createElement('div');
  row.className = 'msg-row agent';
  const id = 'tool-' + Math.random().toString(36).slice(2, 8);
  row.innerHTML = `
    <div style="width:26px;flex-shrink:0;"></div>
    <div class="tool-card" id="${{id}}">
      <div class="tool-card-head">
        <span class="tool-name">${{tool}}</span>
        <span class="badge running" data-role="badge">running</span>
        <span class="tool-meta" data-role="meta">round ${{state.round}}</span>
      </div>
      <details class="mini" open><summary>arguments</summary>
        <pre class="code">${{escapeHtml(JSON.stringify(args, null, 2))}}</pre>
      </details>
      <details class="mini" data-role="result-wrap"><summary>result</summary>
        <pre class="code" data-role="result"></pre>
      </details>
    </div>`;
  stream.appendChild(row); scrollBottom();
  return id;
}}
function resolveToolCard(id, status, resultText, duration) {{
  const card = document.getElementById(id);
  if (!card) return;
  const badge = card.querySelector('[data-role="badge"]');
  badge.className = 'badge ' + status;
  badge.textContent = status;
  card.querySelector('[data-role="meta"]').textContent = `round ${{state.round}} · ${{duration || ''}}`;
  card.querySelector('[data-role="result"]').textContent = resultText || '';
}}

function pushTrace(entry) {{
  state.trace.push(entry);
  document.getElementById('traceCount').textContent = state.trace.length;
}}
function resetTrace() {{
  state.trace = [];
  state.round = 0;
  document.getElementById('traceCount').textContent = 0;
  document.getElementById('traceContent').innerHTML = `<div class="empty-state"><div class="glyph">⎋</div>Chưa có tool call nào. Chạy một scenario ở tab Chat để xem trace tại đây.</div>`;
}}
function renderTraceView() {{
  const el = document.getElementById('traceContent');
  if (state.trace.length === 0) {{ resetTrace(); return; }}
  el.innerHTML = `<div class="timeline">` + state.trace.map(t => `
    <div class="t-item">
      <div class="t-dot ${{t.status}}">${{t.status === 'success' ? '✓' : t.status === 'error' ? '✕' : '…'}}</div>
      <div class="t-card">
        <div class="t-card-top">
          <span class="t-round">round ${{t.round}}</span>
          <span class="t-toolname">${{escapeHtml(t.tool || '')}}</span>
          <span class="badge ${{t.status}}">${{escapeHtml(t.status || '')}}</span>
          <span class="t-duration">${{escapeHtml(t.duration || '')}}</span>
        </div>
        <div class="t-desc">${{escapeHtml(t.desc || '')}}</div>
        <details class="mini"><summary>arguments</summary><pre class="code">${{escapeHtml(JSON.stringify(t.args || {{}}, null, 2))}}</pre></details>
        <details class="mini"><summary>result</summary><pre class="code">${{escapeHtml(t.result || '')}}</pre></details>
      </div>
    </div>
  `).join('') + `</div>`;
}}

function renderRunDetails() {{
  const v = document.getElementById('versionSelect').value;
  const m = RUN_META[v] || {{}};
  document.getElementById('runContent').innerHTML = `
    <div class="kv-panel">
      <h3>Run identity</h3>
      <div class="kv-row"><div class="kv-key">version</div><div class="kv-val"><span class="ver-tag">${{escapeHtml(v)}}</span></div></div>
      <div class="kv-row"><div class="kv-key">run_id</div><div class="kv-val">${{escapeHtml(m.runId || '—')}}</div></div>
      <div class="kv-row"><div class="kv-key">artifact_version</div><div class="kv-val hash">${{escapeHtml(m.artifact || '—')}}</div></div>
      <div class="kv-row"><div class="kv-key">prompt_hash</div><div class="kv-val hash">${{escapeHtml(m.promptHash || '—')}}</div></div>
      <div class="kv-row"><div class="kv-key">tools_hash</div><div class="kv-val hash">${{escapeHtml(m.toolsHash || '—')}}</div></div>
      <div class="kv-row"><div class="kv-key">generated_at</div><div class="kv-val">${{escapeHtml(m.generatedAt || '—')}}</div></div>
    </div>
    <div class="kv-panel">
      <h3>Provider / Model</h3>
      <div class="kv-row"><div class="kv-key">provider</div><div class="kv-val">${{escapeHtml(m.provider || '—')}}</div></div>
      <div class="kv-row"><div class="kv-key">model</div><div class="kv-val">${{escapeHtml(m.model || '—')}}</div></div>
      <div class="kv-row"><div class="kv-key">phase / suite</div><div class="kv-val">${{escapeHtml(m.phaseSuite || '—')}}</div></div>
    </div>
    <div class="kv-panel">
      <h3>Transcript</h3>
      <div class="kv-row"><div class="kv-key">file</div><div class="kv-val">${{escapeHtml(m.transcript || '—')}}</div></div>
    </div>
    <p class="copy-hint">Dữ liệu được đọc từ run JSON, transcript JSON và version log thật.</p>
  `;
}}

function renderMetrics() {{
  const current = document.getElementById('versionSelect').value;
  const rows = METRICS.map(m => {{
    const active = m.v === current ? 'style="background:var(--panel-2)"' : '';
    return `
    <tr ${{active}}>
      <td><span class="ver-tag">${{escapeHtml(m.v)}}</span></td>
      <td>${{bar(m.case)}}</td>
      <td>${{bar(m.routing)}}</td>
      <td>${{bar(m.args)}}</td>
      <td>${{bar(m.multiturn)}}</td>
      <td>${{m.errors > 0 ? `<span class="flag">${{m.errors}} ⚠</span>` : '0'}}</td>
    </tr>`;
  }}).join('');
  function bar(val) {{
    const pct = Math.round((Number(val) || 0) * 100);
    return `<div class="bar-cell"><div class="bar-track"><div class="bar-fill" style="width:${{pct}}%"></div></div><span>${{pct}}%</span></div>`;
  }}
  const noteRow = METRICS.find(m => m.v === current) || {{}};
  document.getElementById('metricsContent').innerHTML = `
    <table class="metrics">
      <thead><tr>
        <th>Version</th><th>Case accuracy</th><th>Tool routing</th><th>Argument accuracy</th><th>Multiturn</th><th>Provider errors</th>
      </tr></thead>
      <tbody>${{rows}}</tbody>
    </table>
    <div class="note-box"><strong>${{escapeHtml(current)}}</strong> — ${{escapeHtml(noteRow.note || 'No note available.')}}</div>
  `;
}}

function onVersionChange() {{
  const v = document.getElementById('versionSelect').value;
  const meta = RUN_META[v] || {{}};
  const provider = meta.provider || DEMO_DATA.provider || 'local';
  const model = meta.model || DEMO_DATA.model || 'demo';
  document.getElementById('providerLabel').textContent = `${{provider}} · ${{model}}`;
  document.getElementById('providerDot').className = 'dot' + (v === 'v0' ? ' err' : '');
  renderRunDetails();
  renderMetrics();
}}

function initScenarioButtons() {{
  const labels = DEMO_DATA.scenario_labels || {{}};
  const mapping = {{
    normal: labels.normal || 'Tìm tin AI hôm nay và tóm tắt 5 ý chính.',
    missing: labels.missing || 'Tóm tắt bài viết này giúp mình.',
    confirm: labels.confirm || 'Gửi bản tổng hợp này lên Telegram giúp mình.',
    error: labels.error || 'Trigger lỗi tool (demo).'
  }};
  document.querySelectorAll('.scenario-btn').forEach(btn => {{
    const kind = (btn.getAttribute('onclick') || '').match(/runScenario\\('([^']+)'\\)/);
    if (!kind) return;
    const label = mapping[kind[1]];
    if (label) btn.innerHTML = escapeHtml(label).replace(/\\n/g, '<br/>');
  }});
}}

function replayScenario(scenarioKey) {{
  const scenario = SCENARIOS[scenarioKey];
  if (!scenario) return;
  setBusy(true);
  addTyping();
  setTimeout(() => {{
    removeTyping();
    addUserMsg(scenario.user || '');
    state.trace = [];
    state.round = 0;
    document.getElementById('traceCount').textContent = 0;
    const steps = scenario.trace || [];
    let delay = 0;
    steps.forEach((step, index) => {{
      delay += Number(step.delay_ms || 350);
      setTimeout(() => {{
        state.round = step.round || (index + 1);
        const cardId = addToolCard(step.tool || 'tool', step.args || {{}}, step.status || 'success', step.result || '', step.duration || '');
        setTimeout(() => {{
          resolveToolCard(cardId, step.status || 'success', step.result || '', step.duration || '');
          pushTrace({{
            round: state.round,
            tool: step.tool || 'tool',
            status: step.status || 'success',
            duration: step.duration || '',
            args: step.args || {{}},
            result: step.result || '',
            desc: step.desc || ''
          }});
          renderTraceView();
        }}, Math.max(60, Number(step.resolve_delay_ms || 120)));
      }}, delay);
    }});
    setTimeout(() => {{
      addAgentMsg(scenario.assistant || scenario.final || '—');
      setBusy(false);
    }}, delay + 420);
  }}, 280);
}}

function runScenario(kind) {{
  if (state.busy) return;
  if (SCENARIOS[kind]) {{
    replayScenario(kind);
    return;
  }}
  addUserMsg(kind);
  addAgentMsg('Chưa có dữ liệu scenario cho lựa chọn này.');
}}

function handleComposerKey(e) {{
  if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendFromComposer(); }}
}}
function sendFromComposer() {{
  const inp = document.getElementById('composerInput');
  const text = inp.value.trim();
  if (!text || state.busy) return;
  inp.value = '';
  const lowered = text.toLowerCase();
  if (lowered.includes('telegram') || lowered.includes('gửi')) return runScenario('confirm');
  if (lowered.includes('tóm tắt') && !lowered.includes('http')) return runScenario('missing');
  if (lowered.includes('lỗi') || lowered.includes('error')) return runScenario('error');
  return runScenario('normal');
}}

function resetChat() {{
  stream.innerHTML = '';
  resetTrace();
  setBusy(false);
  addAgentMsg(DEMO_DATA.welcome_message || 'Chào bạn. Mình là research agent.');
}}

function switchTab(tab) {{
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`view-${{tab}}`).classList.add('active');
  document.querySelector(`.tab-btn[data-tab="${{tab}}"]`).classList.add('active');
  if (tab === 'trace') renderTraceView();
  if (tab === 'run') renderRunDetails();
  if (tab === 'metrics') renderMetrics();
}}

document.getElementById('versionSelect').value = INITIAL_VERSION;
document.getElementById('versionSelect').addEventListener('change', onVersionChange);
document.querySelectorAll('.scenario-btn').forEach(btn => btn.addEventListener('click', () => {{}}));
initScenarioButtons();
onVersionChange();
resetTrace();
resetChat();
</script>
"""


def render_demo_page(data: dict[str, Any]) -> str:
    html = load_demo_template()
    start = html.find("<script>")
    end = html.rfind("</script>")
    if start == -1 or end == -1 or end < start:
        raise ValueError("demo.html does not contain a script block to replace")
    prefix = html[:start]
    suffix = html[end + len("</script>"):]
    return prefix + build_runtime_script(data) + suffix


def main() -> None:
    run_files = list_json(RUNS_DIR)
    transcript_files = list_json(TRANSCRIPTS_DIR)
    version_rows = csv_rows(ARTIFACTS_DIR / "version_log.csv")
    selected_run_path = st.sidebar.selectbox(
        "Run JSON",
        ["(latest)"] + [path.name for path in run_files] if run_files else ["(none)"],
        index=0,
    )
    selected_transcript_path = st.sidebar.selectbox(
        "Transcript JSON",
        ["(latest)"] + [path.name for path in transcript_files] if transcript_files else ["(none)"],
        index=0,
    )

    selected_run = latest(run_files) if selected_run_path == "(latest)" else select_run_payload(selected_run_path)
    selected_transcript = latest(transcript_files) if selected_transcript_path == "(latest)" else select_transcript_payload(selected_transcript_path)

    data = build_demo_data()
    if selected_run:
        data["selected_version"] = selected_run.get("version") or data.get("selected_version")
        data["provider"] = selected_run.get("provider", data.get("provider"))
        data["model"] = selected_run.get("model", data.get("model"))
        data["run_meta"].update(build_run_meta(version_rows, selected_run, run_files, transcript_files))
        data["metrics"] = derive_metrics(selected_run)
        scenarios = derive_scenarios(selected_run, selected_transcript, read_json(DATA_DIR / "eval_group.json", default={}) or {})
        data["scenarios"] = scenarios["scenarios"]
        data["scenario_labels"] = scenarios["scenario_labels"]

    html = render_demo_page(data)
    components.html(html, height=1280, scrolling=True)


if __name__ == "__main__":
    main()
