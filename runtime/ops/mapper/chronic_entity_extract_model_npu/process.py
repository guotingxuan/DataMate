from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from pathlib import Path as _Path
import sys as _sys

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from _chronic_common import Mapper, execute_operator
    from _chronic_common.base import read_jsonl
else:
    from .._chronic_common import Mapper, execute_operator
    from .._chronic_common.base import read_jsonl


SAFETY_NOTE = "本项目仅用于慢病随访数据处理、知识组织和辅助分析，不提供临床诊断，不替代医生决策。"
CANN_ROOT_CANDIDATES = [item for item in [
    os.environ.get("ASCEND_HOME", ""),
    os.environ.get("ASCEND_TOOLKIT_HOME", ""),
    "/usr/local/Ascend/ascend-toolkit/latest",
] if item]
DEFAULT_EMBEDDING_MODEL_PATH = "/models/VideoOps/ChronicCare/bge-small-zh-v1.5"
ENTITY_LABELS = [
    ("Patient", "患者 patient person"),
    ("Disease", "疾病 诊断 慢病 disease diagnosis"),
    ("Drug", "药物 用药 medication drug"),
    ("DrugCategory", "药物类别 drug category"),
    ("Indicator", "检查指标 检验指标 lab indicator"),
    ("LabResult", "检验结果 lab result"),
    ("Visit", "随访 就诊 visit"),
    ("RiskFactor", "危险因素 risk factor"),
    ("RiskEvent", "风险事件 abnormal risk event"),
    ("FollowupPlan", "随访计划 followup plan"),
    ("LifestyleRecord", "生活方式 lifestyle record"),
    ("DoctorAdvice", "医生建议 doctor advice"),
    ("RiskScore", "风险评分 risk score"),
]


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Dict[str, Any]) -> str:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.as_posix()


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> str:
    _ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path.as_posix()


def _bootstrap_ascend_env() -> Dict[str, Any]:
    root = next((Path(item) for item in CANN_ROOT_CANDIDATES if Path(item).exists()), None)
    if root is None:
        return {"cann_root": None, "env_bootstrapped": False, "reason": "CANN root not found"}
    lib_paths = [
        root / "lib64",
        root / "lib64" / "plugin" / "opskernel",
        root / "lib64" / "plugin" / "nnengine",
        root / "opp" / "built-in" / "op_impl" / "ai_core" / "tbe" / "op_tiling" / "lib" / "linux" / "aarch64",
        root / "tools" / "aml" / "lib64",
        root / "tools" / "aml" / "lib64" / "plugin",
        Path("/usr/local/Ascend/driver/lib64"),
        Path("/usr/local/Ascend/driver/lib64/common"),
        Path("/usr/local/Ascend/driver/lib64/driver"),
    ]
    py_paths = [
        root / "python" / "site-packages",
        root / "opp" / "built-in" / "op_impl" / "ai_core" / "tbe",
        Path("/opt/runtime/datamate"),
    ]
    os.environ.setdefault("ASCEND_HOME_PATH", root.as_posix())
    os.environ.setdefault("ASCEND_TOOLKIT_HOME", root.as_posix())
    os.environ.setdefault("ASCEND_OPP_PATH", (root / "opp").as_posix())
    os.environ["LD_LIBRARY_PATH"] = ":".join([p.as_posix() for p in lib_paths if p.exists()] + [item for item in os.environ.get("LD_LIBRARY_PATH", "").split(":") if item])
    os.environ["PYTHONPATH"] = ":".join([p.as_posix() for p in py_paths if p.exists()] + [item for item in os.environ.get("PYTHONPATH", "").split(":") if item])
    return {"cann_root": root.as_posix(), "env_bootstrapped": True}


def _detect_npu_runtime() -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    checks.update(_bootstrap_ascend_env())
    try:
        import torch  # type: ignore
        import torch_npu  # type: ignore  # noqa: F401

        npu_obj = getattr(torch, "npu", None)
        checks["torch_version"] = getattr(torch, "__version__", None)
        checks["torch_npu_available"] = True
        checks["torch_npu_device_available"] = bool(npu_obj.is_available()) if npu_obj else False
        checks["torch_npu_device_count"] = int(npu_obj.device_count()) if npu_obj else 0
    except Exception as exc:
        checks["torch_npu_available"] = False
        checks["torch_npu_error"] = str(exc)
        checks["torch_npu_device_available"] = False
    try:
        completed = subprocess.run(["npu-smi", "info"], capture_output=True, text=True, timeout=3, check=False)
        checks["npu_smi_available"] = completed.returncode == 0
    except Exception as exc:
        checks["npu_smi_available"] = False
        checks["npu_smi_error"] = str(exc)
    checks["npu_available"] = bool(checks.get("torch_npu_available") and checks.get("torch_npu_device_available"))
    checks["backend"] = "torch_npu" if checks["npu_available"] else "cpu_fallback"
    return checks


