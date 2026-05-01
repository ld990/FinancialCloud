from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from kubernetes.config.config_exception import ConfigException

from services.k8s_service import K8sService
from services.user_store import (
	create_user,
	get_user_by_id,
	init_user_store,
	list_users,
	update_user_role,
	update_user_status,
	verify_user,
)


class LoginRequest(BaseModel):
	username: str
	password: str


class LoginResponse(BaseModel):
	token: str
	username: str
	role: str
	status: str


class RegisterRequest(BaseModel):
	username: str
	password: str
	display_name: str


class CreateUserRequest(BaseModel):
	username: str
	password: str
	display_name: str
	role: str = "viewer"
	status: str = "approved"


class UpdateUserStatusRequest(BaseModel):
	status: str  # approved/rejected/pending


class UpdateUserRoleRequest(BaseModel):
	role: str  # admin/auditor/viewer


class ClusterCreateRequest(BaseModel):
	name: str
	api_server: str
	description: str = ""
	kubeconfig_yaml: str = ""


app = FastAPI(title="金融K8s容器安全基线与可视化平台 - API")

# 开发环境允许跨域（可按需收紧）
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.exception_handler(ConfigException)
async def _k8s_config_exception_handler(_: Request, exc: ConfigException):
	# 将 K8s 配置错误转为可读的 503，避免前端因 500 + 无 CORS 头而被浏览器拦截
	return JSONResponse(
		status_code=503,
		content={
			"detail": "Kubernetes 未配置或 kubeconfig 无效。请设置环境变量 KUBECONFIG_PATH 指向有效 kubeconfig 文件。",
			"error": str(exc),
		},
	)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(_: Request, exc: Exception):
	# 兜底异常，保证返回 JSON（也便于 CORS 中间件附加响应头）
	return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "error": str(exc)})

# 简单的 Token 模拟登录态（内存态，重启后失效）
_TOKENS: Dict[str, Dict[str, Any]] = {}
_TOKEN_TTL_SEC = 3600  # 当前未实现过期清理，保留接口扩展位

_k8s_service: Optional[K8sService] = None
_k8s_services_by_cluster: Dict[int, K8sService] = {}
_CLUSTERS: List[Dict[str, Any]] = []
_NEXT_CLUSTER_ID = 1

# 外部链接配置（内存存储，重启后恢复默认）
_EXTERNAL_LINKS = {
    'kiali': 'http://192.168.3.254:31523',
    'grafana': 'http://192.168.3.254:31765',
    'prometheus': 'http://192.168.3.254:32558',
    'alertmanager': ''
}


def _get_default_k8s_service() -> K8sService:
	"""
	延迟初始化 K8sService，避免在 kubeconfig 不存在/不可读时模块导入失败。
	"""
	global _k8s_service
	if _k8s_service is not None:
		return _k8s_service

	kubeconfig_path = os.getenv("KUBECONFIG_PATH", "/etc/rancher/k3s/k3s.yaml")
	try:
		_k8s_service = K8sService(
			kubeconfig_path=kubeconfig_path,
			events_poll_interval_sec=2.0,
			events_watch_timeout_sec=60,
		)
	except ConfigException:
		# 直接抛给上层 handler，返回 503 + 友好提示
		raise
	except Exception as exc:
		raise HTTPException(status_code=503, detail=f"K8s 初始化失败：{exc}")
	return _k8s_service


def _get_selected_cluster_id(token: str) -> Optional[int]:
	user = _TOKENS.get(token, {})
	cid = user.get("cluster_id")
	try:
		return int(cid) if cid is not None else None
	except Exception:
		return None


def _get_cluster_by_id(cluster_id: int) -> Optional[Dict[str, Any]]:
	for c in _CLUSTERS:
		if c.get("id") == cluster_id:
			return c
	return None


