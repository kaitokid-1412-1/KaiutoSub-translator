"""Local Web UI server for SubTrans Auto with strict security and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from subtrans.core.config import Config, get_user_data_dir, load_config, mask_api_key, save_config
from subtrans.core.doctor import run_diagnostics
from subtrans.core.pipeline import FileTask, Pipeline, Stage, StageStatus, discover_inputs
from subtrans.core.probe import choose_best_subtitle_track, probe_subtitles
from subtrans.core.store import TranslationStore

STATIC_DIR = Path(__file__).parent / "static"


def find_free_port(start_port: int = 8765) -> int:
    """Find a free port starting from start_port."""
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


@dataclass
class JobState:
    job_id: str = "web_job"
    status: str = "IDLE"  # IDLE, RUNNING, PAUSED, COMPLETED, FAILED
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "total_files": 0,
        "completed_files": 0,
        "failed_files": 0,
        "api_calls": 0,
        "total_tokens": 0,
    })
    is_paused: bool = False
    thread: Optional[threading.Thread] = None


class ServerManager:
    """Manages active job state, background execution, and SSE event streaming."""

    def __init__(self, token: str, config: Optional[Config] = None):
        self.token = token
        self.cfg = config or load_config()
        self.job = JobState()
        self.subscribers: List[asyncio.Queue] = []
        self._lock = threading.Lock()

    def log(self, message: str):
        with self._lock:
            self.job.logs.append(message)
            if len(self.job.logs) > 500:
                self.job.logs = self.job.logs[-500:]

    def broadcast_sync(self, event_type: str, data: Any):
        """Broadcast event to all SSE subscribers safely from any thread."""
        payload = {"type": event_type, "data": data}
        for q in list(self.subscribers):
            try:
                q.put_nowait(payload)
            except Exception:
                pass


def create_app(token: Optional[str] = None, config: Optional[Config] = None) -> FastAPI:
    """Create FastAPI application with security middleware and static assets."""
    server_token = token or secrets.token_hex(16)
    manager = ServerManager(token=server_token, config=config)

    app = FastAPI(title="SubTrans Auto Web Server")
    app.state.manager = manager
    app.state.server_token = server_token

    # 1. Security Middleware (Host, Origin, and Token enforcement)
    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # 1. Host check: only 127.0.0.1 or localhost
        host_header = request.headers.get("host", "").split(":")[0].lower()
        if host_header not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse(status_code=403, content={"detail": "دسترسی غیرمجاز (Host نامعتبر است)."})

        # 2. Origin check: must be localhost/127.0.0.1 if present
        origin = request.headers.get("origin")
        if origin:
            origin_host = origin.split("://")[-1].split(":")[0].lower()
            if origin_host not in ("127.0.0.1", "localhost", "testserver"):
                return JSONResponse(status_code=403, content={"detail": "دسترسی غیرمجاز (Origin نامعتبر است)."})

        # 3. Token check for modifying methods (POST, PUT, DELETE) and API calls
        path = request.url.path
        if request.method in ("POST", "PUT", "DELETE") or (path.startswith("/api/") and path != "/api/status"):
            query_token = request.query_params.get("token")
            header_token = request.headers.get("x-subtrans-token")
            cookie_token = request.cookies.get("subtrans_token")

            provided = header_token or query_token or cookie_token
            if not provided or not secrets.compare_digest(provided, app.state.server_token):
                return JSONResponse(status_code=403, content={"detail": "توکن امنیتی نامعتبر است یا ارسال نشده است."})

        response = await call_next(request)

        # Set cookie on root access if token was in query parameter
        if path == "/" and "token" in request.query_params:
            tok = request.query_params["token"]
            if secrets.compare_digest(tok, app.state.server_token):
                response.set_cookie(
                    key="subtrans_token",
                    value=tok,
                    httponly=True,
                    samesite="strict",
                )

        return response

    # 2. API Routes
    @app.get("/api/config")
    async def get_configuration():
        cfg = app.state.manager.cfg
        return cfg.to_dict(mask_secrets=True)

    @app.post("/api/config")
    async def update_configuration(new_cfg_data: Dict[str, Any]):
        curr_cfg = load_config()
        # Preserve real API key if masked string was submitted back
        provider_dict = new_cfg_data.get("provider") or {}
        incoming_key = provider_dict.get("api_key", "") if isinstance(provider_dict, dict) else ""
        if incoming_key and "..." in incoming_key:
            new_cfg_data.setdefault("provider", {})["api_key"] = curr_cfg.provider.api_key

        updated_cfg = Config.from_dict(new_cfg_data)
        save_config(updated_cfg)
        app.state.manager.cfg = updated_cfg
        return {"status": "ok", "config": updated_cfg.to_dict(mask_secrets=True)}

    @app.post("/api/test-connection")
    async def test_connection(data: Optional[Dict[str, Any]] = None):
        cfg = app.state.manager.cfg
        base_url = (data.get("base_url") if data else None) or cfg.provider.base_url
        api_key = (data.get("api_key") if data else None) or cfg.provider.api_key
        if api_key and "..." in api_key:
            api_key = cfg.provider.api_key

        is_local = "127.0.0.1" in base_url or "localhost" in base_url
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        models_url = f"{base_url.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=6.0, trust_env=not is_local) as client:
                resp = await client.get(models_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models_list = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
                    return {"ok": True, "message": f"اتصال برقرار است ({len(models_list)} مدل یافت شد).", "models": models_list}
                else:
                    return {"ok": False, "message": f"پاسخ سرور: کد {resp.status_code} ({resp.text[:100]})"}
        except Exception as e:
            return {"ok": False, "message": f"خطا در اتصال: {type(e).__name__}"}

    @app.post("/api/fetch-models")
    async def fetch_models():
        res = await test_connection()
        if res.get("ok"):
            return {"models": res.get("models", [])}
        raise HTTPException(status_code=400, detail=res.get("message", "دریافت مدل‌ها ناموفق بود."))

    @app.post("/api/pick-folder")
    async def pick_folder():
        """Launch native folder picker dialog in a separate subprocess so server is never blocked."""
        script = (
            "import tkinter as tk, tkinter.filedialog as fd\n"
            "root = tk.Tk()\n"
            "root.withdraw()\n"
            "root.attributes('-topmost', True)\n"
            "path = fd.askdirectory()\n"
            "if path: print(path)\n"
        )
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            selected = proc.stdout.strip()
            return {"path": selected if selected else ""}
        except Exception as e:
            return {"path": "", "error": str(e)}

    @app.post("/api/scan")
    async def scan_inputs(payload: Dict[str, Any]):
        target_path_str = payload.get("path", "")
        if not target_path_str:
            raise HTTPException(status_code=400, detail="مسیر ورودی الزامی است.")

        target = Path(target_path_str)
        if not target.exists():
            raise HTTPException(status_code=404, detail="مسیر مورد نظر یافت نشد.")

        cfg = app.state.manager.cfg
        tasks = discover_inputs(target, overwrite_existing=cfg.general.overwrite_existing, target_lang=cfg.general.target_lang)

        results = []
        for t in tasks:
            item_info = {
                "name": t.path.name,
                "path": str(t.path),
                "is_video": t.is_video,
                "tracks": [],
            }
            if t.is_video:
                try:
                    tracks = probe_subtitles(t.path)
                    item_info["tracks"] = [
                        {
                            "index": tr.index,
                            "codec": tr.codec_name,
                            "lang": tr.language,
                            "title": tr.title,
                            "is_bitmap": tr.is_bitmap,
                        }
                        for tr in tracks
                    ]
                except Exception:
                    pass
            results.append(item_info)

        return {"files": results, "count": len(results)}

    @app.post("/api/estimate")
    async def estimate_job(payload: Dict[str, Any]):
        """Calculate dry-run estimation of lines and expected API calls before starting."""
        target_path_str = payload.get("path", "")
        if not target_path_str:
            raise HTTPException(status_code=400, detail="مسیر الزامی است.")
        target = Path(target_path_str)
        if not target.exists():
            raise HTTPException(status_code=404, detail="مسیر پیدا نشد.")

        cfg = app.state.manager.cfg
        pipeline = Pipeline(config=cfg)
        tasks = pipeline.run(input_path=target, dry_run=True)

        return {
            "total_files": len(tasks),
            "estimated_calls": len(tasks) * 5,  # Rough estimate
            "message": f"{len(tasks)} فایل آماده ترجمه است.",
        }

    @app.get("/api/status")
    async def get_job_status():
        m = app.state.manager
        with m._lock:
            return {
                "job_id": m.job.job_id,
                "status": m.job.status,
                "tasks": m.job.tasks,
                "logs": m.job.logs[-100:],
                "stats": m.job.stats,
                "token": app.state.server_token,
            }

    @app.post("/api/start")
    async def start_job(payload: Dict[str, Any]):
        m = app.state.manager
        path_str = payload.get("path", "")
        if not path_str:
            raise HTTPException(status_code=400, detail="مسیر ورودی تعیین نشده است.")

        target = Path(path_str)
        if not target.exists():
            raise HTTPException(status_code=404, detail="مسیر پیدا نشد.")

        with m._lock:
            if m.job.status == "RUNNING":
                return {"status": "already_running"}

            job_id = f"web_{target.stem}_{secrets.token_hex(4)}"
            m.job.job_id = job_id
            m.job.status = "RUNNING"
            m.job.is_paused = False
            m.job.tasks = []
            m.job.logs.clear()

        # Run pipeline in background thread
        def worker():
            m.log(f"شروع پردازش مسیر: {target}")
            pipeline = Pipeline(config=m.cfg)

            def on_event(task: FileTask, stage: Stage, status: StageStatus, msg: str):
                if m.job.is_paused:
                    m.log("عملیات موقتاً متوقف شد (Paused).")
                    m.job.status = "PAUSED"

                # Update in-memory tasks list
                task_dict = {
                    "name": task.path.name,
                    "stages": dict(task.stages),
                    "messages": dict(task.messages),
                    "error": task.error,
                }
                with m._lock:
                    found = False
                    for i, t in enumerate(m.job.tasks):
                        if t["name"] == task.path.name:
                            m.job.tasks[i] = task_dict
                            found = True
                            break
                    if not found:
                        m.job.tasks.append(task_dict)

                m.log(f"[{status.value}] {task.path.name} | {stage.value}: {msg}")
                m.broadcast_sync("task_update", task_dict)

            try:
                finished_tasks = pipeline.run(input_path=target, job_id=job_id, on_event=on_event)
                with m._lock:
                    m.job.status = "COMPLETED"
                    m.log("پردازش تمامی فایل‌ها با موفقیت پایان یافت.")
                m.broadcast_sync("job_completed", {"job_id": job_id})
            except Exception as e:
                with m._lock:
                    m.job.status = "FAILED"
                    m.log(f"خطای پایپ‌لاین: {e}")
                m.broadcast_sync("job_failed", {"error": str(e)})

        t = threading.Thread(target=worker, daemon=True)
        m.job.thread = t
        t.start()
        return {"status": "started", "job_id": job_id}

    @app.post("/api/pause")
    async def pause_job():
        m = app.state.manager
        with m._lock:
            m.job.is_paused = True
            m.job.status = "PAUSED"
            m.log("درخواست توقف عملیات ثبت شد.")
        return {"status": "paused"}

    @app.post("/api/resume")
    async def resume_job(payload: Optional[Dict[str, Any]] = None):
        m = app.state.manager
        if m.job.status == "PAUSED":
            with m._lock:
                m.job.is_paused = False
                m.job.status = "RUNNING"
                m.log("ادامه عملیات...")
        return {"status": "resumed"}

    @app.get("/api/events")
    async def sse_events(request: Request):
        """Server-Sent Events stream for live progress updates."""
        queue: asyncio.Queue = asyncio.Queue()
        m = app.state.manager
        m.subscribers.append(queue)

        async def event_generator():
            try:
                # Send initial state
                init_data = {"type": "init", "token": app.state.server_token}
                yield f"data: {json.dumps(init_data, ensure_ascii=False)}\n\n"

                if request.headers.get("x-test-once") == "true":
                    return

                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        # Heartbeat ping
                        yield ": ping\n\n"
            finally:
                if queue in m.subscribers:
                    m.subscribers.remove(queue)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 3. Mount static files directory
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index_page(token: Optional[str] = Query(None)):
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            html_content = index_file.read_text(encoding="utf-8")
            return HTMLResponse(content=html_content)
        return HTMLResponse(content="<h1>SubTrans Auto UI</h1>")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    """Run the local web UI server and open the browser."""
    import uvicorn
    import webbrowser

    chosen_port = find_free_port(port)
    secret_token = secrets.token_hex(16)
    app = create_app(token=secret_token)

    url = f"http://{host}:{chosen_port}/?token={secret_token}"
    print(f"=== وب‌سرور محلی SubTrans Auto اجرا شد ===")
    print(f"آدرس مرورگر: {url}")
    print("------------------------------------------")

    if open_browser:
        def opener():
            import time
            time.sleep(1.0)
            webbrowser.open(url)
        threading.Thread(target=opener, daemon=True).start()

    uvicorn.run(app, host=host, port=chosen_port, log_level="info")

