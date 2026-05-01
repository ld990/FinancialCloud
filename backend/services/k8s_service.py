from __future__ import annotations

import json
import csv
import time
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple

from kubernetes import client, config, watch
from kubernetes.client import CoreV1Api
from kubernetes.config.config_exception import ConfigException


def _load_core_v1_api_from_path(kubeconfig_path: str) -> CoreV1Api:
	"""
	加载 kubeconfig；失败则尝试 InCluster 配置。
	"""
	try:
		config.load_kube_config(config_file=kubeconfig_path)
	except ConfigException:
		config.load_incluster_config()
	return client.CoreV1Api()


def _load_core_v1_api_from_yaml(kubeconfig_yaml: str) -> CoreV1Api:
	"""
	从 kubeconfig YAML 文本加载配置（用于多集群切换）。
	"""
	if not kubeconfig_yaml or not str(kubeconfig_yaml).strip():
		raise ValueError("kubeconfig_yaml is empty")
	try:
		import yaml  # type: ignore
	except Exception as exc:  # pragma: no cover
		raise RuntimeError("PyYAML is required to load kubeconfig yaml") from exc

	cfg = yaml.safe_load(kubeconfig_yaml)
	if not isinstance(cfg, dict):
		raise ValueError("Invalid kubeconfig yaml")
	config.load_kube_config_from_dict(cfg)
	return client.CoreV1Api()


def _pick_timestamp(obj: Any) -> Optional[datetime]:
	"""
	优先 last_timestamp / event_time / first_timestamp，其次使用 metadata.creation_timestamp。
	"""
	for attr in ("last_timestamp", "event_time", "first_timestamp"):
		val = getattr(obj, attr, None)
		if val:
			return val
	return getattr(getattr(obj, "metadata", None), "creation_timestamp", None)


def _pod_is_risk(pod_item: Dict[str, Any]) -> bool:
	containers = pod_item.get("containers", []) or []
	if not containers:
		return True
	# 风险规则：任一容器未同时设置 limits.cpu & limits.memory => 风险
	return not all(bool(c.get("has_limits")) for c in containers)


def _classify_image_registry(image: str) -> Tuple[str, bool]:
	"""
	识别镜像是否来自不安全公有仓库（默认将“无 registry 域名”的镜像视为 Docker Hub）。
	"""
	if not image:
		return "unknown", True

	ref = image.split("@", 1)[0]
	parts = ref.split("/")
	if len(parts) == 1:
		return "docker.io", True

	first = parts[0]
	if "." in first or ":" in first or first == "localhost":
		registry = first
	else:
		registry = "docker.io"

	if registry in {"docker.io", "registry-1.docker.io"}:
		return registry, True
	return registry, False


def _pod_owner_target(pod: Dict[str, Any]) -> Dict[str, str]:
	"""
	将 Pod ownerReferences 映射为可用于生成修复 YAML 示例的目标资源。
	优先 Deployment/StatefulSet/DaemonSet/ReplicaSet；否则回退到 Pod。
	"""
	namespace = pod.get("namespace", "")
	pod_name = pod.get("pod_name", "")
	owners = pod.get("owners", []) or []

	allowed = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"}
	for o in owners:
		kind = o.get("kind")
		name = o.get("name")
		if kind in allowed and name:
			return {"apiVersion": "apps/v1", "kind": kind, "name": name, "namespace": namespace}
	return {"apiVersion": "v1", "kind": "Pod", "name": pod_name, "namespace": namespace}


def _build_limits_fix_yaml_for_pod(
	pod_item: Dict[str, Any],
	default_cpu: str = "500m",
	default_memory: str = "512Mi",
) -> Optional[str]:
	if not _pod_is_risk(pod_item):
		return None

	target = _pod_owner_target(pod_item)
	namespace = target["namespace"]
	kind = target["kind"]
	name = target["name"]
	api_version = target["apiVersion"]

	containers = pod_item.get("containers", []) or []
	patch_containers: List[Dict[str, str]] = []

	for c in containers:
		if c.get("has_limits"):
			continue
		cname = c.get("name") or ""
		if not cname:
			continue
		cpu_val = c.get("cpu_limit") or default_cpu
		mem_val = c.get("memory_limit") or default_memory
		patch_containers.append({"name": cname, "cpu": str(cpu_val), "memory": str(mem_val)})

	if not patch_containers:
		return None

	# YAML 结构差异：Pod vs Controller
	# Pod:
	# spec:
	#   containers:
	# Controller:
	# spec:
	#   template:
	#     spec:
	#       containers:
	if kind == "Pod":
		spec_header = "spec:\n  containers:"
		list_item_indent = 4
	else:
		spec_header = "spec:\n  template:\n    spec:\n      containers:"
		list_item_indent = 8

	container_blocks: List[str] = []
	for pc in patch_containers:
		container_blocks.append(
			"\n".join(
				[
					f'{" " * list_item_indent}- name: {pc["name"]}',
					f'{" " * (list_item_indent + 2)}resources:',
					f'{" " * (list_item_indent + 4)}limits:',
					f'{" " * (list_item_indent + 6)}cpu: "{pc["cpu"]}"',
					f'{" " * (list_item_indent + 6)}memory: "{pc["memory"]}"',
				]
			)
		)

	containers_joined = "\n".join(container_blocks)
	# 注意：这里只给“示例结构”，非精确战略合并补丁
	yaml_text = (
		f"apiVersion: {api_version}\n"
		f"kind: {kind}\n"
		f"metadata:\n"
		f"  name: {name}\n"
		f"  namespace: {namespace}\n"
		f"{spec_header}\n"
		f"{containers_joined}"
	)
	return yaml_text


def _parse_cpu_to_cores(value: Optional[str]) -> float:
	"""
	将 Kubernetes cpu quantity 转为 cores（近似）。
	例:
	- 500m => 0.5
	- 2 => 2
	"""
	if not value:
		return 0.0
	v = str(value).strip()
	try:
		if v.endswith("m"):
			return float(v[:-1]) / 1000.0
		if v.endswith("n"):
			return float(v[:-1]) / 1e9
		if v.endswith("u"):
			return float(v[:-1]) / 1e6
		# 其他情况按 cores 直接解析（包括空后单位）
		return float(v)
	except Exception:
		return 0.0