def _get_k8s_service_for_token(token: str) -> K8sService:
	cid = _get_selected_cluster_id(token)
	if not cid:
		return _get_default_k8s_service()

	cluster = _get_cluster_by_id(cid)
	if not cluster:
		return _get_default_k8s_service()

	if cid in _k8s_services_by_cluster:
		return _k8s_services_by_cluster[cid]

	kubeconfig_yaml = (cluster.get("kubeconfig_yaml") or "").strip()
	if not kubeconfig_yaml:
		raise HTTPException(status_code=400, detail="该集群未配置 kubeconfig，无法连接")

	try:
		svc = K8sService(
			kubeconfig_yaml=kubeconfig_yaml,
			events_poll_interval_sec=2.0,
			events_watch_timeout_sec=60,
		)
	except Exception as exc:
		raise HTTPException(status_code=400, detail=f"kubeconfig 加载失败：{exc}")

	_k8s_services_by_cluster[cid] = svc
	return svc


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
	if not authorization:
		return None
	parts = authorization.split()
	if len(parts) == 2 and parts[0].lower() == "bearer":
		return parts[1]
	return None


def require_token(request: Request, authorization: Optional[str] = Header(None)) -> str:
	"""
	从 Authorization: Bearer <token> 或 /k8s/events?token=<token> 获取 token。
	"""
	token = _extract_bearer_token(authorization)
	if not token:
		token = request.query_params.get("token")
	if not token or token not in _TOKENS:
		raise HTTPException(status_code=401, detail="Unauthorized")
	return token


def require_admin(token: str = Depends(require_token)) -> str:
	user = _TOKENS.get(token, {})
	if user.get("role") != "admin":
		raise HTTPException(status_code=403, detail="Forbidden")
	return token


def _normalize_cluster_name(name: str) -> str:
	return " ".join((name or "").strip().split())


def _patch_kubeconfig_server(kubeconfig_yaml: str, api_server: str) -> str:
	"""
	将 kubeconfig 中的 cluster.server 统一覆盖为表单里的 API 地址，
	避免用户填了正确 API 但 YAML 仍是 127.0.0.1 导致连错目标。
	"""
	content = (kubeconfig_yaml or "").strip()
	server = (api_server or "").strip()
	if not content or not server:
		return content
	try:
		import yaml  # type: ignore
	except Exception:
		return content
	try:
		cfg = yaml.safe_load(content)
		if not isinstance(cfg, dict):
			return content
		clusters = cfg.get("clusters")
		if isinstance(clusters, list):
			for item in clusters:
				if isinstance(item, dict):
					cluster = item.get("cluster")
					if isinstance(cluster, dict):
						cluster["server"] = server
		return yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
	except Exception:
		return content


@app.on_event("startup")
def on_startup() -> None:
	init_user_store()


@app.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
	user = verify_user(body.username, body.password)
	if not user:
		raise HTTPException(status_code=401, detail="Invalid credentials")
	if user.get("status") != "approved":
		raise HTTPException(status_code=403, detail="账号待审核，请联系管理员审批后登录")

	token = secrets.token_urlsafe(32)
	_TOKENS[token] = {
		"user_id": str(user["id"]),
		"username": user["username"],
		"display_name": user["display_name"],
		"role": user["role"],
		"status": user["status"],
		"cluster_id": None,
	}
	return LoginResponse(
		token=token,
		username=user["username"],
		role=user["role"],
		status=user["status"],
	)


@app.post("/auth/register")
async def register(body: RegisterRequest) -> Dict[str, Any]:
	username = body.username.strip()
	display_name = body.display_name.strip()
	if len(username) < 3:
		raise HTTPException(status_code=400, detail="Username too short")
	if len(body.password) < 6:
		raise HTTPException(status_code=400, detail="Password too short")
	if not display_name:
		raise HTTPException(status_code=400, detail="Display name is required")
	try:
		user_id = create_user(
			username=username,
			password=body.password,
			display_name=display_name,
			role="viewer",
			status="pending",
		)
		return {"ok": True, "user_id": user_id, "status": "pending"}
	except sqlite3.IntegrityError:
		raise HTTPException(status_code=409, detail="Username already exists")


@app.post("/auth/logout")
async def logout(token: str = Depends(require_token)) -> Dict[str, Any]:
	_TOKENS.pop(token, None)
	return {"ok": True}