def _read_npu_smi_samples() -> List[Dict[str, Any]]:
    env = os.environ.copy()
    extra_libs = [
        "/usr/local/Ascend/driver/lib64/common",
        "/usr/local/Ascend/driver/lib64/driver",
        "/usr/local/Ascend/driver/lib64",
    ]
    env["LD_LIBRARY_PATH"] = ":".join(extra_libs + [item for item in env.get("LD_LIBRARY_PATH", "").split(":") if item])
    completed = subprocess.run(["npu-smi", "info"], capture_output=True, text=True, timeout=3, check=False, env=env)
    if completed.returncode != 0:
        return []
    lines = completed.stdout.splitlines()
    samples: List[Dict[str, Any]] = []
    for index, line in enumerate(lines[:-1]):
        match = re.search(r"\|\s*(\d+)\s+910\w*\s+\|\s+\S+\s+\|\s*([0-9.]+)", line)
        if not match:
            continue
        next_line = lines[index + 1]
        aicore_match = re.search(r"\|\s*\d+\s+\|\s+[0-9A-Fa-f:.]+\s+\|\s*([0-9.]+)\s+", next_line)
        hbm_match = re.search(r"([0-9]+)\s*/\s*([0-9]+)\s*\|", next_line)
        samples.append(
            {
                "npu_id": int(match.group(1)),
                "power_watt": float(match.group(2)),
                "aicore_percent": float(aicore_match.group(1)) if aicore_match else None,
                "hbm_used_mb": int(hbm_match.group(1)) if hbm_match else None,
                "hbm_total_mb": int(hbm_match.group(2)) if hbm_match else None,
            }
        )
    return samples


class _NpuSmiSampler:
    def __init__(self, interval_seconds: float = 1.0, device_id: int = 0):
        self.interval_seconds = interval_seconds
        self.device_id = device_id
        self.samples: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.started_at = 0.0
        self.ended_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self.started_at = time.perf_counter()

        def run() -> None:
            while not self._stop.is_set():
                try:
                    items = _read_npu_smi_samples()
                    sample = next((item for item in items if item.get("npu_id") == self.device_id), None)
                    if sample:
                        sample["timestamp_perf"] = time.perf_counter()
                        self.samples.append(sample)
                except Exception as exc:
                    self.errors.append(str(exc))
                self._stop.wait(self.interval_seconds)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.ended_at = time.perf_counter()

    def summary(self) -> Dict[str, Any]:
        elapsed = (self.ended_at or time.perf_counter()) - self.started_at if self.started_at else 0.0
        powers = [float(item["power_watt"]) for item in self.samples if item.get("power_watt") is not None]
        aicores = [float(item["aicore_percent"]) for item in self.samples if item.get("aicore_percent") is not None]
        hbm_used = [float(item["hbm_used_mb"]) for item in self.samples if item.get("hbm_used_mb") is not None]
        avg_power = sum(powers) / len(powers) if powers else None
        return {
            "status": "collected" if self.samples else "not_collected",
            "sample_count": len(self.samples),
            "sample_interval_seconds": self.interval_seconds,
            "elapsed_seconds": round(elapsed, 6),
            "device_id": self.device_id,
            "average_power_watt": round(avg_power, 4) if avg_power is not None else None,
            "max_power_watt": round(max(powers), 4) if powers else None,
            "average_aicore_percent": round(sum(aicores) / len(aicores), 4) if aicores else None,
            "max_aicore_percent": round(max(aicores), 4) if aicores else None,
            "average_hbm_used_mb": round(sum(hbm_used) / len(hbm_used), 2) if hbm_used else None,
            "max_hbm_used_mb": round(max(hbm_used), 2) if hbm_used else None,
            "estimated_energy_wh": round(avg_power * elapsed / 3600.0, 6) if avg_power is not None else None,
            "errors": self.errors[:3],
        }


def _entity_records(cpu_result: Dict[str, Any], max_records: int) -> List[Dict[str, Any]]:
    artifacts = cpu_result.get("artifact_paths") or {}
    entity_path = Path(artifacts.get("entities_raw") or "")
    records: List[Dict[str, Any]] = []
    if entity_path.exists():
        for row in read_jsonl(entity_path):
            records.append(row)
            if max_records > 0 and len(records) >= max_records:
                break
    return records


def _entity_text(row: Dict[str, Any]) -> str:
    return " ".join(
        str(part)
        for part in [
            row.get("entity_type", ""),
            row.get("canonical_name", ""),
            row.get("entity_id", ""),
            row.get("source_type", ""),
        ]
        if part
    )


