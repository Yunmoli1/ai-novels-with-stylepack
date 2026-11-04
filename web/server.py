# -*- coding: utf-8 -*-
"""server：工作台 FastAPI 应用（v0.6.0）。

- 静态站点（阶段 0 产物）挂在 /，动态页与 API 在 /app/*
- 只经 launch.py 绑 127.0.0.1（红线 1；此处不监听，不自行起服务）
- 模型 key 只在服务端内存/配置文件，页面永不回显（红线 5）
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(ROOT / "scripts"))

import appstate  # noqa: E402
import routes_create  # noqa: E402
import routes_distill  # noqa: E402
import routes_memory  # noqa: E402
import routes_bible  # noqa: E402
import routes_history  # noqa: E402
import routes_serial  # noqa: E402

TEMPLATES = Jinja2Templates(directory=str(WEB / "templates"))


def create_app(site_dir: Path | None = None) -> FastAPI:
    site = Path(site_dir) if site_dir else WEB / "site"
    app = FastAPI(title="StylePack 工作台", docs_url=None, redoc_url=None)
    app.include_router(routes_create.router)
    app.include_router(routes_distill.router)
    app.include_router(routes_memory.router)
    app.include_router(routes_bible.router)
    app.include_router(routes_history.router)
    app.include_router(routes_serial.router)
    app.mount("/static", StaticFiles(directory=str(WEB / "static")),
              name="static")

    @app.get("/app/history")
    async def history_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request, name="history.html",
            context={"active": "history",
                     "version": appstate.workbench_version()})

    @app.get("/app/bible")
    async def bible_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request, name="bible.html",
            context={"active": "bible",
                     "version": appstate.workbench_version()})

    @app.get("/app/config")
    async def config_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request, name="config.html", context={"active": "config",
                                                  "version": appstate.workbench_version()})

    @app.get("/app/create")
    async def create_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request, name="create.html", context={"active": "create",
                                                  "version": appstate.workbench_version()})

    @app.get("/app/serial")
    async def serial_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request, name="serial.html", context={"active": "serial",
                                                  "version": appstate.workbench_version()})

    @app.get("/app/distill")
    async def distill_page(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request, name="distill.html", context={"active": "distill",
                                                  "version": appstate.workbench_version()})

    if (site / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(site), html=True), name="site")
    return app


def main() -> int:  # 供测试/直启；常规入口是 launch.py
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