@app.get("/auth/me")
async def auth_me(token: str = Depends(require_token)) -> Dict[str, Any]:
	user = _TOKENS.get(token, {})
	return {
		"user_id": user.get("user_id", ""),
		"username": user.get("username", ""),
		"display_name": user.get("display_name", ""),
		"role": user.get("role", ""),
		"status": user.get("status", ""),
		"cluster_id": user.get("cluster_id", None),
	}


@app.get("/clusters")
async def list_clusters(token: str = Depends(require_token)) -> Dict[str, Any]:
	return {"clusters": _CLUSTERS}


@app.post("/clusters")
async def create_cluster(body: ClusterCreateRequest, token: str = Depends(require_admin)) -> Dict[str, Any]:
	global _NEXT_CLUSTER_ID
	name = _normalize_cluster_name(body.name)
	api_server = (body.api_server or "").strip()
	description = (body.description or "").strip()
	kubeconfig_yaml = (body.kubeconfig_yaml or "").strip()
	if not name:
		raise HTTPException(status_code=400, detail="Cluster name is required")
	if not api_server:
		raise HTTPException(status_code=400, detail="API server is required")
	if not (api_server.startswith("http://") or api_server.startswith("https://")):
		raise HTTPException(status_code=400, detail="API server must start with http:// or https://")

	if any(_normalize_cluster_name(item.get("name", "")) == name for item in _CLUSTERS):
		raise HTTPException(status_code=409, detail="Cluster name already exists")

	# 将 kubeconfig 的 server 与 API 地址保持一致，避免 127.0.0.1/localhost 误配
	kubeconfig_yaml = _patch_kubeconfig_server(kubeconfig_yaml, api_server)

	cluster = {
		"id": _NEXT_CLUSTER_ID,
		"name": name,
		"api_server": api_server,
		"description": description,
		"kubeconfig_yaml": kubeconfig_yaml,
	}
	_NEXT_CLUSTER_ID += 1
	_CLUSTERS.append(cluster)
	return {"ok": True, "cluster": cluster}


@app.post("/clusters/{cluster_id}/select")
async def select_cluster(cluster_id: int, token: str = Depends(require_token)) -> Dict[str, Any]:
	if cluster_id == 0:
		_TOKENS[token]["cluster_id"] = None
		return {"ok": True, "cluster_id": None}
	cluster = _get_cluster_by_id(cluster_id)
	if not cluster:
		raise HTTPException(status_code=404, detail="Cluster not found")
	_TOKENS[token]["cluster_id"] = cluster_id
	return {"ok": True, "cluster_id": cluster_id}


@app.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: int, token: str = Depends(require_admin)) -> Dict[str, Any]:
	for idx, item in enumerate(_CLUSTERS):
		if item.get("id") == cluster_id:
			_CLUSTERS.pop(idx)
			_k8s_services_by_cluster.pop(cluster_id, None)
			return {"ok": True}
	raise HTTPException(status_code=404, detail="Cluster not found")


@app.get("/users")
async def users_list(token: str = Depends(require_admin)) -> Dict[str, Any]:
	return {"users": list_users()}


@app.post("/users")
async def users_create(body: CreateUserRequest, token: str = Depends(require_admin)) -> Dict[str, Any]:
	username = body.username.strip()
	display_name = body.display_name.strip()
	if len(username) < 3:
		raise HTTPException(status_code=400, detail="Username too short")
	if len(body.password) < 6:
		raise HTTPException(status_code=400, detail="Password too short")
	if body.role not in ("admin", "auditor", "viewer"):
		raise HTTPException(status_code=400, detail="Invalid role")
	if body.status not in ("approved", "pending", "rejected"):
		raise HTTPException(status_code=400, detail="Invalid status")
	try:
		user_id = create_user(
			username=username,
			password=body.password,
			display_name=display_name or username,
			role=body.role,
			status=body.status,
		)
		return {"ok": True, "user_id": user_id}
	except sqlite3.IntegrityError:
		raise HTTPException(status_code=409, detail="Username already exists")


