"""지역 데이터셋 버전 관리: 등록 → 검증 → 활성화 → (문제 시) 롤백.

저장 위치: data_processed/datasets/<name>/v<k>.nc (등록할 때 복사하며, 한 번 등록한 버전 파일은 덮어쓰지 않는다)
목록:     data_processed/datasets/registry.json
설정에서 쓰기: regions.path: "registry:<name>" (활성 버전) 또는 "registry:<name>@v<k>" (고정 버전)

검증 (validate_dataset)
  오류 (활성화 막음): 지역 0개, id 중복, 인구 음수·0, 면적 <= 0, 위경도 범위 밖, C 음수·행 합 != 1,
                     omega 음수·대각 != 0, 이동 불균형 (상대 1e-9 초과), 기후 범위 (RH 0~100, 기온 -60~60) 밖
  경고: 인구 결측 (미확보), 기후 결측, provenance 의 출처 정보 없음, 합성 자료 표시
갱신 비교 (diff): 지역 집합 변화, 지역별 인구 상대 변화 (5% 넘으면 경고), 이동·접촉 행렬 변화
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from .dataset import RegionDataset

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data_processed" / "datasets"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_dataset(ds: RegionDataset) -> dict:
    err, warn = [], []
    if ds.K == 0:
        err.append("지역이 없다")
        return {"ok": False, "errors": err, "warnings": warn}
    if len(set(ds.ids)) != ds.K:
        err.append("지역 id 중복")
    pop = ds.population
    if np.any(np.isfinite(pop) & (pop <= 0)):
        err.append("인구 0 이하 지역")
    if np.any(~np.isfinite(pop)):
        warn.append(f"인구 결측(미확보) {int(np.sum(~np.isfinite(pop)))} 지역: 시뮬레이션에 쓸 수 없음")
    if np.any(ds.area_km2 <= 0):
        err.append("면적 0 이하 지역")
    if np.any(np.abs(ds.lat) > 90) or np.any(np.abs(ds.lon) > 180):
        err.append("위경도 범위 밖")
    if np.all(np.isfinite(ds.contact)):
        if np.any(ds.contact < 0) or np.max(np.abs(ds.contact.sum(axis=1) - 1)) > 1e-9:
            err.append("접촉 행렬 C 가 음수이거나 행 합이 1 이 아니다")
    if np.all(np.isfinite(ds.mobility)):
        if np.any(ds.mobility < 0) or np.any(np.diag(ds.mobility) != 0):
            err.append("이동률 omega 가 음수이거나 대각이 0 이 아니다")
        if np.all(np.isfinite(pop)):
            net = ds.mobility.T @ pop - ds.mobility.sum(axis=1) * pop
            if np.max(np.abs(net) / pop) > 1e-9:
                err.append("이동 불균형: 감염이 없어도 인구가 재분포된다 (D-010 은 균형 이동을 요구)")
    if ds.tavg is not None:
        if np.any(~np.isfinite(ds.tavg)) or np.any(~np.isfinite(ds.rh)):
            warn.append("기후 결측 칸 있음")
        T, RH = ds.tavg[np.isfinite(ds.tavg)], ds.rh[np.isfinite(ds.rh)]
        if np.any((T < -60) | (T > 60)) or np.any((RH < 0) | (RH > 100)):
            err.append("기후 값 범위 밖")
    p = ds.provenance or {}
    if not p.get("population") or not p.get("boundaries"):
        warn.append("provenance 에 인구·경계 출처 기록이 없다")
    if ds.synthetic:
        warn.append("합성 자료 (synthetic = 1): 실제 지역 자료가 아니다")
    return {"ok": not err, "errors": err, "warnings": warn}


def _pop_source(prov: dict):
    pm = prov.get("population") or {}
    if pm.get("source"):
        return pm["source"]
    if isinstance(pm.get("primary"), dict):                  # 표 + 보조 출처를 합친 경우 (예: World Bank + NE POP_EST)
        return f"{pm['primary'].get('source')} (+ 보조: {(pm.get('fallback') or {}).get('source')})"
    return None


class Registry:
    def __init__(self, store: Path | None = None):
        """store 를 주지 않으면 환경 변수 SEIR_SIM_DATASET_STORE, 그것도 없으면 data_processed/datasets."""
        import os
        self.store = Path(store or os.environ.get("SEIR_SIM_DATASET_STORE") or STORE)
        self.path = self.store / "registry.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self):
        self.store.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False))
        tmp.replace(self.path)

    def list(self) -> dict:
        return self.data

    def register(self, name: str, src: str | Path, note: str = "") -> str:
        src = Path(src)
        ds = RegionDataset.load(src)
        v = validate_dataset(ds)
        entry = self.data.setdefault(name, {"versions": [], "active": None, "history": []})
        version = f"v{len(entry['versions']) + 1}"
        dst = self.store / name / f"{version}.nc"
        if dst.exists():
            raise FileExistsError(f"{dst} 가 이미 있다 (등록된 버전은 덮어쓰지 않는다)")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        prov = ds.provenance or {}
        entry["versions"].append({
            "version": version, "file": str(dst.relative_to(ROOT)) if dst.is_relative_to(ROOT) else str(dst),
            "sha256": _sha256(dst), "registered_from": str(src),
            "registered_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "note": note,
            "K": ds.K, "population_total": float(np.nansum(ds.population)), "synthetic": ds.synthetic,
            "population_source": _pop_source(prov), "validation": v,
            "diff_vs_active": self.diff(name, None, ds) if entry["active"] else None})
        self._save()
        return version

    def _entry(self, name, version):
        e = self.data[name]
        for v in e["versions"]:
            if v["version"] == version:
                return v
        raise KeyError(f"{name}@{version} 없음")

    def activate(self, name: str, version: str, force: bool = False) -> None:
        v = self._entry(name, version)
        if not v["validation"]["ok"] and not force:
            raise ValueError(f"{name}@{version} 검증 실패: {v['validation']['errors']}")
        if _sha256(ROOT / v["file"]) != v["sha256"]:
            raise ValueError(f"{name}@{version} 파일의 SHA-256 이 등록 때와 다르다 (변조·손상)")
        e = self.data[name]
        if e["active"] and e["active"] != version:
            e["history"].append(e["active"])
        e["active"] = version
        self._save()

    def rollback(self, name: str) -> str:
        e = self.data[name]
        if not e["history"]:
            raise ValueError(f"{name}: 되돌릴 이전 활성 버전이 없다")
        prev = e["history"].pop()
        e["active"] = prev
        self._save()
        return prev

    def resolve(self, spec: str) -> Path:
        """'name' 또는 'name@vk' -> 파일 경로 (SHA-256 확인)."""
        name, _, version = spec.partition("@")
        e = self.data.get(name)
        if e is None:
            raise KeyError(f"등록되지 않은 데이터셋: {name}")
        version = version or e["active"]
        if not version:
            raise ValueError(f"{name}: 활성 버전이 없다 (activate 필요)")
        v = self._entry(name, version)
        path = ROOT / v["file"]
        if _sha256(path) != v["sha256"]:
            raise ValueError(f"{name}@{version} 파일의 SHA-256 이 등록 때와 다르다")
        return path

    def diff(self, name: str, version: str | None, new: RegionDataset) -> dict:
        """활성(또는 지정) 버전과 새 데이터셋 비교."""
        old = RegionDataset.load(self.resolve(name if version is None else f"{name}@{version}"))
        common = [i for i in new.ids if i in old.ids]
        oi = {r: k for k, r in enumerate(old.ids)}
        ni = {r: k for k, r in enumerate(new.ids)}
        rel = {r: float(new.population[ni[r]] / old.population[oi[r]] - 1) for r in common
               if np.isfinite(old.population[oi[r]]) and np.isfinite(new.population[ni[r]]) and old.population[oi[r]] > 0}
        out = {"added": sorted(set(new.ids) - set(old.ids)), "removed": sorted(set(old.ids) - set(new.ids)),
               "population_rel_change_max": max(map(abs, rel.values())) if rel else None,
               "population_changed_over_5pct": sorted(r for r, v in rel.items() if abs(v) > 0.05)}
        if not out["added"] and not out["removed"]:
            o = [oi[r] for r in new.ids]
            for key in ("mobility", "contact"):
                a, b = getattr(old, key)[np.ix_(o, o)], getattr(new, key)
                if np.all(np.isfinite(a)) and np.all(np.isfinite(b)):
                    out[f"{key}_max_abs_change"] = float(np.max(np.abs(a - b)))
        return out