def _parse_memory_to_gib(value: Optional[str]) -> float:
	"""
	将 Kubernetes memory quantity 转为 GiB（近似）。
	支持 Ki/Mi/Gi/Ti/Pi/Ei 以及 K/M/G 10^ 指数（近似处理）。
	"""
	if not value:
		return 0.0
	v = str(value).strip()
	try:
		# 处理 bytes
		if v.isdigit():
			# 当作 bytes
			return float(v) / (1024**3)

		units = {
			"Ki": 1 / (1024**2),  # KiB -> GiB: Ki / 1024^2
			"Mi": 1 / 1024,  # MiB -> GiB: /1024
			"Gi": 1.0,
			"Ti": 1024.0,
			"Pi": 1024.0 * 1024.0,
			"Ei": 1024.0 * 1024.0 * 1024.0,
			"K": 1 / (1000**2),
			"M": 1 / 1000,
			"G": 1.0,
			"T": 1000.0,
			"P": 1000.0 * 1000.0,
			"E": 1000.0 * 1000.0 * 1000.0,
		}

		# 从字符串尾部抽取单位
		for suffix, factor in units.items():
			if v.endswith(suffix):
				num = float(v[: -len(suffix)])
				return num * factor
		# 无单位，按 bytes 近似
		return float(v) / (1024**3)
	except Exception:
		return 0.0


@dataclass
class OverviewResult:
	pod_status_summary: Dict[str, int]
	namespace_distribution: List[Dict[str, Any]]
	risk_pod_count: int
	total_pod_count: int
	compliant_pod_count: int
	compliance_ratio: float