@app.patch("/users/{user_id}/status")
async def users_update_status(user_id: int, body: UpdateUserStatusRequest, token: str = Depends(require_admin)) -> Dict[str, Any]:
	if body.status not in ("approved", "pending", "rejected"):
		raise HTTPException(status_code=400, detail="Invalid status")
	ok = update_user_status(user_id, body.status)
	if not ok:
		raise HTTPException(status_code=404, detail="User not found")
	return {"ok": True}


@app.patch("/users/{user_id}/role")
async def users_update_role(user_id: int, body: UpdateUserRoleRequest, token: str = Depends(require_admin)) -> Dict[str, Any]:
	if body.role not in ("admin", "auditor", "viewer"):
		raise HTTPException(status_code=400, detail="Invalid role")
	user = get_user_by_id(user_id)
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	ok = update_user_role(user_id, body.role)
	if not ok:
		raise HTTPException(status_code=404, detail="User not found")
	return {"ok": True}


@app.get("/k8s/overview")
async def k8s_overview(token: str = Depends(require_token)) -> Dict[str, Any]:
	# token 仅用于鉴权；数据仍由 kubernetes SDK 实时采集
	try:
		return await run_in_threadpool(_get_k8s_service_for_token(token).get_overview)
	except Exception as exc:
		return {
			"totalPods": 0,
			"normalPods": 0,
			"riskPods": 0,
			"score": 0,
			"error": str(exc),
		}


@app.get("/k8s/overview/components")
async def k8s_overview_components(token: str = Depends(require_token)) -> Dict[str, Any]:
	try:
		return await run_in_threadpool(_get_k8s_service_for_token(token).get_overview_components)
	except Exception as exc:
		return {"updated_at": "", "components": [], "error": str(exc)}


@app.get("/k8s/audit")
async def k8s_audit(
	token: str = Depends(require_token),
	max_fix_pods: int = 50,
	default_cpu: str = "500m",
	default_memory: str = "512Mi",
) -> List[Dict[str, Any]]:
	try:
		return await run_in_threadpool(
			_get_k8s_service_for_token(token).get_audit,
			max_fix_pods=max_fix_pods,
			default_cpu=default_cpu,
			default_memory=default_memory,
		)
	except Exception:
		return []


@app.get("/k8s/resources/usage")
async def k8s_resources_usage(token: str = Depends(require_token)) -> Dict[str, Any]:
	try:
		return await run_in_threadpool(_get_k8s_service_for_token(token).get_resources_usage)
	except Exception as exc:
		return {"items": [], "error": str(exc)}


@app.get("/k8s/resources/node-top")
async def k8s_node_top_usage(token: str = Depends(require_token)) -> Dict[str, Any]:
	try:
		return await run_in_threadpool(_get_k8s_service_for_token(token).get_node_top_usage)
	except Exception as exc:
		return {"nodes": [], "error": str(exc)}


@app.get("/k8s/security/advanced-scan")
async def k8s_advanced_scan(token: str = Depends(require_token)) -> Dict[str, Any]:
	return await run_in_threadpool(_get_k8s_service_for_token(token).get_security_advanced_scan)


@app.get("/k8s/security/supply-chain")
async def k8s_supply_chain_scan(token: str = Depends(require_token)) -> Dict[str, Any]:
	return await run_in_threadpool(_get_k8s_service_for_token(token).get_supply_chain_scan)


@app.get("/k8s/security/supply-chain/unused")
async def k8s_supply_chain_unused(token: str = Depends(require_token)) -> Dict[str, Any]:
	"""
	残留/无用镜像扫描（识别 + 建议命令）。
	需要权限：list nodes。
	"""
	try:
		return await run_in_threadpool(_get_k8s_service_for_token(token).get_unused_images_scan)
	except Exception as exc:
		return {"scanned_at": "", "unused_images": [], "error": str(exc)}


@app.get("/k8s/security/top-alerts")
async def k8s_top_alerts(token: str = Depends(require_token), limit: int = 5) -> Dict[str, Any]:
	# 对可能出现的 Kubernetes 权限/连通性异常做降级，避免前端 500
	try:
		alerts = await run_in_threadpool(_get_k8s_service_for_token(token).get_top_alerts, limit)
		return {"alerts": alerts}
	except Exception as exc:
		# 返回空列表并带上简要错误信息，便于前端可视化降级
		return {"alerts": [], "error": str(exc)}