def _encode_texts(model_path: str, texts: List[str], device: str, batch_size: int, max_length: int) -> Tuple[Any, float]:
    import torch  # type: ignore
    import torch.nn.functional as F  # type: ignore
    from transformers import AutoModel, AutoTokenizer  # type: ignore

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True).eval().to(device)
    outputs = []
    started = time.perf_counter()
    with torch.no_grad():
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset:offset + batch_size]
            encoded = tokenizer(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
            encoded = {key: value.to(device) for key, value in encoded.items()}
            vector = model(**encoded).last_hidden_state[:, 0]
            vector = F.normalize(vector, p=2, dim=1)
            outputs.append(vector.detach().cpu())
        if device.startswith("npu"):
            torch.npu.synchronize()
    seconds = time.perf_counter() - started
    return torch.cat(outputs, dim=0), seconds


def _standardize_entities(
    records: List[Dict[str, Any]],
    model_path: str,
    batch_size: int,
    max_length: int,
    threshold: float,
    cpu_benchmark_records: int,
) -> Dict[str, Any]:
    import torch  # type: ignore
    import torch_npu  # type: ignore  # noqa: F401

    texts = [_entity_text(row) for row in records] or [""]
    cpu_records = records[:cpu_benchmark_records] if cpu_benchmark_records > 0 else records
    cpu_texts = [_entity_text(row) for row in cpu_records] or [""]
    label_names = [item[0] for item in ENTITY_LABELS]
    label_texts = [item[1] for item in ENTITY_LABELS]

    cpu_process_started = time.process_time()
    cpu_vectors, cpu_embedding_seconds = _encode_texts(model_path, cpu_texts, "cpu", batch_size, max_length)
    cpu_label_vectors, cpu_label_seconds = _encode_texts(model_path, label_texts, "cpu", batch_size, max_length)
    cpu_process_seconds = time.process_time() - cpu_process_started
    torch.npu.set_device("npu:0")
    with _NpuSmiSampler(interval_seconds=1.0, device_id=0) as npu_sampler:
        npu_vectors, npu_embedding_seconds = _encode_texts(model_path, texts, "npu:0", batch_size, max_length)
        npu_label_vectors, npu_label_seconds = _encode_texts(model_path, label_texts, "npu:0", batch_size, max_length)

        sim_started = time.perf_counter()
        scores = npu_vectors.to("npu:0").matmul(npu_label_vectors.to("npu:0").T)
        top_scores, top_indices = scores.max(dim=1)
        torch.npu.synchronize()
        npu_similarity_seconds = time.perf_counter() - sim_started
    npu_resource_metrics = npu_sampler.summary()
    top_scores_cpu = top_scores.cpu().tolist()
    top_indices_cpu = top_indices.cpu().tolist()

    standardized = []
    kept = 0
    for row, score, index in zip(records, top_scores_cpu, top_indices_cpu):
        predicted_type = label_names[int(index)]
        item = dict(row)
        item["npu_predicted_entity_type"] = predicted_type
        item["npu_entity_type_score"] = round(float(score), 6)
        item["npu_candidate_kept"] = bool(float(score) >= threshold)
        item["npu_model_path"] = model_path
        kept += int(item["npu_candidate_kept"])
        standardized.append(item)

    cpu_total = cpu_embedding_seconds + cpu_label_seconds
    npu_total = npu_embedding_seconds + npu_label_seconds + npu_similarity_seconds
    cpu_count = len(cpu_records)
    npu_count = len(records)
    cpu_seconds_per_record = cpu_total / cpu_count if cpu_count else None
    npu_seconds_per_record = npu_total / npu_count if npu_count else None
    estimated_cpu_full_seconds = (cpu_seconds_per_record or 0.0) * npu_count if npu_count else 0.0
    return {
        "rows": standardized,
        "metrics": {
            "model_path": model_path,
            "record_count": npu_count,
            "npu_record_count": npu_count,
            "cpu_benchmark_record_count": cpu_count,
            "label_count": len(label_names),
            "batch_size": batch_size,
            "max_length": max_length,
            "threshold": threshold,
            "kept_count": kept,
            "cpu_embedding_seconds": round(cpu_total, 6),
            "npu_embedding_seconds": round(npu_embedding_seconds + npu_label_seconds, 6),
            "npu_similarity_seconds": round(npu_similarity_seconds, 6),
            "cpu_total_model_seconds": round(cpu_total, 6),
            "npu_total_model_seconds": round(npu_total, 6),
            "cpu_process_seconds": round(cpu_process_seconds, 6),
            "cpu_compute_utilization_percent": round((cpu_process_seconds / cpu_total) * 100.0, 4) if cpu_total else None,
            "cpu_resource_metrics_status": "process_time_estimated",
            "cpu_resource_metrics_note": "CPU 利用率按当前进程 CPU time / wall time 估算，不等同于整机功耗采样。",
            "npu_resource_metrics": npu_resource_metrics,
            "npu_resource_metrics_status": npu_resource_metrics.get("status"),
            "cpu_seconds_per_record": round(cpu_seconds_per_record, 8) if cpu_seconds_per_record else None,
            "npu_seconds_per_record": round(npu_seconds_per_record, 8) if npu_seconds_per_record else None,
            "estimated_cpu_full_seconds": round(estimated_cpu_full_seconds, 6),
            "estimated_full_speedup": round(estimated_cpu_full_seconds / npu_total, 4) if npu_total else None,
            "model_speedup": round((cpu_seconds_per_record or 0) / npu_seconds_per_record, 4) if npu_seconds_per_record else None,
            "cpu_embedding_shape": list(cpu_vectors.shape),
            "npu_embedding_shape": list(npu_vectors.shape),
            "business_input": "chronic_entity_extract/entities_raw.jsonl",
            "business_output": "npu_entity_standardized.jsonl",
        },
    }


class chronic_entity_extract_model_npu(Mapper):
    def execute(self, sample, params=None):
        params = dict(params or {})
        started = time.perf_counter()
        runtime = _detect_npu_runtime()
        if not runtime.get("npu_available") and not bool(params.get("fallback", True)):
            raise RuntimeError(f"NPU runtime unavailable: {runtime}")

        cpu_started = time.perf_counter()
        cpu_result = execute_operator("chronic_entity_extract", sample, params)
        cpu_rule_seconds = time.perf_counter() - cpu_started

        npu_max_records = int(params.get("npu_max_records", params.get("model_max_records", 0)))
        records = _entity_records(cpu_result, npu_max_records)
        model_path = str(params.get("embedding_model_path") or DEFAULT_EMBEDDING_MODEL_PATH)
        export_root = Path(sample.get("export_path", "./outputs")).resolve()
        out_dir = _ensure_dir(export_root / "chronic_entity_extract_model_npu")
        entity_dir = out_dir / "entities"
        cpu_artifacts = cpu_result.get("artifact_paths") or {}
        source_entity_dir = Path(cpu_artifacts.get("entities", ""))
        if source_entity_dir.exists():
            if entity_dir.exists():
                shutil.rmtree(entity_dir)
            shutil.copytree(source_entity_dir, entity_dir)

        standardized_path = out_dir / "npu_entity_standardized.jsonl"
        if runtime.get("npu_available"):
            npu_payload = _standardize_entities(
                records,
                model_path,
                int(params.get("model_batch_size", 64)),
                int(params.get("model_max_length", 64)),
                float(params.get("candidate_keep_threshold", 0.35)),
                int(params.get("cpu_benchmark_records", 2048)),
            )
            _write_jsonl(standardized_path, npu_payload["rows"])
            model_inference = npu_payload["metrics"]
            fallback_used = False
        else:
            _write_jsonl(standardized_path, [])
            model_inference = {"record_count": len(records), "model_path": model_path, "reason": "NPU runtime unavailable"}
            fallback_used = True

        report_path = out_dir / "entity_extract_model_npu_report.json"
        summary = {
            "entity_count": int((cpu_result.get("summary") or {}).get("entity_count", 0) or 0),
            "backend": "real_bge_embedding_standardization",
            "fallback_used": fallback_used,
            "npu_available": bool(runtime.get("npu_available")),
            "npu_execution_used": bool(runtime.get("npu_available")),
            "cpu_rule_extraction_seconds": round(cpu_rule_seconds, 6),
            "model_inference": model_inference,
            "duration_seconds": round(time.perf_counter() - started, 4),
        }
        _write_json(report_path, {"status": "success", "operator": "chronic_entity_extract_model_npu", "runtime": runtime, "summary": summary, "safety_note": SAFETY_NOTE})
        artifact_paths = {
            "entities": entity_dir.as_posix(),
            "entities_raw": (entity_dir / "entities_raw.jsonl").as_posix(),
            "npu_entity_standardized": standardized_path.as_posix(),
            "report": report_path.as_posix(),
        }
        history = dict(cpu_result.get("pipeline_artifacts") or {})
        for key, value in artifact_paths.items():
            history[key] = value
            history[f"chronic_entity_extract_model_npu.{key}"] = value
        result = dict(cpu_result)
        result.update({"operator": "chronic_entity_extract_model_npu", "artifact_paths": artifact_paths, "pipeline_artifacts": history, "summary": summary})
        return result
