"""
统一日志写入器 - 符合 unified_log_schema.json 规范
"""
import json
import csv
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, asdict, field
import subprocess


def get_git_commit_hash() -> str:
    """获取当前 Git commit hash"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()[:8] if result.returncode == 0 else 'unknown'
    except Exception:
        return 'unknown'


def get_env_versions() -> Dict[str, str]:
    """获取环境版本信息"""
    versions = {}
    
    try:
        import torch
        versions['pytorch_ver'] = torch.__version__
        versions['cuda_ver'] = torch.version.cuda or 'N/A'
    except ImportError:
        versions['pytorch_ver'] = 'N/A'
        versions['cuda_ver'] = 'N/A'
    
    try:
        import tensorrt
        versions['tensorrt_ver'] = tensorrt.__version__
    except ImportError:
        versions['tensorrt_ver'] = None
    
    try:
        import modelopt
        versions['modelopt_ver'] = modelopt.__version__
    except ImportError:
        versions['modelopt_ver'] = None
    
    return versions


@dataclass
class ExperimentLog:
    """
    实验日志数据结构 - 对齐 unified_log_schema.json
    
    所有字段都有默认值，必填字段在写入时会检查
    """
    # ===== 基础信息 (必填) =====
    exp_id: str = ""
    combo: str = ""  # K-only / Q-only / K→Q / P-only / etc.
    seed: int = 42
    dataset_id: str = ""
    split: str = "val"
    
    # ===== 超参数 (可选) =====
    rho: Optional[float] = None      # 剪枝率
    T: Optional[float] = None        # 蒸馏温度
    beta: Optional[float] = None     # KD 权重
    gamma: Optional[float] = None    # FD 权重
    bits_w: Optional[int] = None     # 权重位宽
    bits_a: Optional[int] = None     # 激活位宽
    keep_list: Optional[str] = None  # 保留 FP16 的层
    
    # ===== 资源指标 (必填) =====
    params_M: float = 0.0    # 参数量 (百万)
    flops_G: float = 0.0     # 计算量 (GFLOPs)
    size_MB: float = 0.0     # 模型体积 (MB)
    vram_GB: float = 0.0     # 峰值显存 (GB)
    
    # ===== 质量指标 (必填) =====
    chamfer: float = 0.0
    absrel: float = 0.0
    rmse: float = 0.0
    delta1: float = 0.0
    reproj_px: float = 0.0
    
    # ===== 效率指标 (必填) =====
    t_pair_p50_ms: float = 0.0   # 单 pair 时延 p50
    t_pair_p95_ms: float = 0.0   # 单 pair 时延 p95
    t_scene_s: float = 0.0       # 场景耗时
    pairs_per_sec: float = 0.0   # 吞吐量
    
    # ===== 端侧信息 (可选) =====
    edge_device: Optional[Dict[str, Any]] = None
    
    # ===== 数据信息 (可选) =====
    num_pairs: Optional[int] = None
    calibration_set_hash: Optional[str] = None
    
    # ===== 环境信息 =====
    pytorch_ver: Optional[str] = None
    cuda_ver: Optional[str] = None
    tensorrt_ver: Optional[str] = None
    modelopt_ver: Optional[str] = None
    commit_hash: str = ""
    
    # ===== 元信息 (必填) =====
    notes: Optional[str] = None
    gpu_hours: float = 0.0
    datetime: str = ""
    
    def __post_init__(self):
        """自动填充可推断的字段"""
        if not self.datetime:
            self.datetime = datetime.now().isoformat()
        if not self.commit_hash:
            self.commit_hash = get_git_commit_hash()
        
        # 填充环境版本
        if self.pytorch_ver is None:
            env = get_env_versions()
            self.pytorch_ver = env.get('pytorch_ver')
            self.cuda_ver = env.get('cuda_ver')
            self.tensorrt_ver = env.get('tensorrt_ver')
            self.modelopt_ver = env.get('modelopt_ver')
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return asdict(self)
    
    def validate(self, schema_path: Optional[Path] = None) -> List[str]:
        """
        验证日志是否符合 schema
        返回缺失的必填字段列表
        """
        required = [
            'exp_id', 'combo', 'seed', 'dataset_id', 'split',
            'params_M', 'flops_G', 'size_MB', 'vram_GB',
            'chamfer', 'absrel', 'rmse', 'delta1', 'reproj_px',
            't_pair_p50_ms', 't_pair_p95_ms', 't_scene_s', 'pairs_per_sec',
            'gpu_hours', 'commit_hash', 'datetime'
        ]
        
        data = self.to_dict()
        missing = []
        for field in required:
            if field not in data or data[field] is None or data[field] == "":
                missing.append(field)
        
        return missing


class UnifiedLogger:
    """
    统一日志管理器
    
    支持：
    - JSON 格式写入（推荐）
    - CSV 格式追加
    - 多实验合并
    """
    
    def __init__(self, log_dir: Union[str, Path]):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def save_json(self, log: ExperimentLog, filename: str) -> Path:
        """保存单条日志为 JSON"""
        if not filename.endswith('.json'):
            filename += '.json'
        
        path = self.log_dir / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(log.to_dict(), f, indent=2, ensure_ascii=False)
        
        return path
    
    def append_csv(self, log: ExperimentLog, filename: str = 'all_experiments.csv') -> Path:
        """追加日志到 CSV（用于汇总）"""
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        path = self.log_dir / filename
        data = log.to_dict()
        
        # 扁平化 edge_device
        if data.get('edge_device'):
            for k, v in data['edge_device'].items():
                data[f'edge_{k}'] = v
            del data['edge_device']
        else:
            data['edge_device'] = None
        
        file_exists = path.exists()
        
        with open(path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(data)
        
        return path
    
    def load_json(self, filename: str) -> ExperimentLog:
        """加载 JSON 日志"""
        if not filename.endswith('.json'):
            filename += '.json'
        
        path = self.log_dir / filename
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return ExperimentLog(**data)
    
    def list_logs(self, pattern: str = '*.json') -> List[Path]:
        """列出所有日志文件"""
        return list(self.log_dir.glob(pattern))
    
    def merge_to_table(self, output: str = 'result_table.csv') -> Path:
        """合并所有 JSON 日志到一个表格"""
        logs = []
        for json_path in self.list_logs('*.json'):
            if json_path.name == 'unified_log_schema.json':
                continue
            try:
                log = self.load_json(json_path.name)
                logs.append(log)
            except Exception as e:
                print(f"Warning: Failed to load {json_path}: {e}")
        
        if not logs:
            print("No logs found to merge")
            return None
        
        # 写入 CSV
        output_path = self.log_dir.parent / 'reports' / output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        all_data = [log.to_dict() for log in logs]
        
        # 扁平化
        for data in all_data:
            if data.get('edge_device'):
                for k, v in data['edge_device'].items():
                    data[f'edge_{k}'] = v
            data.pop('edge_device', None)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_data[0].keys())
            writer.writeheader()
            writer.writerows(all_data)
        
        return output_path


# ============ 便捷函数 ============

def create_log(
    exp_id: str,
    combo: str,
    dataset_id: str = "default",
    **kwargs
) -> ExperimentLog:
    """快速创建日志对象"""
    return ExperimentLog(
        exp_id=exp_id,
        combo=combo,
        dataset_id=dataset_id,
        **kwargs
    )


def save_experiment_log(
    log: ExperimentLog,
    log_dir: Union[str, Path],
    also_csv: bool = True
) -> Dict[str, Path]:
    """
    保存实验日志（JSON + 可选 CSV）
    
    Returns:
        {'json': Path, 'csv': Path or None}
    """
    logger = UnifiedLogger(log_dir)
    
    # 验证
    missing = log.validate()
    if missing:
        print(f"Warning: Missing required fields: {missing}")
    
    # 保存
    json_path = logger.save_json(log, f"{log.exp_id}.json")
    csv_path = logger.append_csv(log) if also_csv else None
    
    return {'json': json_path, 'csv': csv_path}


# ============ 测试 ============

if __name__ == '__main__':
    # 创建测试日志
    log = ExperimentLog(
        exp_id="test_baseline_v1",
        combo="baseline",
        dataset_id="test_set",
        split="val",
        params_M=123.4,
        flops_G=456.7,
        size_MB=234.5,
        vram_GB=8.0,
        chamfer=0.05,
        absrel=0.10,
        rmse=0.15,
        delta1=0.95,
        reproj_px=2.5,
        t_pair_p50_ms=50.0,
        t_pair_p95_ms=80.0,
        t_scene_s=10.0,
        pairs_per_sec=20.0,
        gpu_hours=0.5,
    )
    
    # 验证
    missing = log.validate()
    print(f"Missing fields: {missing}")
    
    # 打印
    print(json.dumps(log.to_dict(), indent=2))
