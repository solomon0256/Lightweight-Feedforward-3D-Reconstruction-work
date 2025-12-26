#!/usr/bin/env python3
"""
PQK Experiment Run Logger
=========================
统一的实验日志系统，每次 run 自动产出标准化文件。

Usage:
    from scripts.run_logger import RunLogger
    
    with RunLogger("Q", "fp16", "7scenes_heads") as run:
        run.log_config(config_dict)
        # ... run experiment ...
        run.log_results(results_dict)
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import yaml


class RunLogger:
    """统一的 PQK 实验日志管理器"""
    
    # 与 baseline 完全一致的 summary schema
    SUMMARY_SCHEMA = {
        "model": {
            "name": str,
            "params_total": int,
            "params_encoder": int,
            "params_decoder": int,
            "macs": int,
        },
        "performance": {
            "t_pair_p50_ms": float,
            "t_pair_p95_ms": float,
            "vram_peak_gb": float,
            "throughput_pairs_per_sec": float,
        },
        "quality_depth": {
            "absrel": float,
            "sqrel": float,
            "rmse": float,
            "rmse_log": float,
            "delta1": float,
            "delta2": float,
            "delta3": float,
            "si_log": float,
        },
        "quality_pose_visloc": {
            "median_pos_error_m": float,
            "median_angular_error_deg": float,
            "acc_0.1m_1deg": float,
            "acc_0.25m_2deg": float,
            "acc_0.5m_5deg": float,
            "acc_5m_10deg": float,
        },
        "quality_pose_pairwise": {
            "rre_deg": float,
            "rte_m": float,
        },
    }
    
    def __init__(
        self,
        method: str,  # P, Q, K
        variant: str,  # fp16, int8, pruned_50, distill_small, etc.
        dataset: str,  # 7scenes_heads, scannet, etc.
        seed: int = 0,
        base_dir: str = "runs",
    ):
        """
        初始化 RunLogger
        
        Args:
            method: 方法类型 (P/Q/K)
            variant: 具体变体 (fp16, int8, pruned_50, etc.)
            dataset: 数据集名称
            seed: 随机种子
            base_dir: 实验目录根路径
        """
        self.method = method.upper()
        self.variant = variant
        self.dataset = dataset
        self.seed = seed
        self.base_dir = Path(base_dir)
        
        # 生成实验ID: YYYYMMDD_HHMM_<method>_<variant>_<dataset>_s<seed>
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.exp_id = f"{timestamp}_{self.method}_{self.variant}_{self.dataset}_s{self.seed}"
        
        # 创建实验目录
        self.run_dir = self.base_dir / self.exp_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化日志文件
        self.stdout_log = self.run_dir / "stdout.log"
        self.stderr_log = self.run_dir / "stderr.log"
        
        # 存储配置和结果
        self._config: Dict[str, Any] = {}
        self._results: Dict[str, Any] = {}
        self._raw_results: list = []
        
        print(f"[RunLogger] Experiment: {self.exp_id}")
        print(f"[RunLogger] Directory: {self.run_dir}")
    
    def __enter__(self):
        """Context manager 入口"""
        self._save_git_info()
        self._save_command()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 出口，自动保存所有文件"""
        if exc_type is not None:
            # 记录错误
            with open(self.stderr_log, "a") as f:
                f.write(f"\nException: {exc_type.__name__}: {exc_val}\n")
        
        # 保存配置
        if self._config:
            self._save_config()
        
        # 保存结果
        if self._results:
            self._save_summary()
        
        if self._raw_results:
            self._save_raw_results()
        
        print(f"[RunLogger] Saved to: {self.run_dir}")
        return False
    
    def _save_git_info(self):
        """保存 Git 版本信息"""
        try:
            # Commit hash
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            
            with open(self.run_dir / "git_commit.txt", "w") as f:
                f.write(commit + "\n")
            
            # Diff patch
            diff = subprocess.check_output(
                ["git", "diff"],
                stderr=subprocess.DEVNULL
            ).decode()
            
            with open(self.run_dir / "git_diff.patch", "w") as f:
                f.write(diff)
                
        except subprocess.CalledProcessError:
            print("[RunLogger] Warning: Git info not available")
    
    def _save_command(self):
        """保存执行命令"""
        command = " ".join(sys.argv)
        with open(self.run_dir / "command.txt", "w") as f:
            f.write(f"# Executed at: {datetime.now().isoformat()}\n")
            f.write(f"# Working dir: {os.getcwd()}\n")
            f.write(f"python {command}\n")
    
    def log_config(self, config: Dict[str, Any]):
        """记录实验配置"""
        self._config = {
            "exp_id": self.exp_id,
            "method": self.method,
            "variant": self.variant,
            "dataset": self.dataset,
            "seed": self.seed,
            "timestamp": datetime.now().isoformat(),
            **config
        }
    
    def _save_config(self):
        """保存配置到 YAML"""
        with open(self.run_dir / "config.yaml", "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
    
    def log_results(self, results: Dict[str, Any]):
        """记录聚合结果（与 baseline schema 一致）"""
        self._results = results
    
    def _save_summary(self):
        """保存 summary.json（与 baseline 同 schema）"""
        summary = {
            "exp_id": self.exp_id,
            "method": self.method,
            "variant": self.variant,
            "dataset": self.dataset,
            "timestamp": datetime.now().isoformat(),
            "baseline_ref": "runs/BASELINE_FREEZE/baseline_complete.json",
            **self._results
        }
        
        with open(self.run_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)
    
    def log_raw_result(self, sample_id: str, result: Dict[str, Any]):
        """记录单个样本的原始结果"""
        self._raw_results.append({
            "sample_id": sample_id,
            **result
        })
    
    def _save_raw_results(self):
        """保存原始结果到 JSONL"""
        with open(self.run_dir / "results_raw.jsonl", "w") as f:
            for r in self._raw_results:
                f.write(json.dumps(r) + "\n")
    
    def log_profile(self, profile: Dict[str, Any]):
        """记录性能分析结果"""
        with open(self.run_dir / "profile.json", "w") as f:
            json.dump(profile, f, indent=2)
    
    def log_stdout(self, text: str):
        """追加到 stdout.log"""
        with open(self.stdout_log, "a") as f:
            f.write(text + "\n")
    
    @staticmethod
    def compare_with_baseline(
        summary_path: str,
        baseline_path: str = "runs/BASELINE_FREEZE/baseline_complete.json"
    ) -> Dict[str, Dict[str, float]]:
        """
        与 baseline 对比，计算相对变化
        
        Returns:
            Dict with relative changes for each metric
        """
        with open(summary_path) as f:
            summary = json.load(f)
        
        with open(baseline_path) as f:
            baseline = json.load(f)
        
        comparison = {}
        
        # 对比 quality_depth
        if "quality_depth" in summary and "quality_depth" in baseline:
            comparison["quality_depth"] = {}
            for metric in summary["quality_depth"]:
                if metric in baseline["quality_depth"]:
                    base_val = baseline["quality_depth"][metric]
                    new_val = summary["quality_depth"][metric]
                    if base_val != 0:
                        change = (new_val - base_val) / base_val * 100
                        comparison["quality_depth"][metric] = {
                            "baseline": base_val,
                            "current": new_val,
                            "change_pct": round(change, 2)
                        }
        
        # 对比 performance
        if "performance" in summary and "performance" in baseline:
            comparison["performance"] = {}
            for metric in summary["performance"]:
                if metric in baseline["performance"]:
                    base_val = baseline["performance"][metric]
                    new_val = summary["performance"][metric]
                    if base_val != 0:
                        change = (new_val - base_val) / base_val * 100
                        comparison["performance"][metric] = {
                            "baseline": base_val,
                            "current": new_val,
                            "change_pct": round(change, 2)
                        }
        
        return comparison


def create_exp_id(method: str, variant: str, dataset: str, seed: int = 0) -> str:
    """生成标准实验ID"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{timestamp}_{method.upper()}_{variant}_{dataset}_s{seed}"


# 示例用法
if __name__ == "__main__":
    # Demo: 创建一个 Q-FP16 实验
    with RunLogger("Q", "fp16", "7scenes_heads") as run:
        # 记录配置
        run.log_config({
            "model": {
                "name": "DUSt3R_ViTLarge_BaseDecoder_512_dpt",
                "precision": "fp16",
            },
            "evaluation": {
                "dataset_path": "datasets/7-scenes/heads",
                "num_pairs": 100,
            }
        })
        
        # 模拟实验结果
        run.log_results({
            "quality_depth": {
                "absrel": 0.1170,
                "sqrel": 0.0361,
                "rmse": 0.1448,
                "rmse_log": 0.1655,
                "delta1": 0.8990,
                "delta2": 0.9630,
                "delta3": 0.9775,
                "si_log": 0.1615,
            },
            "performance": {
                "t_pair_p50_ms": 180.0,  # FP16 更快
                "vram_peak_gb": 1.8,     # FP16 更省显存
            }
        })
        
        # 记录性能分析
        run.log_profile({
            "latency_ms": {"min": 170, "p50": 180, "p95": 195, "max": 210},
            "vram_gb": {"baseline": 0.8, "peak": 1.8, "delta": 1.0},
            "speedup_vs_baseline": 1.96,
        })
    
    print("\n[Demo] Run completed!")