@app.get("/k8s/fix/patch")
async def k8s_fix_patch(
	token: str = Depends(require_token),
	risk_type: str = "resource_limits",  # resource_limits|privileged|hostpath
	max_items: int = 6,
	default_cpu: str = "500m",
	default_memory: str = "512Mi",
) -> Dict[str, Any]:
	try:
		bundle = await run_in_threadpool(
			_get_k8s_service_for_token(token).get_fix_patch_bundle,
			risk_type,
			max_items,
			default_cpu,
			default_memory,
		)
		return {"bundle": bundle}
	except Exception as exc:
		return {"bundle": {}, "error": str(exc)}


@app.get("/k8s/reports/weekly-preview")
async def k8s_weekly_report_preview(token: str = Depends(require_token)) -> Dict[str, Any]:
	html = await run_in_threadpool(_get_k8s_service_for_token(token).get_weekly_report_preview)
	return {"html": html}


@app.get("/k8s/reports/weekly-csv")
async def k8s_weekly_report_csv(token: str = Depends(require_token)) -> Dict[str, Any]:
	csv_text = await run_in_threadpool(_get_k8s_service_for_token(token).get_weekly_report_csv)
	return {"csv": csv_text}


@app.get("/k8s/events")
def k8s_events(
	token: str = Depends(require_token),
	limit: int = 200,
) -> StreamingResponse:
	"""
	SSE 推送 K8s Events（真实 SDK 采集）。
	前端按时间倒序展示。
	"""

	def _event_generator():
		svc = _get_k8s_service_for_token(token)
		# 先推送一批最近事件快照，避免页面初次打开为空
		try:
			snapshot = svc._get_events_snapshot(limit=limit)
			for payload in snapshot:
				yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
		except Exception:
			# 快照失败不阻断实时流
			pass

		# 再持续推送实时事件流
		for payload in svc.stream_events(limit=limit):
			# SSE 格式：data: <json>\n\n
			yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

	# SSE 的内容类型
	return StreamingResponse(_event_generator(), media_type="text/event-stream")


@app.get("/k8s/events/snapshot")
async def k8s_events_snapshot(
	token: str = Depends(require_token),
	limit: int = 200,
) -> Dict[str, Any]:
	"""
	返回最近事件快照（JSON），用于前端进入页面时先展示历史数据。
	"""
	try:
		events = await run_in_threadpool(_get_k8s_service_for_token(token)._get_events_snapshot, limit)
		return {"events": events}
	except Exception as exc:
		return {"events": [], "error": str(exc)}


@app.get("/healthz")
def healthz() -> Dict[str, str]:
	return {"ok": "true"}


# 文件上传相关
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    token: str = Depends(require_token)
) -> Dict[str, Any]:
    """上传图片文件"""
    # 检查文件类型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只允许上传图片文件")
    
    # 生成安全文件名
    file_ext = Path(file.filename).suffix if file.filename else ".jpg"
    safe_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = UPLOAD_DIR / safe_filename
    
    # 保存文件
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    # 返回访问 URL
    return {
        "filename": safe_filename,
        "url": f"/uploads/{safe_filename}"
    }


class ExternalLinkUpdate(BaseModel):
    kiali: str = ''
    grafana: str = ''
    prometheus: str = ''
    alertmanager: str = ''


@app.get("/config/external-links")
async def get_external_links(token: str = Depends(require_token)) -> Dict[str, Any]:
    """获取外部链接配置"""
    return {"links": _EXTERNAL_LINKS}


@app.post("/config/external-links")
@app.put("/config/external-links")
async def update_external_links(data: ExternalLinkUpdate, token: str = Depends(require_admin)) -> Dict[str, Any]:
    """更新外部链接配置（仅管理员）"""
    global _EXTERNAL_LINKS
    _EXTERNAL_LINKS = {
        'kiali': data.kiali,
        'grafana': data.grafana,
        'prometheus': data.prometheus,
        'alertmanager': data.alertmanager
    }
    return {"ok": True, "links": _EXTERNAL_LINKS}