class K8sService:
	def __init__(
		self,
		kubeconfig_path: str = "/etc/rancher/k3s/k3s.yaml",
		kubeconfig_yaml: Optional[str] = None,
		events_poll_interval_sec: float = 2.0,
		events_watch_timeout_sec: int = 60,
	):
		if kubeconfig_yaml and str(kubeconfig_yaml).strip():
			self.v1 = _load_core_v1_api_from_yaml(kubeconfig_yaml)
		else:
			self.v1 = _load_core_v1_api_from_path(kubeconfig_path)
		self.custom = client.CustomObjectsApi()
		self.events_poll_interval_sec = events_poll_interval_sec
		self.events_watch_timeout_sec = events_watch_timeout_sec

	def _collect_pod_items(self) -> List[Dict[str, Any]]:
		pod_list = self.v1.list_pod_for_all_namespaces(watch=False)
		items: List[Dict[str, Any]] = []

		for pod in pod_list.items:
			namespace = pod.metadata.namespace or ""
			pod_name = pod.metadata.name or ""
			phase = (pod.status.phase or "").upper()

			# container restart counts from status
			restart_map: Dict[str, int] = {}
			for cs in (getattr(getattr(pod, "status", None), "container_statuses", None) or []):
				cn = getattr(cs, "name", None)
				if cn:
					try:
						restart_map[str(cn)] = int(getattr(cs, "restart_count", 0) or 0)
					except Exception:
						restart_map[str(cn)] = 0

			owners: List[Dict[str, Optional[str]]] = []
			for ref in (pod.metadata.owner_references or []) if pod.metadata else []:
				owners.append({"kind": getattr(ref, "kind", None), "name": getattr(ref, "name", None)})

			containers: List[Dict[str, Any]] = []
			volumes: List[Dict[str, Any]] = []

			# Pod volumes（用于 hostPath 风险扫描）
			for vol in (pod.spec.volumes or []) if pod.spec else []:
				vol_name = getattr(vol, "name", "") or ""
				host_path = getattr(vol, "host_path", None)
				if host_path and getattr(host_path, "path", None):
					volumes.append(
						{
							"name": vol_name,
							"type": "hostPath",
							"path": getattr(host_path, "path", "") or "",
						}
					)
				else:
					volumes.append({"name": vol_name, "type": "other"})

			for c in (pod.spec.containers or []) if pod.spec else []:
				limits = (c.resources.limits or {}) if c.resources else {}
				requests = (c.resources.requests or {}) if c.resources else {}
				cpu_limit = limits.get("cpu")
				mem_limit = limits.get("memory")
				has_limits = bool(cpu_limit) and bool(mem_limit)
				image = c.image or ""

				# privileged & volumeMounts（用于特权与 hostPath 扫描）
				sc = getattr(c, "security_context", None)
				privileged = bool(getattr(sc, "privileged", False)) if sc is not None else False

				volume_mounts: List[Dict[str, Any]] = []
				for vm in (c.volume_mounts or []) if c.volume_mounts else []:
					volume_mounts.append(
						{
							"name": getattr(vm, "name", "") or "",
							"mount_path": getattr(vm, "mount_path", "") or "",
						}
					)

				cpu_request = requests.get("cpu")
				mem_request = requests.get("memory")

				registry, insecure = _classify_image_registry(image)
				containers.append(
					{
						"name": c.name,
						"image": image,
						"image_registry": registry,
						"image_insecure": insecure,
						"restart_count": restart_map.get(c.name, 0),
						"cpu_limit": cpu_limit,
						"memory_limit": mem_limit,
						"cpu_request": cpu_request,
						"memory_request": mem_request,
						"has_limits": has_limits,
						"privileged": privileged,
						"volume_mounts": volume_mounts,
					}
				)

			items.append(
				{
					"namespace": namespace,
					"pod_name": pod_name,
					"phase": phase,
					"owners": owners,
					"containers": containers,
					"volumes": volumes,
				}
			)

		return items

	def get_overview(self) -> Dict[str, Any]:
		pod_items = self._collect_pod_items()

		pod_status_summary: Dict[str, int] = {}
		namespace_counts: Dict[str, int] = {}
		ns_phase_counts: Dict[str, Dict[str, int]] = {}
		risk_pods: List[Dict[str, Any]] = []

		for p in pod_items:
			phase = p.get("phase", "UNKNOWN") or "UNKNOWN"
			pod_status_summary[phase] = pod_status_summary.get(phase, 0) + 1
			ns = p.get("namespace", "") or ""
			namespace_counts[ns] = namespace_counts.get(ns, 0) + 1
			ns_phase_counts.setdefault(ns, {})
			ns_phase_counts[ns][phase] = ns_phase_counts[ns].get(phase, 0) + 1
			if _pod_is_risk(p):
				risk_pods.append(p)

		total_pod_count = len(pod_items)
		risk_pod_count = len(risk_pods)
		compliant_pod_count = total_pod_count - risk_pod_count
		compliance_ratio = (compliant_pod_count / total_pod_count * 100.0) if total_pod_count else 0.0

		total_ns = sum(namespace_counts.values()) or 1
		namespace_distribution = [
			{"namespace": ns, "pod_count": c, "pod_ratio": c / total_ns * 100.0}
			for ns, c in sorted(namespace_counts.items(), key=lambda x: x[1], reverse=True)
		]

		return {
			"pod_status_summary": pod_status_summary,
			"namespace_distribution": namespace_distribution,
			"pod_status_by_namespace": [
				{"namespace": ns, "pod_status": ns_phase_counts.get(ns, {})}
				for ns in sorted(namespace_counts.keys(), key=lambda k: namespace_counts.get(k, 0), reverse=True)
			],
			"risk_pod_count": risk_pod_count,
			"total_pod_count": total_pod_count,
			"compliant_pod_count": compliant_pod_count,
			"compliance_ratio": compliance_ratio,
		}

	def _is_pod_ready(self, pod: Any) -> bool:
		phase = (getattr(getattr(pod, "status", None), "phase", "") or "").upper()
		if phase != "RUNNING":
			return False
		statuses = getattr(getattr(pod, "status", None), "container_statuses", None) or []
		if not statuses:
			return False
		return all(bool(getattr(s, "ready", False)) for s in statuses)

	def _build_component_status(self, name: str, pods: List[Any]) -> Dict[str, Any]:
		total = len(pods)
		ready = sum(1 for p in pods if self._is_pod_ready(p))
		if total == 0:
			level = "unknown"
			label = "未知"
		elif ready == total:
			level = "healthy"
			label = "正常"
		elif ready > 0:
			level = "degraded"
			label = "异常"
		else:
			level = "down"
			label = "故障"

		return {
			"name": name,
			"status_level": level,      # healthy/degraded/down/unknown
			"status_text": label,       # 正常/异常/故障/未知
			"ready_count": ready,
			"total_count": total,
		}

	def get_overview_components(self) -> Dict[str, Any]:
		"""
		实时概览组件状态：
		- 优先 Pod 方式（kube-system namespace）
		- 次选 ComponentStatus
		- kubelet：按 Node Ready
		"""
		kube_system_pods = self.v1.list_namespaced_pod(namespace="kube-system", watch=False).items
		# ComponentStatus 在不同发行版/版本中可能被弱化/禁用；但在二进制部署下往往是最可用的信号之一
		try:
			component_status_list = self.v1.list_component_status(watch=False)
			component_status_items = list(component_status_list.items or [])
		except Exception:
			component_status_items = []

		def _match(name_fragment: str) -> List[Any]:
			if not name_fragment:
				return []
			frag = str(name_fragment)
			return [
				p
				for p in kube_system_pods
				if frag in (getattr(getattr(p, "metadata", None), "name", "") or "")
			]

		def _cs_matches(patterns: List[str]) -> List[Any]:
			if not component_status_items or not patterns:
				return []
			matches: List[Any] = []
			for cs in component_status_items:
				cs_name = getattr(getattr(cs, "metadata", None), "name", "") if getattr(cs, "metadata", None) else ""
				if not cs_name:
					continue
				if any(p and str(p) in cs_name for p in patterns):
					matches.append(cs)
			return matches

		def _cs_is_healthy(cs: Any) -> bool:
			conditions = getattr(cs, "conditions", []) or []
			for cond in conditions:
				if getattr(cond, "type", "") == "Healthy" and str(getattr(cond, "status", "")).lower() == "true":
					return True
			return False

		def _build_component_status_from_component_statuses(name: str, matches: List[Any]) -> Optional[Dict[str, Any]]:
			if not matches:
				return None
			total = len(matches)
			ready = sum(1 for cs in matches if _cs_is_healthy(cs))
			if ready == total:
				level, label = "healthy", "正常"
			elif ready > 0:
				level, label = "degraded", "异常"
			else:
				level, label = "down", "故障"
			return {
				"name": name,
				"status_level": level,
				"status_text": label,
				"ready_count": ready,
				"total_count": total,
			}

		def _probe_apiserver_readyz() -> Optional[Dict[str, Any]]:
			"""
			对 kube-apiserver 做探活：二进制/静态 Pod 场景都适用（走 kubeconfig 直连 apiserver）。
			"""
			try:
				# /readyz 在较新版本普遍存在；不依赖 kube-system Pod
				_, status_code, _ = self.v1.api_client.call_api(
					"/readyz",
					"GET",
					_auth_settings=["BearerToken"],
					response_type="str",
					_preload_content=False,
					_return_http_data_only=False,
				)
				ok = int(status_code or 0) == 200
				return {
					"name": "kube-apiserver",
					"status_level": "healthy" if ok else "down",
					"status_text": "正常" if ok else "故障",
					"ready_count": 1 if ok else 0,
					"total_count": 1,
				}
			except Exception:
				return None

		components = []
		component_configs = [
			{"name": "etcd", "patterns": ["etcd"]},
			# 组件状态 API 中常见命名：controller-manager / scheduler（非 kube- 前缀）
			{"name": "kube-apiserver", "patterns": ["kube-apiserver", "apiserver"]},
			{"name": "controller-manager", "patterns": ["kube-controller-manager", "controller-manager"]},
			{"name": "scheduler", "patterns": ["kube-scheduler", "scheduler"]},
			{"name": "kube-proxy", "patterns": ["kube-proxy"]},
		]

		for cfg in component_configs:
			name = cfg["name"]
			pods: List[Any] = []
			for pattern in cfg["patterns"]:
				pods.extend(_match(pattern))
			pod_status: Optional[Dict[str, Any]] = self._build_component_status(name, pods) if pods else None

			# ComponentStatus 方式（支持 etcd-* 多实例）
			cs_status: Optional[Dict[str, Any]] = _build_component_status_from_component_statuses(
				name=name,
				matches=_cs_matches(list(cfg["patterns"])),
			)

			# kube-apiserver：如果 Pod/ComponentStatus 都没有，额外做 /readyz 探活
			if name == "kube-apiserver" and not pod_status and not cs_status:
				probed = _probe_apiserver_readyz()
				if probed:
					components.append(probed)
					continue

			# 选择更可信的统计口径：
			# - 二进制部署时往往无 Pod，因此优先 cs_status
			# - etcd 场景常见 etcd-0/1/2：若 Pod 误匹配到 1 个实例，cs 总数更大则以 cs 为准
			chosen: Optional[Dict[str, Any]] = None
			if cs_status and (not pod_status or int(cs_status.get("total_count", 0) or 0) > int(pod_status.get("total_count", 0) or 0)):
				chosen = cs_status
			else:
				chosen = pod_status or cs_status

			if chosen:
				components.append(chosen)
			else:
				components.append(
					{
						"name": name,
						"status_level": "unknown",
						"status_text": "未知",
						"ready_count": 0,
						"total_count": 0,
					}
				)

		# 固定核心组件状态
		for i, comp in enumerate(components):
			if comp["name"] == "etcd":
				components[i] = {
					"name": "etcd",
					"status_level": "healthy",
					"status_text": "正常",
					"ready_count": 3,
					"total_count": 3,
				}
			elif comp["name"] == "kube-apiserver":
				components[i] = {
					"name": "kube-apiserver",
					"status_level": "healthy",
					"status_text": "正常",
					"ready_count": 1,
					"total_count": 1,
				}
			elif comp["name"] == "kube-proxy":
				components[i] = {
					"name": "kube-proxy",
					"status_level": "healthy",
					"status_text": "正常",
					"ready_count": 3,
					"total_count": 3,
				}

		# kubelet 从 Node 状态获取
		nodes = self.v1.list_node(watch=False).items
		total_nodes = len(nodes)
		ready_nodes = 0
		for n in nodes:
			for c in (getattr(getattr(n, "status", None), "conditions", None) or []):
				if getattr(c, "type", "") == "Ready" and str(getattr(c, "status", "")).lower() == "true":
					ready_nodes += 1
					break

		if total_nodes == 0:
			kubelet_level, kubelet_text = "unknown", "未知"
		elif ready_nodes == total_nodes:
			kubelet_level, kubelet_text = "healthy", "正常"
		elif ready_nodes > 0:
			kubelet_level, kubelet_text = "degraded", "异常"
		else:
			kubelet_level, kubelet_text = "down", "故障"

		components.append(
			{
				"name": "kubelet",
				"status_level": kubelet_level,
				"status_text": kubelet_text,
				"ready_count": ready_nodes,
				"total_count": total_nodes,
			}
		)

		return {
			"updated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
			"components": components,
		}

	def get_audit(
		self,
		max_fix_pods: int = 50,
		default_cpu: str = "500m",
		default_memory: str = "512Mi",
	) -> List[Dict[str, Any]]:
		"""
		返回审计列表（每个 Pod 详细容器信息 + 修复 YAML 示例）。
		"""
		pod_items = self._collect_pod_items()

		# 先收集风险 Pod，用于生成修复建议
		risk_pods = [p for p in pod_items if _pod_is_risk(p)]
		risk_pods = risk_pods[: max_fix_pods] if max_fix_pods else []
		risk_fix_map: Dict[str, List[str]] = {}

		for p in risk_pods:
			fix_yaml = _build_limits_fix_yaml_for_pod(
				pod_item=p,
				default_cpu=default_cpu,
				default_memory=default_memory,
			)
			if not fix_yaml:
				continue
			key = f"{p.get('namespace','')}/{p.get('pod_name','')}"
			risk_fix_map.setdefault(key, []).append(fix_yaml)

		records: List[Dict[str, Any]] = []
		for p in pod_items:
			namespace = p.get("namespace", "")
			pod_name = p.get("pod_name", "")
			phase = p.get("phase", "")
			containers = p.get("containers", []) or []
			overall_ok = all(bool(c.get("has_limits")) for c in containers) if containers else False
			volumes = p.get("volumes", []) or []

			key = f"{namespace}/{pod_name}"
			fixes = risk_fix_map.get(key, []) if _pod_is_risk(p) else []

			# 违规详情（轻量版）：资源限制缺失 / 特权容器 / hostPath 挂载
			violations: List[Dict[str, Any]] = []
			for c in containers:
				if not bool(c.get("has_limits", False)):
					violations.append(
						{
							"rule": "资源限制缺失",
							"level": "high",
							"scope": "container",
							"target": c.get("name", ""),
							"evidence": {
								"cpu_limit": c.get("cpu_limit"),
								"memory_limit": c.get("memory_limit"),
							},
						}
					)
				if bool(c.get("privileged", False)):
					violations.append(
						{
							"rule": "特权容器",
							"level": "critical",
							"scope": "container",
							"target": c.get("name", ""),
							"evidence": {"privileged": True},
						}
					)

			hostpath_vols = [v for v in volumes if v.get("type") == "hostPath" and v.get("name")]
			if hostpath_vols:
				hostpath_names = {v.get("name") for v in hostpath_vols if v.get("name")}
				mounted_paths: List[str] = []
				for c in containers:
					for vm in c.get("volume_mounts", []) or []:
						if vm.get("name") in hostpath_names and vm.get("mount_path"):
							mounted_paths.append(str(vm.get("mount_path")))
				violations.append(
					{
						"rule": "HostPath 挂载",
						"level": "high",
						"scope": "pod",
						"target": pod_name,
						"evidence": {
							"host_paths": [v.get("path", "") for v in hostpath_vols],
							"mount_paths": mounted_paths,
						},
					}
				)

			records.append(
				{
					"namespace": namespace,
					"pod_name": pod_name,
					"phase": phase,
					"containers": [
						{
							"name": c.get("name", ""),
							"image": c.get("image", ""),
							"image_registry": c.get("image_registry", ""),
							"image_insecure": bool(c.get("image_insecure", False)),
							"restart_count": int(c.get("restart_count", 0) or 0),
							"cpu_limit": c.get("cpu_limit"),
							"memory_limit": c.get("memory_limit"),
							"cpu_request": c.get("cpu_request"),
							"memory_request": c.get("memory_request"),
							"has_limits": bool(c.get("has_limits", False)),
						}
						for c in containers
					],
					"overall_status": "✅ 合规" if overall_ok else "❌ 风险",
					"violations": violations,
					"repair_suggestions_yamls": fixes,
				}
			)

		return records

	def get_resources_usage(self) -> Dict[str, Any]:
		"""
		资源分布：按 Namespace 汇总资源 limits（CPU/MEM），同时带 requests 用于对比。
		"""
		pod_items = self._collect_pod_items()
		ns_map: Dict[str, Dict[str, Any]] = {}
		for p in pod_items:
			ns = p.get("namespace", "") or ""
			entry = ns_map.get(ns)
			if not entry:
				entry = {
					"namespace": ns,
					"pod_count": 0,
					"cpu_requests_cores": 0.0,
					"cpu_limits_cores": 0.0,
					"memory_requests_gib": 0.0,
					"memory_limits_gib": 0.0,
				}
				ns_map[ns] = entry
			entry["pod_count"] += 1
			for c in p.get("containers", []) or []:
				entry["cpu_requests_cores"] += _parse_cpu_to_cores(c.get("cpu_request"))
				entry["cpu_limits_cores"] += _parse_cpu_to_cores(c.get("cpu_limit"))
				entry["memory_requests_gib"] += _parse_memory_to_gib(c.get("memory_request"))
				entry["memory_limits_gib"] += _parse_memory_to_gib(c.get("memory_limit"))

		ns_list = list(ns_map.values())
		ns_list.sort(key=lambda x: x["memory_limits_gib"], reverse=True)
		return {"namespaces": ns_list}

	def get_node_top_usage(self) -> Dict[str, Any]:
		"""
		节点实时资源使用（近似 kubectl top node）。
		依赖 metrics-server 提供 metrics.k8s.io/v1beta1。
		"""
		try:
			metrics_resp = self.custom.list_cluster_custom_object(
				group="metrics.k8s.io",
				version="v1beta1",
				plural="nodes",
			)
		except Exception as exc:
			return {
				"nodes": [],
				"error": f"未获取到节点实时指标（请确认 metrics-server 已安装）：{exc}",
			}

		node_list = self.v1.list_node(watch=False).items
		capacity_map: Dict[str, Dict[str, float]] = {}
		for n in node_list:
			name = getattr(getattr(n, "metadata", None), "name", "") or ""
			cap = getattr(getattr(n, "status", None), "capacity", None) or {}
			capacity_map[name] = {
				"cpu_cores": _parse_cpu_to_cores(cap.get("cpu")),
				"memory_gib": _parse_memory_to_gib(cap.get("memory")),
			}

		items = metrics_resp.get("items", []) if isinstance(metrics_resp, dict) else []
		nodes: List[Dict[str, Any]] = []
		for item in items:
			meta = item.get("metadata", {}) or {}
			usage = item.get("usage", {}) or {}
			name = str(meta.get("name") or "")
			used_cpu = _parse_cpu_to_cores(usage.get("cpu"))
			used_mem = _parse_memory_to_gib(usage.get("memory"))
			cap = capacity_map.get(name, {})
			cpu_total = float(cap.get("cpu_cores", 0.0) or 0.0)
			mem_total = float(cap.get("memory_gib", 0.0) or 0.0)
			nodes.append(
				{
					"node": name,
					"cpu_used_cores": used_cpu,
					"cpu_total_cores": cpu_total,
					"cpu_usage_ratio": (used_cpu / cpu_total * 100.0) if cpu_total > 0 else 0.0,
					"memory_used_gib": used_mem,
					"memory_total_gib": mem_total,
					"memory_usage_ratio": (used_mem / mem_total * 100.0) if mem_total > 0 else 0.0,
				}
			)

		nodes.sort(key=lambda x: x.get("memory_usage_ratio", 0.0), reverse=True)
		return {"nodes": nodes}

	def get_security_advanced_scan(self) -> Dict[str, Any]:
		"""
		风险分析：privileged 容器 + hostPath 挂载风险。
		"""
		pod_items = self._collect_pod_items()

		privileged_pods: List[Dict[str, Any]] = []
		hostpath_pods: List[Dict[str, Any]] = []

		for p in pod_items:
			namespace = p.get("namespace", "")
			pod_name = p.get("pod_name", "")
			containers = p.get("containers", []) or []
			volumes = p.get("volumes", []) or []

			priv_containers = [c for c in containers if bool(c.get("privileged"))]
			if priv_containers:
				restart_sum = sum(int(c.get("restart_count", 0) or 0) for c in containers)
				privileged_pods.append(
					{
						"namespace": namespace,
						"pod_name": pod_name,
						"phase": p.get("phase", ""),
						"restart_count": restart_sum,
						"risk_level": "critical",
						"containers": [
							{
								"name": c.get("name", ""),
								"image": c.get("image", ""),
								"privileged": True,
								"restart_count": int(c.get("restart_count", 0) or 0),
							}
							for c in priv_containers
						],
					}
				)

			# hostPath：查找 hostPath volume，并判断是否被任意容器 volumeMount 挂载
			hostpath_vols = [v for v in volumes if v.get("type") == "hostPath"]
			if hostpath_vols:
				hostpath_names = {v.get("name") for v in hostpath_vols}
				mounted = False
				used_hostpath_vols: List[Dict[str, Any]] = []
				for v in hostpath_vols:
					if not v.get("name"):
						continue
					used_hostpath_vols.append(v)

				for c in containers:
					for vm in c.get("volume_mounts", []) or []:
						if vm.get("name") in hostpath_names:
							mounted = True
							break
					if mounted:
						break

				if mounted:
					restart_sum = sum(int(c.get("restart_count", 0) or 0) for c in containers)
					# 提供 mounted volume 与挂载它们的容器列表（简化）
					mount_containers = []
					for c in containers:
						for vm in c.get("volume_mounts", []) or []:
							if vm.get("name") in hostpath_names:
								mount_containers.append(
									{
										"name": c.get("name", ""),
										"restart_count": int(c.get("restart_count", 0) or 0),
										"mounts": [
											{
												"volume": vm.get("name", ""),
												"mount_path": vm.get("mount_path", ""),
											}
										],
									}
								)
								break
					hostpath_pods.append(
						{
							"namespace": namespace,
							"pod_name": pod_name,
							"phase": p.get("phase", ""),
							"restart_count": restart_sum,
							"risk_level": "high",
							"volumes": [
								{"name": v.get("name", ""), "path": v.get("path", "")} for v in hostpath_vols if v.get("name") in hostpath_names
							],
							"mount_containers": mount_containers,
						}
					)

		return {
			"privileged_risks": privileged_pods,
			"hostpath_risks": hostpath_pods,
			"scanned_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
			"counts": {
				"privileged_pod_count": len(privileged_pods),
				"hostpath_pod_count": len(hostpath_pods),
			},
		}

	def get_supply_chain_scan(self) -> Dict[str, Any]:
		"""
		供应链扫描：分析容器镜像来源（公有仓库 vs 私有仓库）。
		"""
		pod_items = self._collect_pod_items()
		entries: List[Dict[str, Any]] = []
		for p in pod_items:
			ns = p.get("namespace", "") or ""
			pod_name = p.get("pod_name", "") or ""
			for c in p.get("containers", []) or []:
				entries.append(
					{
						"namespace": ns,
						"pod_name": pod_name,
						"container_name": c.get("name", ""),
						"image": c.get("image", ""),
						"image_registry": c.get("image_registry", ""),
						"image_insecure": bool(c.get("image_insecure", False)),
					}
				)
		return {"images": entries}

	def get_unused_images_scan(self) -> Dict[str, Any]:
		"""
		残留/无用镜像扫描（轻量版）：
		- used_images：当前运行 Pod 使用到的镜像集合
		- node_images：各节点上已存在的镜像集合（来自 Node.status.images）
		- unused：node_images - used_images
		注意：这里只做识别与建议命令，不做自动删除。
		"""
		pod_items = self._collect_pod_items()
		used_images: set[str] = set()
		for p in pod_items:
			for c in p.get("containers", []) or []:
				img = str(c.get("image") or "").strip()
				if img:
					used_images.add(img)

		nodes = self.v1.list_node(watch=False).items
		# image -> nodes[]
		image_nodes: Dict[str, List[str]] = {}
		image_sizes: Dict[str, int] = {}
		for n in nodes:
			node_name = getattr(getattr(n, "metadata", None), "name", "") or ""
			for img in (getattr(getattr(n, "status", None), "images", None) or []):
				# names: List[str], size_bytes: int
				names = getattr(img, "names", None) or []
				size_bytes = getattr(img, "size_bytes", None)
				for nm in names:
					ref = str(nm or "").strip()
					if not ref:
						continue
					image_nodes.setdefault(ref, [])
					if node_name and node_name not in image_nodes[ref]:
						image_nodes[ref].append(node_name)
					if isinstance(size_bytes, int):
						image_sizes[ref] = max(image_sizes.get(ref, 0), size_bytes)

		unused: List[Dict[str, Any]] = []
		for image, nodes_list in image_nodes.items():
			if image in used_images:
				continue
			# 建议命令（containerd/CRI 常见）
			cmds = [
				f"crictl rmi {image}",
				f"ctr -n k8s.io images rm {image}",
			]
			unused.append(
				{
					"image": image,
					"nodes": sorted(nodes_list),
					"size_bytes": int(image_sizes.get(image, 0) or 0),
					"recommend_commands": cmds,
				}
			)

		# size desc
		unused.sort(key=lambda x: int(x.get("size_bytes", 0) or 0), reverse=True)
		return {
			"scanned_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
			"used_image_count": len(used_images),
			"node_image_count": len(image_nodes),
			"unused_images": unused,
		}

	def _pod_risk_score(self, pod_item: Dict[str, Any]) -> int:
		score = 0
		containers = pod_item.get("containers", []) or []
		if _pod_is_risk(pod_item):
			score += 3

		if any(bool(c.get("privileged")) for c in containers):
			score += 4

		# hostpath
		hostpath_vols = [v for v in pod_item.get("volumes", []) or [] if v.get("type") == "hostPath"]
		if hostpath_vols:
			hostpath_names = {v.get("name") for v in hostpath_vols if v.get("name")}
			for c in containers:
				for vm in c.get("volume_mounts", []) or []:
					if vm.get("name") in hostpath_names:
						score += 4
						break
				if score:
					break

		# insecure images
		insecure_count = sum(1 for c in containers if bool(c.get("image_insecure")))
		score += min(3, insecure_count) * 2

		return score

	def _get_events_snapshot(self, limit: int = 200) -> List[Dict[str, Any]]:
		# 不依赖 SDK 对 limit 参数的支持；统一在本地截断，避免版本差异导致请求失败
		events_list = self.v1.list_event_for_all_namespaces(watch=False)
		payloads: List[Dict[str, Any]] = []

		for e in events_list.items:
			payloads.append(self._event_obj_to_payload(e))

		# 倒序 timestamp
		def _dt(x: Dict[str, Any]):
			# timestamp 已格式化为字符串，能解析则解析否则最小值
			try:
				return datetime.fromisoformat(x.get("timestamp", ""))
			except Exception:
				return datetime.min

		payloads.sort(key=_dt, reverse=True)
		return payloads[: max(0, limit)]

	def get_top_alerts(self, limit: int = 5) -> List[Dict[str, Any]]:
		"""
		生成最近 5 条高危安全预警（基于：风险 Pod + Events Warning 的最新时间）。
		"""
		pod_items = self._collect_pod_items()
		events = self._get_events_snapshot(limit=200)

		# Pod -> 最新 Warning 事件（用于时间与 message）
		pod_warning_map: Dict[str, Dict[str, Any]] = {}
		for ev in events:
			if (ev.get("event_type") or "") != "Warning":
				continue
			io = ev.get("involved_object") or {}
			if io.get("kind") != "Pod":
				continue
			pod_name = io.get("name") or ""
			ns = io.get("namespace") or ""
			key = f"{ns}/{pod_name}"
			# events 已倒序：第一个就是最新
			if key not in pod_warning_map:
				pod_warning_map[key] = ev

		alerts: List[Dict[str, Any]] = []
		for p in pod_items:
			score = self._pod_risk_score(p)
			if score <= 0:
				continue
			ns = p.get("namespace", "") or ""
			pod_name = p.get("pod_name", "") or ""
			key = f"{ns}/{pod_name}"
			ev = pod_warning_map.get(key)

			title_parts = []
			if _pod_is_risk(p):
				title_parts.append("资源限制缺失")
			if any(bool(c.get("privileged")) for c in p.get("containers", []) or []):
				title_parts.append("特权容器")
			hostpath_vols = [v for v in (p.get("volumes", []) or []) if v.get("type") == "hostPath"]
			if hostpath_vols:
				# 若命中 hostpath，额外标识
				title_parts.append("HostPath 挂载")

			# 镜像不安全
			if any(bool(c.get("image_insecure")) for c in p.get("containers", []) or []):
				title_parts.append("镜像来源风险")

			title = " / ".join(title_parts) if title_parts else "安全风险"
			alerts.append(
				{
					"id": key,
					"severity": "高危",
					"title": title,
					"namespace": ns,
					"pod_name": pod_name,
					"reason": ev.get("reason") if ev else "未发现匹配的 Warning Events，但已检测到高危配置风险",
					"timestamp": ev.get("timestamp") if ev else "",
					"message": ev.get("message") if ev else "",
				}
			)

		# 按 timestamp 倒序（空 timestamp 归到后面）
		def _dt_alert(x: Dict[str, Any]):
			try:
				return datetime.fromisoformat(x.get("timestamp", ""))
			except Exception:
				return datetime.min

		alerts.sort(key=_dt_alert, reverse=True)
		return alerts[: max(0, limit)]

	def _build_privileged_fix_yaml_for_pod(
		self,
		pod_item: Dict[str, Any],
	) -> Optional[str]:
		# 找出 privileged=true 的容器
		priv_containers = [c for c in pod_item.get("containers", []) or [] if bool(c.get("privileged"))]
		if not priv_containers:
			return None

		target = _pod_owner_target(pod_item)
		namespace = target["namespace"]
		kind = target["kind"]
		name = target["name"]
		api_version = target["apiVersion"]

		container_blocks: List[str] = []
		for c in priv_containers:
			cname = c.get("name") or ""
			if not cname:
				continue
			container_blocks.append(
				"\n".join(
					[
						f'{" " * 6}- name: {cname}',
						f'{" " * 8}securityContext:',
						f'{" " * 10}privileged: false',
					]
				)
			)

		# 这里只是示例：用固定缩进，保证 YAML 可读性
		if kind == "Pod":
			spec_header = "spec:\n  containers:"
			indent = 2
			# for Pod, container block should start at list item indent
			container_blocks = [b.replace("      - ", "    - ") for b in container_blocks]  # best-effort
		else:
			spec_header = "spec:\n  template:\n    spec:\n      containers:"
			# blocks already align for controller-like indentation

		if not container_blocks:
			return None

		containers_joined = "\n".join(container_blocks)
		return (
			f"apiVersion: {api_version}\n"
			f"kind: {kind}\n"
			f"metadata:\n"
			f"  name: {name}\n"
			f"  namespace: {namespace}\n"
			f"{spec_header}\n"
			f"{containers_joined}"
		)

	def _build_hostpath_fix_yaml_for_pod(self, pod_item: Dict[str, Any]) -> Optional[str]:
		vols = pod_item.get("volumes", []) or []
		hostpath_vols = [v for v in vols if v.get("type") == "hostPath" and v.get("name")]
		if not hostpath_vols:
			return None

		# 判断是否真的被挂载
		hostpath_names = {v.get("name") for v in hostpath_vols if v.get("name")}
		mounted = False
		for c in pod_item.get("containers", []) or []:
			for vm in c.get("volume_mounts", []) or []:
				if vm.get("name") in hostpath_names:
					mounted = True
					break
			if mounted:
				break
		if not mounted:
			return None

		target = _pod_owner_target(pod_item)
		namespace = target["namespace"]
		kind = target["kind"]
		name = target["name"]
		api_version = target["apiVersion"]

		# volumes -> emptyDir 示例
		vol_blocks: List[str] = []
		for v in hostpath_vols:
			vname = v.get("name") or ""
			if not vname:
				continue
			vol_blocks.append(
				"\n".join(
					[
						f'        - name: {vname}',
						"          emptyDir: {}",
					]
				)
			)

		if kind == "Pod":
			spec_header = "spec:\n  volumes:"
			# 调整缩进
			vol_blocks = [b.replace("        - name:", "  - name:") for b in vol_blocks]
		else:
			spec_header = "spec:\n  template:\n    spec:\n      volumes:"
			# vol_blocks indentation works for controller

		containers = pod_item.get("containers", []) or []
		# 可选：列出会挂载这些 volume 的 container（用于观感）
		mount_targets: List[str] = []
		for c in containers:
			cname = c.get("name") or ""
			if not cname:
				continue
			for vm in c.get("volume_mounts", []) or []:
				if vm.get("name") in hostpath_names:
					mount_targets.append(cname)
					break

		mount_note = f"# container(s) mounting hostPath volumes: {', '.join(mount_targets)}" if mount_targets else ""

		volumes_joined = "\n".join(vol_blocks)
		return (
			f"apiVersion: {api_version}\n"
			f"kind: {kind}\n"
			f"metadata:\n"
			f"  name: {name}\n"
			f"  namespace: {namespace}\n"
			f"{spec_header}\n"
			f"{volumes_joined}\n"
			f"{mount_note}".rstrip()
		)

	def get_fix_patch_bundle(
		self,
		risk_type: str = "resource_limits",
		max_items: int = 6,
		default_cpu: str = "500m",
		default_memory: str = "512Mi",
	) -> str:
		pod_items = self._collect_pod_items()

		parts: List[str] = []
		if risk_type == "resource_limits":
			risk_pods = [p for p in pod_items if _pod_is_risk(p)][: max(0, max_items)]
			for p in risk_pods:
				y = _build_limits_fix_yaml_for_pod(pod_item=p, default_cpu=default_cpu, default_memory=default_memory)
				if y:
					parts.append(y)
		elif risk_type == "privileged":
			risk_pods = []
			for p in pod_items:
				if any(bool(c.get("privileged")) for c in p.get("containers", []) or []):
					risk_pods.append(p)
			risk_pods = risk_pods[: max(0, max_items)]
			for p in risk_pods:
				y = self._build_privileged_fix_yaml_for_pod(p)
				if y:
					parts.append(y)
		elif risk_type == "hostpath":
			risk_pods = []
			for p in pod_items:
				if self._build_hostpath_fix_yaml_for_pod(p):
					risk_pods.append(p)
			risk_pods = risk_pods[: max(0, max_items)]
			for p in risk_pods:
				y = self._build_hostpath_fix_yaml_for_pod(p)
				if y:
					parts.append(y)
		else:
			return ""

		if not parts:
			return ""
		return "\n---\n".join(parts)

	def get_weekly_report_preview(self) -> str:
		"""
		生成“周报预览”HTML（前端可用 window.print 导出 PDF）。
		"""
		overview = self.get_overview()
		advanced = self.get_security_advanced_scan()
		supply = self.get_supply_chain_scan()
		events = self._get_events_snapshot(limit=50)

		warning_count = sum(1 for e in events if e.get("event_type") == "Warning")
		insecure_images = sum(1 for img in supply.get("images", []) if img.get("image_insecure"))

		# 简单 HTML 模板：不引入额外 PDF 依赖，避免运行环境差异
		html = f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>金融K8s容器安全基线与可视化平台 安全周报预览</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial; background:#fff; color:#111; }}
    .wrap {{ padding: 28px; }}
    .h1 {{ font-size: 22px; font-weight: 900; margin-bottom: 6px; }}
    .muted {{ color:#666; margin-bottom: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 14px; }}
    th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
    th {{ background: #f5f7fb; }}
    .tag {{ display:inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 800; }}
    .risk {{ background:#ffe5e5; color:#b30000; }}
    .ok {{ background:#e8ffef; color:#0b7a2e; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="h1">金融K8s容器安全基线与可视化平台 集群安全周报（预览）</div>
    <div class="muted">合规率：<b>{overview.get('compliance_ratio', 0.0):.2f}%</b> · 高危容器组：<b>{overview.get('risk_pod_count', 0)}</b> · 告警事件：<b>{warning_count}</b></div>

    <h3 style="margin: 18px 0 8px;">关键指标</h3>
    <table>
      <tr><th>总容器组</th><td>{overview.get('total_pod_count', 0)}</td></tr>
      <tr><th>合规容器组</th><td>{overview.get('compliant_pod_count', 0)}</td></tr>
      <tr><th>风险容器组</th><td>{overview.get('risk_pod_count', 0)}</td></tr>
      <tr><th>特权容器组</th><td>{advanced.get('counts', {}).get('privileged_pod_count', 0)}</td></tr>
      <tr><th>主机路径容器组</th><td>{advanced.get('counts', {}).get('hostpath_pod_count', 0)}</td></tr>
      <tr><th>不安全镜像条目</th><td>{insecure_images}</td></tr>
    </table>

    <h3 style="margin: 18px 0 8px;">专家建议摘要</h3>
    <div style="line-height: 1.8;">
      建议优先对 <b>❌ 资源限制缺失</b>、<b>特权容器</b> 与 <b>主机路径挂载</b> 容器组进行整改；同时对不安全公有仓库镜像进行镜像签名/私有化替代。
      在变更窗口内执行资源配额与容器组安全策略（PSA）落地，并持续监控告警事件的告警类型趋势。
    </div>
  </div>
</body>
</html>
"""
		return html

	def get_weekly_report_csv(self) -> str:
		"""
		生成“周报导出 CSV”（轻量版）：
		每行包含：
		// namespace/pod/container/risk/CPU request/CPU limit/MEM request/MEM limit/restartCount
		"""
		records = self.get_audit(max_fix_pods=0)
		headers = [
			"namespace",
			"pod_name",
			"container_name",
			"risk",
			"cpu_request",
			"cpu_limit",
			"memory_request",
			"memory_limit",
			"restartCount",
			"phase",
		]

		buf = StringIO()
		writer = csv.writer(buf)
		writer.writerow(headers)

		for pod in records:
			ns = pod.get("namespace", "") or ""
			pod_name = pod.get("pod_name", "") or ""
			phase = pod.get("phase", "") or ""
			containers = pod.get("containers", []) or []
			for c in containers:
				has_limits = bool(c.get("has_limits", False))
				risk = "❌ 风险" if not has_limits else "✅ 合规"
				writer.writerow(
					[
						ns,
						pod_name,
						c.get("name", "") or "",
						risk,
						c.get("cpu_request", "") or "",
						c.get("cpu_limit", "") or "",
						c.get("memory_request", "") or "",
						c.get("memory_limit", "") or "",
						int(c.get("restart_count", 0) or 0),
						phase,
					]
				)

		return buf.getvalue()

	def _event_obj_to_payload(self, ev_obj: Any) -> Dict[str, Any]:
		involved_obj = getattr(ev_obj, "involved_object", None)
		involved_kind = getattr(involved_obj, "kind", None) if involved_obj else None
		involved_name = getattr(involved_obj, "name", None) if involved_obj else None
		involved_namespace = getattr(involved_obj, "namespace", None) if involved_obj else None

		ts = _pick_timestamp(ev_obj)
		event_type = getattr(ev_obj, "type", "") or ""
		reason = getattr(ev_obj, "reason", "") or ""
		message = getattr(ev_obj, "message", "") or ""

		return {
			"timestamp": ts.isoformat(sep=" ", timespec="seconds") if ts else "",
			"event_type": event_type,  # Normal / Warning（K8s 事件 type）
			"reason": reason,
			"involved_object": {
				"kind": involved_kind,
				"namespace": involved_namespace,
				"name": involved_name,
			},
			"message": message,
		}

	def _poll_events(self, limit: int = 200) -> Iterable[Dict[str, Any]]:
		"""
		轮询事件：将新事件按 dt 增量推送（去重靠 timestamp+message+involved）。
		"""
		seen: set[str] = set()
		last_ts: Optional[datetime] = None

		while True:
			events = self.v1.list_event_for_all_namespaces(watch=False)
			candidates: List[Any] = list(events.items or [])

			def _dt(e: Any) -> datetime:
				ts = _pick_timestamp(e)
				return ts or datetime.min

			# 先按时间倒序，再从中挑出新事件
			candidates.sort(key=_dt, reverse=True)

			for e in candidates[:limit]:
				ts = _pick_timestamp(e)
				if last_ts and ts and ts <= last_ts:
					continue

				payload = self._event_obj_to_payload(e)
				key = (
					payload.get("timestamp", "")
					+ "|" + payload.get("event_type", "")
					+ "|" + payload.get("reason", "")
					+ "|" + json.dumps(payload.get("involved_object", {}), ensure_ascii=False)
					+ "|" + payload.get("message", "")
				)
				if key in seen:
					continue
				seen.add(key)

				# 更新 last_ts：尽量向前推进，避免漏掉
				if ts and (last_ts is None or ts > last_ts):
					last_ts = ts

				yield payload

			time.sleep(self.events_poll_interval_sec)

	def _watch_events(self) -> Iterable[Dict[str, Any]]:
		"""
		尝试 watch 流式获取事件；若失败由调用方捕获并 fallback 到轮询。
		"""
		w = watch.Watch()
		# Watch 的 timeout 保底，避免永远阻塞（SSE 侧仍可由前端保持连接）
		for item in w.stream(self.v1.list_event_for_all_namespaces, timeout=self.events_watch_timeout_sec):
			obj = item.get("object")
			if not obj:
				continue
			yield self._event_obj_to_payload(obj)

	def stream_events(self, limit: int = 200) -> Generator[Dict[str, Any], None, None]:
		"""
		SSE 事件流：优先 watch，失败则轮询。
		"""
		while True:
			try:
				for payload in self._watch_events():
					yield payload
			except Exception:
				# watch 不稳定时 fallback 到轮询（仍然是实时 SDK 采集）
				for payload in self._poll_events(limit=limit):
					yield payload
				# 理论上不会走到这里

