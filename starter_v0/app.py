from __future__ import annotations

import html
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import streamlit as st

from env_loader import load_lab_env
from providers import make_provider
from providers.base import ToolCall
from tools import TOOL_FUNCTIONS, load_tool_declarations, to_openai_tools
from versioning import build_artifact_version


# ============================================================
# Application configuration
# ============================================================

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
TRANSCRIPTS_DIR = ROOT / "transcripts"

SYSTEM_PROMPT_PATH = ARTIFACTS_DIR / "system_prompt.md"
TOOLS_PATH = ARTIFACTS_DIR / "tools.yaml"

load_lab_env(ROOT)

st.set_page_config(
    page_title="Research Agent Lab",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# UI styling
# ============================================================

def apply_custom_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1480px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(128, 128, 128, 0.18);
        }

        .hero-section {
            padding: 1.5rem 1.7rem;
            margin-bottom: 1.2rem;
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 22px;
            background:
                linear-gradient(
                    135deg,
                    color-mix(in srgb, var(--primary-color) 13%, transparent),
                    transparent 58%
                );
        }

        .hero-eyebrow {
            margin-bottom: 0.45rem;
            color: var(--primary-color);
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .hero-title {
            margin: 0;
            font-size: 2rem;
            font-weight: 750;
            line-height: 1.2;
        }

        .hero-subtitle {
            max-width: 850px;
            margin-top: 0.55rem;
            margin-bottom: 0;
            color: rgba(128, 128, 128, 0.95);
            font-size: 1rem;
        }

        .chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1rem;
        }

        .info-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.35rem 0.68rem;
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 999px;
            background: color-mix(
                in srgb,
                var(--background-color) 90%,
                var(--primary-color)
            );
            font-size: 0.82rem;
        }

        .section-label {
            margin-top: 0.4rem;
            margin-bottom: 0.7rem;
            font-size: 0.83rem;
            font-weight: 700;
            letter-spacing: 0.055em;
            text-transform: uppercase;
            color: rgba(128, 128, 128, 0.95);
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.28rem 0.62rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
        }

        .status-success {
            color: #137333;
            background: rgba(52, 168, 83, 0.15);
        }

        .status-error {
            color: #b3261e;
            background: rgba(234, 67, 53, 0.15);
        }

        .status-waiting {
            color: #8a4b00;
            background: rgba(251, 188, 4, 0.18);
        }

        .status-neutral {
            color: rgba(128, 128, 128, 1);
            background: rgba(128, 128, 128, 0.12);
        }

        .tool-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.55rem;
        }

        .tool-title {
            margin: 0;
            font-size: 1rem;
            font-weight: 700;
        }

        .tool-meta {
            margin-top: 0.2rem;
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.82rem;
        }

        .run-id {
            overflow-wrap: anywhere;
            color: rgba(128, 128, 128, 0.95);
            font-family: monospace;
            font-size: 0.78rem;
        }

        div[data-testid="stMetric"] {
            padding: 0.85rem 1rem;
            border: 1px solid rgba(128, 128, 128, 0.18);
            border-radius: 16px;
        }

        div[data-testid="stChatMessage"] {
            border-radius: 18px;
        }

        .stButton > button {
            border-radius: 12px;
        }

        .stTextInput input,
        .stSelectbox [data-baseweb="select"] > div {
            border-radius: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Utility functions
# ============================================================

def json_text(value: Any) -> str:
    """Convert an object to readable JSON."""
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def get_event_status(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("awaiting_user"):
            return "waiting"
        if result.get("error"):
            return "error"

    return "success"


def status_label(status: str) -> tuple[str, str]:
    labels = {
        "success": ("Thành công", "status-success"),
        "error": ("Lỗi", "status-error"),
        "waiting": ("Chờ người dùng", "status-waiting"),
        "answered": ("Đã trả lời", "status-success"),
        "waiting_for_user": ("Chờ bổ sung", "status-waiting"),
        "provider_error": ("Lỗi provider", "status-error"),
        "max_tool_rounds": ("Vượt giới hạn round", "status-error"),
    }

    return labels.get(status, (status, "status-neutral"))


def create_run_id(version_label: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    suffix = uuid4().hex[:6]
    return f"{version_label}_{timestamp}_{suffix}"


def initialize_session_state() -> None:
    defaults = {
        "session_id": uuid4().hex[:12],
        "messages": [],
        "history": [],
        "runs": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_session() -> None:
    st.session_state.session_id = uuid4().hex[:12]
    st.session_state.messages = []
    st.session_state.history = []
    st.session_state.runs = []


def transcript_payload() -> dict[str, Any]:
    return {
        "session_id": st.session_state.session_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "messages": st.session_state.messages,
        "runs": st.session_state.runs,
    }


def save_transcript() -> Path:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    transcript_path = (
        TRANSCRIPTS_DIR
        / f"{st.session_state.session_id}.transcript.json"
    )

    transcript_path.write_text(
        json_text(transcript_payload()),
        encoding="utf-8",
    )

    return transcript_path


# ============================================================
# Tool execution
# ============================================================

def execute_tool_call(
    call: ToolCall,
    round_index: int,
    call_index: int,
) -> dict[str, Any]:
    started_at = time.perf_counter()

    func = TOOL_FUNCTIONS.get(call.name)

    if not func:
        result: Any = {
            "error": "unknown_tool",
            "message": f"No implementation found for tool '{call.name}'.",
        }
    else:
        try:
            result = func(**call.args)
        except Exception as exc:
            result = {
                "error": type(exc).__name__,
                "message": str(exc),
            }

    duration_ms = round(
        (time.perf_counter() - started_at) * 1000,
        2,
    )

    return {
        "round": round_index,
        "call_index": call_index,
        "tool": call.name,
        "args": call.args,
        "result": result,
        "status": get_event_status(result),
        "duration_ms": duration_ms,
    }


def assistant_tool_message(
    response_text: str | None,
    calls: list[ToolCall],
) -> dict[str, str]:
    call_summary = [
        {
            "name": call.name,
            "args": call.args,
        }
        for call in calls
    ]

    content = response_text or "I will call the selected tool(s)."

    return {
        "role": "assistant",
        "content": (
            f"{content}\n\n"
            "TOOL_CALLS_JSON:\n"
            f"{json_text(call_summary)}"
        ),
    }


def tool_results_message(
    events: list[dict[str, Any]],
) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "TOOL_RESULTS_JSON:\n"
            f"{json_text(events)}\n\n"
            "Use only these tool results. "
            "If the user asked for a digest and the items are ready, "
            "call the formatting tool. Otherwise answer the user directly "
            "with cited sources when available."
        ),
    }


# ============================================================
# Agent loop
# ============================================================

def run_agent_loop(
    provider: Any,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]],
    model: str | None,
    max_tool_rounds: int = 4,
    on_tool_update: Callable[[str, ToolCall, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    loop_started_at = time.perf_counter()

    working_messages = list(messages)
    rounds: list[dict[str, Any]] = []
    all_tool_events: list[dict[str, Any]] = []

    for round_index in range(1, max_tool_rounds + 1):
        provider_started_at = time.perf_counter()

        try:
            response = provider.complete(
                working_messages,
                tools,
                model=model,
                temperature=0.0,
            )
        except Exception as exc:
            provider_duration_ms = round(
                (time.perf_counter() - provider_started_at) * 1000,
                2,
            )

            rounds.append(
                {
                    "round": round_index,
                    "assistant_text": None,
                    "tool_calls": [],
                    "tool_results": [],
                    "provider_duration_ms": provider_duration_ms,
                    "provider_error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )

            return {
                "status": "provider_error",
                "assistant_text": (
                    "Không thể hoàn thành yêu cầu vì provider đang gặp lỗi. "
                    "Hãy kiểm tra API key, quota hoặc cấu hình model."
                ),
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                "rounds": rounds,
                "tool_events": all_tool_events,
                "total_duration_ms": round(
                    (time.perf_counter() - loop_started_at) * 1000,
                    2,
                ),
            }

        provider_duration_ms = round(
            (time.perf_counter() - provider_started_at) * 1000,
            2,
        )

        calls = response.tool_calls or []

        round_record: dict[str, Any] = {
            "round": round_index,
            "assistant_text": response.text,
            "tool_calls": [
                {
                    "name": call.name,
                    "args": call.args,
                }
                for call in calls
            ],
            "tool_results": [],
            "provider_duration_ms": provider_duration_ms,
        }

        # Agent has produced a final response.
        if not calls:
            rounds.append(round_record)

            return {
                "status": "answered",
                "assistant_text": response.text or "",
                "rounds": rounds,
                "tool_events": all_tool_events,
                "total_duration_ms": round(
                    (time.perf_counter() - loop_started_at) * 1000,
                    2,
                ),
            }

        working_messages.append(
            assistant_tool_message(response.text, calls)
        )

        non_clarification_events: list[dict[str, Any]] = []

        for call_index, call in enumerate(calls, start=1):
            if on_tool_update:
                on_tool_update("calling", call, None)

            event = execute_tool_call(
                call=call,
                round_index=round_index,
                call_index=call_index,
            )

            round_record["tool_results"].append(event)
            all_tool_events.append(event)

            if on_tool_update:
                on_tool_update("completed", call, event)

            result = event.get("result", {})

            if (
                isinstance(result, dict)
                and result.get("awaiting_user")
            ):
                question = (
                    result.get("question")
                    or call.args.get("question")
                    or "Bạn vui lòng bổ sung thêm thông tin."
                )

                rounds.append(round_record)

                return {
                    "status": "waiting_for_user",
                    "assistant_text": question,
                    "rounds": rounds,
                    "tool_events": all_tool_events,
                    "total_duration_ms": round(
                        (time.perf_counter() - loop_started_at) * 1000,
                        2,
                    ),
                }

            non_clarification_events.append(event)

        rounds.append(round_record)

        working_messages.append(
            tool_results_message(non_clarification_events)
        )

    return {
        "status": "max_tool_rounds",
        "assistant_text": (
            f"Agent đã dừng sau {max_tool_rounds} vòng gọi tool "
            "để tránh vòng lặp không kiểm soát."
        ),
        "rounds": rounds,
        "tool_events": all_tool_events,
        "total_duration_ms": round(
            (time.perf_counter() - loop_started_at) * 1000,
            2,
        ),
    }


# ============================================================
# UI rendering functions
# ============================================================

def render_header(
    provider_name: str,
    model_name: str,
    version_label: str,
    tool_count: int,
) -> None:
    provider_safe = html.escape(provider_name)
    model_safe = html.escape(model_name or "Default model")
    version_safe = html.escape(version_label)

    st.markdown(
        f"""
        <section class="hero-section">
           
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_status_pill(status: str) -> None:
    label, css_class = status_label(status)

    st.markdown(
        f"""
        <span class="status-pill {css_class}">
            {html.escape(label)}
        </span>
        """,
        unsafe_allow_html=True,
    )


def render_tool_event(
    event: dict[str, Any],
    expanded: bool = False,
) -> None:
    tool_name = str(event.get("tool", "unknown_tool"))
    event_status = str(event.get("status", "unknown"))
    duration_ms = event.get("duration_ms", 0)
    round_index = event.get("round", "?")
    call_index = event.get("call_index", "?")

    with st.container(border=True):
        heading_col, status_col = st.columns(
            [4, 1],
            vertical_alignment="center",
        )

        with heading_col:
            st.markdown(
                f"""
                <div class="tool-heading">
                    <div>
                        <p class="tool-title">
                            🛠️ {html.escape(tool_name)}
                        </p>
                        <p class="tool-meta">
                            Round {round_index}
                            · Call {call_index}
                            · {duration_ms} ms
                        </p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with status_col:
            render_status_pill(event_status)

        args_col, result_col = st.columns(2)

        with args_col:
            with st.expander(
                "Arguments",
                expanded=expanded,
            ):
                st.code(
                    json_text(event.get("args", {})),
                    language="json",
                )

        with result_col:
            with st.expander(
                "Result",
                expanded=expanded or event_status == "error",
            ):
                result = event.get("result", {})

                if event_status == "error":
                    message = (
                        result.get("message")
                        if isinstance(result, dict)
                        else str(result)
                    )
                    st.error(message or "Tool execution failed.")

                st.code(
                    json_text(result),
                    language="json",
                )


def render_message(message: dict[str, Any]) -> None:
    role = message.get("role", "assistant")
    avatar = "👤" if role == "user" else "🤖"

    with st.chat_message(role, avatar=avatar):
        st.markdown(message.get("content", ""))

        run_id = message.get("run_id")
        status = message.get("status")

        if role == "assistant" and (run_id or status):
            metadata_cols = st.columns([1, 4])

            with metadata_cols[0]:
                if status:
                    render_status_pill(status)

            with metadata_cols[1]:
                if run_id:
                    st.markdown(
                        f"""
                        <div class="run-id">
                            Run ID: {html.escape(str(run_id))}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        tool_events = message.get("tool_events", [])

        if tool_events:
            with st.expander(
                f"Tool trace · {len(tool_events)} event(s)",
                expanded=False,
            ):
                for event in tool_events:
                    render_tool_event(event)


def render_run_metrics(run: dict[str, Any]) -> None:
    tool_events = run.get("tool_events", [])
    rounds = run.get("rounds", [])

    success_calls = sum(
        1
        for event in tool_events
        if event.get("status") == "success"
    )

    error_calls = sum(
        1
        for event in tool_events
        if event.get("status") == "error"
    )

    metric_cols = st.columns(4)

    metric_cols[0].metric(
        "Agent status",
        status_label(run.get("status", "unknown"))[0],
    )

    metric_cols[1].metric(
        "Tool calls",
        len(tool_events),
        delta=f"{success_calls} success",
    )

    metric_cols[2].metric(
        "Rounds",
        len(rounds),
    )

    metric_cols[3].metric(
        "Duration",
        f"{run.get('total_duration_ms', 0):,.0f} ms",
        delta=f"{error_calls} errors" if error_calls else None,
        delta_color="inverse",
    )


def tool_declaration_rows(
    declarations: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if not isinstance(declarations, list):
        return rows

    for declaration in declarations:
        if not isinstance(declaration, dict):
            continue

        function_data = declaration.get("function", {})
        function_data = (
            function_data
            if isinstance(function_data, dict)
            else {}
        )

        name = (
            declaration.get("name")
            or function_data.get("name")
            or "unknown"
        )

        description = (
            declaration.get("description")
            or function_data.get("description")
            or ""
        )

        parameters = (
            declaration.get("parameters")
            or function_data.get("parameters")
            or {}
        )

        required = (
            parameters.get("required", [])
            if isinstance(parameters, dict)
            else []
        )

        rows.append(
            {
                "Tool": name,
                "Description": description,
                "Required arguments": ", ".join(required),
            }
        )

    return rows


# ============================================================
# Main application
# ============================================================

def main() -> None:
    apply_custom_css()
    initialize_session_state()

    # --------------------------------------------------------
    # Validate artifact files
    # --------------------------------------------------------

    missing_files = [
        path
        for path in (SYSTEM_PROMPT_PATH, TOOLS_PATH)
        if not path.exists()
    ]

    if missing_files:
        st.error(
            "Không tìm thấy artifact bắt buộc:\n\n"
            + "\n".join(f"- `{path}`" for path in missing_files)
        )
        st.stop()

    try:
        system_prompt = SYSTEM_PROMPT_PATH.read_text(
            encoding="utf-8"
        )

        tool_declarations = load_tool_declarations(TOOLS_PATH)
        openai_tools = to_openai_tools(tool_declarations)

    except Exception as exc:
        st.error(
            f"Không thể tải prompt hoặc tools.yaml: {exc}"
        )
        st.stop()

    # --------------------------------------------------------
    # Sidebar configuration
    # --------------------------------------------------------

    with st.sidebar:
        st.markdown("## 🔬 Lab Control Panel")
        st.caption(
            "Cấu hình môi trường chạy và artifact version."
        )

        provider_name = st.selectbox(
            "Provider",
            [
                "nvidia",
                "groq",
                "gemini",
                "openrouter",
                "openai",
                "anthropic",
            ],
            index=0,
            help="Provider dùng để gọi model.",
        )

        version_label = st.text_input(
            "Version label",
            value="v0",
            help="Ví dụ: v0, v1, v2 hoặc v3.",
        ).strip() or "v0"

        model_override = st.text_input(
            "Model override",
            value="",
            placeholder="Để trống để dùng default model",
        ).strip()

        max_tool_rounds = st.slider(
            "Maximum tool rounds",
            min_value=1,
            max_value=8,
            value=4,
            help="Giới hạn số vòng agent có thể gọi tool.",
        )

        show_trace_live = st.toggle(
            "Mở Tool Trace sau khi chạy",
            value=True,
        )

        st.divider()

        artifact_version = build_artifact_version(
            version_label,
            SYSTEM_PROMPT_PATH,
            TOOLS_PATH,
        )

        st.markdown("### Artifact identity")
        st.code(
            artifact_version.artifact_version,
            language=None,
        )

        st.caption("Prompt hash")
        st.code(
            artifact_version.prompt_hash[:16],
            language=None,
        )

        st.caption("Tools hash")
        st.code(
            artifact_version.tools_hash[:16],
            language=None,
        )

        st.divider()

        clear_col, new_col = st.columns(2)

        with clear_col:
            if st.button(
                "Xóa chat",
                use_container_width=True,
            ):
                clear_session()
                st.rerun()

        with new_col:
            if st.button(
                "Phiên mới",
                use_container_width=True,
            ):
                clear_session()
                st.rerun()

        transcript_data = json_text(
            transcript_payload()
        )

        st.download_button(
            "⬇️ Tải transcript",
            data=transcript_data,
            file_name=(
                f"{st.session_state.session_id}"
                ".transcript.json"
            ),
            mime="application/json",
            use_container_width=True,
        )

        st.caption(
            f"Session: `{st.session_state.session_id}`"
        )

    # --------------------------------------------------------
    # Provider initialization
    # --------------------------------------------------------

    provider = None
    provider_setup_error: str | None = None

    try:
        provider = make_provider(provider_name)
        selected_model = (
            model_override
            or getattr(provider, "default_model", None)
            or "default"
        )
    except Exception as exc:
        selected_model = model_override or "unavailable"
        provider_setup_error = str(exc)

    # --------------------------------------------------------
    # Header and summary
    # --------------------------------------------------------

    render_header(
        provider_name=provider_name,
        model_name=selected_model,
        version_label=version_label,
        tool_count=len(tool_declarations),
    )

    if provider_setup_error:
        st.error(
            "Provider chưa sẵn sàng: "
            f"{provider_setup_error}"
        )

    # --------------------------------------------------------
    # Main navigation
    # --------------------------------------------------------

    chat_tab, trace_tab, run_tab = st.tabs(
        [
            "💬 Agent Chat",
            "🛠️ Tool Trace",
            "📑 Run Details",
        ]
    )

    # ========================================================
    # Chat tab
    # ========================================================

    with chat_tab:
        st.markdown(
            '<div class="section-label">Demo scenarios</div>',
            unsafe_allow_html=True,
        )

        demo_prompt: str | None = None

        prompt_col_1, prompt_col_2, prompt_col_3 = st.columns(3)

        with prompt_col_1:
            if st.button(
                "🔎 Research bình thường",
                use_container_width=True,
            ):
                demo_prompt = (
                    "Tìm trên web tin AI hôm nay "
                    "và tóm tắt những điểm nổi bật."
                )

        with prompt_col_2:
            if st.button(
                "❓ Thiếu URL",
                use_container_width=True,
            ):
                demo_prompt = (
                    "Tóm tắt bài viết này giúp mình."
                )

        with prompt_col_3:
            if st.button(
                "🛡️ Xác nhận hành động",
                use_container_width=True,
            ):
                demo_prompt = (
                    "Đăng bản tin này lên Telegram giúp mình."
                )

        st.divider()

        if not st.session_state.messages:
            st.info(
                "Bắt đầu bằng một câu hỏi hoặc chọn "
                "một kịch bản demo phía trên."
            )

        for message in st.session_state.messages:
            render_message(message)

        typed_input = st.chat_input(
            "Nhập yêu cầu cho Research Agent..."
        )

        user_input = demo_prompt or typed_input

        if user_input:
            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            with st.chat_message("user", avatar="👤"):
                st.markdown(user_input)

            if provider is None:
                st.error(
                    "Không thể chạy agent vì provider "
                    "chưa được khởi tạo."
                )
                st.stop()

            history_context = (
                st.session_state.history[-10:]
                if st.session_state.history
                else []
            )

            input_messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                *history_context,
                {
                    "role": "user",
                    "content": user_input,
                },
            ]

            run_id = create_run_id(version_label)

            with st.chat_message(
                "assistant",
                avatar="🤖",
            ):
                with st.status(
                    "Agent đang phân tích yêu cầu...",
                    expanded=True,
                ) as run_status:
                    live_tool_status = st.empty()

                    def update_live_tool(
                        state: str,
                        call: ToolCall,
                        event: dict[str, Any] | None,
                    ) -> None:
                        if state == "calling":
                            live_tool_status.info(
                                f"Đang gọi tool `{call.name}`..."
                            )
                            return

                        if event and event.get("status") == "error":
                            live_tool_status.error(
                                f"Tool `{call.name}` gặp lỗi sau "
                                f"{event.get('duration_ms', 0)} ms"
                            )
                        else:
                            live_tool_status.success(
                                f"Tool `{call.name}` hoàn tất trong "
                                f"{event.get('duration_ms', 0) if event else 0} ms"
                            )

                    st.write(
                        f"Provider: `{provider_name}`"
                    )
                    st.write(
                        f"Model: `{selected_model}`"
                    )
                    st.write(
                        f"Artifact: "
                        f"`{artifact_version.artifact_version}`"
                    )

                    response = run_agent_loop(
                        provider=provider,
                        messages=input_messages,
                        tools=openai_tools,
                        model=selected_model,
                        max_tool_rounds=max_tool_rounds,
                        on_tool_update=update_live_tool,
                    )

                    response_status = response.get(
                        "status",
                        "unknown",
                    )

                    if response_status in {
                        "provider_error",
                        "max_tool_rounds",
                    }:
                        run_status.update(
                            label="Agent kết thúc với lỗi",
                            state="error",
                            expanded=False,
                        )
                    elif response_status == "waiting_for_user":
                        run_status.update(
                            label="Agent cần thêm thông tin",
                            state="complete",
                            expanded=False,
                        )
                    else:
                        run_status.update(
                            label="Agent đã hoàn thành",
                            state="complete",
                            expanded=False,
                        )

                assistant_text = response.get(
                    "assistant_text",
                    "",
                )

                st.markdown(assistant_text)

                response_tool_events = response.get(
                    "tool_events",
                    [],
                )

                response_rounds = response.get(
                    "rounds",
                    [],
                )

                run_record = {
                    "run_id": run_id,
                    "created_at": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    "provider": provider_name,
                    "model": selected_model,
                    "version": version_label,
                    "artifact_version": (
                        artifact_version.artifact_version
                    ),
                    "prompt_hash": (
                        artifact_version.prompt_hash
                    ),
                    "tools_hash": (
                        artifact_version.tools_hash
                    ),
                    "status": response_status,
                    "user_input": user_input,
                    "assistant_text": assistant_text,
                    "tool_events": response_tool_events,
                    "rounds": response_rounds,
                    "total_duration_ms": response.get(
                        "total_duration_ms",
                        0,
                    ),
                    "error": response.get("error"),
                }

                render_run_metrics(run_record)

                if response_tool_events:
                    with st.expander(
                        (
                            "Tool Trace "
                            f"· {len(response_tool_events)} event(s)"
                        ),
                        expanded=show_trace_live,
                    ):
                        for event in response_tool_events:
                            render_tool_event(
                                event,
                                expanded=False,
                            )

                if response.get("error"):
                    with st.expander(
                        "Technical error details"
                    ):
                        st.code(
                            json_text(response["error"]),
                            language="json",
                        )

            assistant_message = {
                "role": "assistant",
                "content": assistant_text,
                "run_id": run_id,
                "status": response_status,
                "tool_events": response_tool_events,
            }

            st.session_state.messages.append(
                assistant_message
            )

            st.session_state.history.extend(
                [
                    {
                        "role": "user",
                        "content": user_input,
                    },
                    {
                        "role": "assistant",
                        "content": assistant_text,
                    },
                ]
            )

            st.session_state.runs.append(run_record)
            save_transcript()

    # ========================================================
    # Tool Trace tab
    # ========================================================

    with trace_tab:
        st.markdown(
            '<div class="section-label">Execution evidence</div>',
            unsafe_allow_html=True,
        )

        if not st.session_state.runs:
            st.info(
                "Chưa có run nào. Hãy chạy agent trong tab Chat."
            )
        else:
            run_options = {
                run["run_id"]: run
                for run in reversed(st.session_state.runs)
            }

            selected_run_id = st.selectbox(
                "Chọn run cần kiểm tra",
                options=list(run_options.keys()),
            )

            selected_run = run_options[selected_run_id]

            render_run_metrics(selected_run)

            st.caption(
                f"Artifact: "
                f"`{selected_run.get('artifact_version')}`"
            )

            st.markdown("### User request")
            st.info(selected_run.get("user_input", ""))

            st.markdown("### Final response")
            st.markdown(
                selected_run.get("assistant_text", "")
            )

            st.markdown("### Tool execution trace")

            selected_events = selected_run.get(
                "tool_events",
                [],
            )

            if not selected_events:
                st.info(
                    "Run này không gọi tool."
                )
            else:
                for event in selected_events:
                    render_tool_event(
                        event,
                        expanded=True,
                    )

            with st.expander("Round-level details"):
                st.code(
                    json_text(
                        selected_run.get("rounds", [])
                    ),
                    language="json",
                )

    # ========================================================
    # Run Details tab
    # ========================================================

    with run_tab:
        st.markdown(
            '<div class="section-label">Reproducibility information</div>',
            unsafe_allow_html=True,
        )

        artifact_col, session_col = st.columns(2)

        with artifact_col:
            with st.container(border=True):
                st.markdown("### Artifact identity")

                st.markdown(
                    f"**Version label:** `{version_label}`"
                )
                st.markdown(
                    "**Artifact version:**"
                )
                st.code(
                    artifact_version.artifact_version,
                    language=None,
                )

                st.markdown("**Prompt hash:**")
                st.code(
                    artifact_version.prompt_hash,
                    language=None,
                )

                st.markdown("**Tools hash:**")
                st.code(
                    artifact_version.tools_hash,
                    language=None,
                )

        with session_col:
            with st.container(border=True):
                st.markdown("### Runtime session")

                st.markdown(
                    f"**Session ID:** "
                    f"`{st.session_state.session_id}`"
                )
                st.markdown(
                    f"**Provider:** `{provider_name}`"
                )
                st.markdown(
                    f"**Model:** `{selected_model}`"
                )
                st.markdown(
                    f"**Recorded runs:** "
                    f"`{len(st.session_state.runs)}`"
                )
                st.markdown(
                    f"**Transcript:** "
                    f"`transcripts/"
                    f"{st.session_state.session_id}"
                    f".transcript.json`"
                )

        st.markdown("### Registered tools")

        rows = tool_declaration_rows(tool_declarations)

        if rows:
            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "Không đọc được danh sách tool declarations."
            )

        with st.expander(
            "System prompt preview",
            expanded=False,
        ):
            st.code(
                system_prompt,
                language="markdown",
            )

        with st.expander(
            "Raw transcript JSON",
            expanded=False,
        ):
            st.code(
                json_text(transcript_payload()),
                language="json",
            )


if __name__ == "__main__":
    main()
