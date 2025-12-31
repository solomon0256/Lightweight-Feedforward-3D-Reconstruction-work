"""
配置加载器 - 统一读取 workload.yaml / eval.yaml / 实验配置
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field


def load_yaml(path: Union[str, Path]) -> Dict[str, Any]:
    """加载单个 YAML 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并多个配置字典，后者覆盖前者"""
    result = {}
    for config in configs:
        for key, value in config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_configs(result[key], value)
            else:
                result[key] = value
    return result


@dataclass
class ProjectPaths:
    """项目路径管理"""
    root: Path
    config: Path
    expconfigs: Path
    scripts: Path
    logs: Path
    outputs: Path
    checkpoints: Path
    datasets: Path
    reports: Path
    
    @classmethod
    def from_root(cls, root: Union[str, Path]) -> 'ProjectPaths':
        root = Path(root)
        return cls(
            root=root,
            config=root / 'config',
            expconfigs=root / 'expconfigs',
            scripts=root / 'scripts',
            logs=root / 'logs',
            outputs=root / 'outputs',
            checkpoints=root / 'outputs' / 'checkpoints',
            datasets=root / 'datasets',
            reports=root / 'reports',
        )
    
    def ensure_dirs(self):
        """确保所有目录存在"""
        for p in [self.logs, self.outputs, self.checkpoints, self.datasets, self.reports]:
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class ExperimentConfig:
    """实验配置容器"""
    # 基础信息
    exp_id: str = ""
    exp_name: str = ""
    seed: int = 42
    
    # 工作负载口径
    workload: Dict[str, Any] = field(default_factory=dict)
    
    # 评测口径
    eval: Dict[str, Any] = field(default_factory=dict)
    
    # 实验特定配置
    experiment: Dict[str, Any] = field(default_factory=dict)
    
    # 路径
    paths: Optional[ProjectPaths] = None
    
    @classmethod
    def load(
        cls,
        project_root: Union[str, Path],
        exp_config_name: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None
    ) -> 'ExperimentConfig':
        """
        加载完整实验配置
        
        Args:
            project_root: 项目根目录
            exp_config_name: 实验配置文件名（如 'distill.yaml'）
            overrides: 命令行覆盖参数
        """
        paths = ProjectPaths.from_root(project_root)
        
        # 1. 加载全局口径
        workload = load_yaml(paths.config / 'workload.yaml')
        eval_cfg = load_yaml(paths.config / 'eval.yaml')
        
        # 2. 加载实验配置（可选）
        exp_cfg = {}
        if exp_config_name:
            # 支持完整路径或仅文件名
            exp_config_path = Path(exp_config_name)
            if exp_config_path.is_absolute() or exp_config_path.exists():
                # 如果是绝对路径或已存在的相对路径，直接使用
                exp_path = exp_config_path if exp_config_path.is_absolute() else paths.root / exp_config_path
            else:
                # 否则在expconfigs目录下查找
                exp_path = paths.expconfigs / exp_config_path.name
            
            if exp_path.exists():
                exp_cfg = load_yaml(exp_path)
            else:
                print(f"[WARN] Experiment config not found: {exp_path}")
        
        # 3. 应用覆盖
        if overrides:
            exp_cfg = merge_configs(exp_cfg, overrides)
        
        # 4. 提取基础信息
        run_cfg = exp_cfg.get('run', {})
        exp_name = run_cfg.get('exp_name', exp_config_name or 'unnamed')
        seed = run_cfg.get('seed', workload.get('seed', 42))
        
        return cls(
            exp_id=f"{exp_name}_{seed}",
            exp_name=exp_name,
            seed=seed,
            workload=workload,
            eval=eval_cfg,
            experiment=exp_cfg,
            paths=paths,
        )
    
    # ============ 便捷访问器 ============
    
    @property
    def input_shape(self) -> tuple:
        """获取输入形状 [B, C, H, W]"""
        return tuple(self.workload.get('input', {}).get('shape', [1, 3, 512, 384]))
    
    @property
    def device(self) -> str:
        return self.workload.get('device', 'cuda')
    
    @property
    def pair_graph_k(self) -> int:
        return self.workload.get('pair_graph', {}).get('k', 4)
    
    @property
    def quality_metrics(self) -> list:
        """质量指标列表"""
        return [m['name'] for m in self.eval.get('metrics', {}).get('quality', [])]
    
    @property
    def efficiency_metrics(self) -> list:
        """效率指标列表"""
        return [m['name'] for m in self.eval.get('metrics', {}).get('efficiency', [])]
    
    @property
    def resource_metrics(self) -> list:
        """资源指标列表"""
        return [m['name'] for m in self.eval.get('metrics', {}).get('resources', [])]
    
    @property
    def quality_drop_threshold(self) -> float:
        """精度跌幅阈值 (%)"""
        return self.eval.get('thresholds', {}).get('quality_drop_main_pct', 1.5)
    
    @property
    def speedup_target(self) -> float:
        """加速目标 (%)"""
        return self.eval.get('thresholds', {}).get('speedup_pair_p50_pct', 50)
    
    @property
    def early_stop_patience(self) -> int:
        return self.eval.get('early_stop', {}).get('no_improve_ckpt', 3)
    
    def get_max_epochs(self, stage: str = 'distill') -> int:
        """获取最大 epoch 数"""
        return self.eval.get('early_stop', {}).get('max_epoch', {}).get(stage, 30)


def get_project_root() -> Path:
    """自动检测项目根目录"""
    # 从当前文件向上查找包含 config/ 的目录
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / 'config').exists() and (parent / 'scripts').exists():
            return parent
    # 回退到当前工作目录
    return Path.cwd()


# ============ CLI 参数解析辅助 ============

def add_common_args(parser):
    """添加通用命令行参数"""
    parser.add_argument('--project-root', type=str, default=None,
                        help='项目根目录（默认自动检测）')
    parser.add_argument('--exp-config', type=str, default=None,
                        help='实验配置文件名（如 distill.yaml）')
    parser.add_argument('--seed', type=int, default=None,
                        help='随机种子（覆盖配置）')
    parser.add_argument('--device', type=str, default=None,
                        help='设备（cuda/cpu）')
    parser.add_argument('--dry-run', action='store_true',
                        help='干跑模式（不实际运行，仅验证配置）')
    return parser


def config_from_args(args) -> ExperimentConfig:
    """从命令行参数创建配置"""
    root = Path(args.project_root) if args.project_root else get_project_root()
    
    overrides = {}
    if args.seed is not None:
        overrides['run'] = {'seed': args.seed}
    if args.device is not None:
        overrides['device'] = args.device
    
    return ExperimentConfig.load(
        project_root=root,
        exp_config_name=args.exp_config,
        overrides=overrides if overrides else None
    )


# ============ 测试 ============

if __name__ == '__main__':
    # 快速测试
    root = get_project_root()
    print(f"Project root: {root}")
    
    cfg = ExperimentConfig.load(root, 'distill.yaml')
    print(f"Exp ID: {cfg.exp_id}")
    print(f"Input shape: {cfg.input_shape}")
    print(f"Quality metrics: {cfg.quality_metrics}")
    print(f"Quality drop threshold: {cfg.quality_drop_threshold}%")
