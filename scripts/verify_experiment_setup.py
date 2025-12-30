#!/usr/bin/env python3
"""
实验前完整验证脚本

功能：
- 验证所有配置文件存在且格式正确
- 验证所有脚本存在且可执行
- 验证路径和目录结构
- 验证模型权重
- 验证数据集（如果存在）
- 生成详细验证报告

使用方法：
    python3 scripts/verify_experiment_setup.py --exp K-only
    python3 scripts/verify_experiment_setup.py --exp Q-only
    python3 scripts/verify_experiment_setup.py --exp K-to-Q
    python3 scripts/verify_experiment_setup.py --all
"""

import argparse
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

class ExperimentVerifier:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.errors = []
        self.warnings = []
        self.info = []
        
    def verify_file_exists(self, file_path: Path, description: str) -> bool:
        """验证文件存在"""
        if file_path.exists():
            self.info.append(f"✅ {description}: {file_path} 存在")
            return True
        else:
            self.errors.append(f"❌ {description}: {file_path} 不存在")
            return False
    
    def verify_yaml_config(self, config_path: Path, description: str) -> Tuple[bool, Dict]:
        """验证YAML配置文件"""
        if not config_path.exists():
            self.errors.append(f"❌ {description}: {config_path} 不存在")
            return False, {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if config is None:
                self.errors.append(f"❌ {description}: {config_path} 为空或格式错误")
                return False, {}
            
            self.info.append(f"✅ {description}: {config_path} 格式正确")
            self.info.append(f"   配置内容: {json.dumps(config, indent=4, ensure_ascii=False, default=str)[:500]}...")
            return True, config
        except yaml.YAMLError as e:
            self.errors.append(f"❌ {description}: {config_path} YAML解析错误: {e}")
            return False, {}
        except Exception as e:
            self.errors.append(f"❌ {description}: {config_path} 读取错误: {e}")
            return False, {}
    
    def verify_script(self, script_path: Path, description: str) -> bool:
        """验证脚本存在且可执行"""
        if not script_path.exists():
            self.errors.append(f"❌ {description}: {script_path} 不存在")
            return False
        
        if not script_path.is_file():
            self.errors.append(f"❌ {description}: {config_path} 不是文件")
            return False
        
        # 检查文件大小（空文件可能有问题）
        if script_path.stat().st_size == 0:
            self.warnings.append(f"⚠️ {description}: {script_path} 文件为空")
        
        self.info.append(f"✅ {description}: {script_path} 存在")
        self.info.append(f"   文件大小: {script_path.stat().st_size} 字节")
        
        return True
    
    def verify_directory(self, dir_path: Path, description: str, create_if_missing: bool = False) -> bool:
        """验证目录存在"""
        if dir_path.exists() and dir_path.is_dir():
            self.info.append(f"✅ {description}: {dir_path} 存在")
            return True
        elif create_if_missing:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                self.info.append(f"✅ {description}: {dir_path} 已创建")
                return True
            except Exception as e:
                self.errors.append(f"❌ {description}: {dir_path} 创建失败: {e}")
                return False
        else:
            self.warnings.append(f"⚠️ {description}: {dir_path} 不存在（将自动创建）")
            return True
    
    def verify_k_only_setup(self) -> bool:
        """验证K-only（蒸馏）实验设置"""
        print("\n" + "="*80)
        print("验证 K-only（蒸馏）实验设置")
        print("="*80)
        
        all_ok = True
        
        # 1. 验证配置文件
        config_path = self.project_root / "expconfigs" / "distill.yaml"
        ok, config = self.verify_yaml_config(config_path, "蒸馏配置文件")
        if not ok:
            all_ok = False
        else:
            # 验证关键配置项
            required_keys = ['run', 'data', 'teacher', 'student', 'distill', 'optim']
            for key in required_keys:
                if key not in config:
                    self.errors.append(f"❌ 配置文件缺少必需项: {key}")
                    all_ok = False
                else:
                    self.info.append(f"   配置项 {key}: {json.dumps(config[key], indent=2, default=str)[:200]}")
        
        # 2. 验证脚本
        script_path = self.project_root / "scripts" / "train_distill.py"
        if not self.verify_script(script_path, "蒸馏训练脚本"):
            all_ok = False
        
        # 3. 验证输出目录
        output_dirs = [
            ("checkpoints", "checkpoints/"),
            ("outputs", "outputs/"),
            ("logs", "logs/distill"),
        ]
        for desc, path in output_dirs:
            dir_path = self.project_root / path
            self.verify_directory(dir_path, f"{desc}目录", create_if_missing=True)
        
        # 4. 验证Teacher模型
        teacher_path = self.project_root / "checkpoints" / "DUSt3R_teacher.safetensors"
        if not teacher_path.exists():
            # 检查HuggingFace缓存
            hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
            if hf_cache.exists():
                self.info.append(f"✅ Teacher模型将在首次运行时从HuggingFace下载")
            else:
                self.warnings.append(f"⚠️ Teacher模型不存在，将在首次运行时下载")
        else:
            self.info.append(f"✅ Teacher模型: {teacher_path} 存在")
        
        # 5. 验证数据集路径（如果配置了）
        if config and 'data' in config:
            train_set = config['data'].get('train_set', '')
            if train_set and train_set != 'datasets/train_pairs.lst':
                train_path = self.project_root / train_set
                if train_path.exists():
                    self.info.append(f"✅ 训练集列表: {train_path} 存在")
                else:
                    self.warnings.append(f"⚠️ 训练集列表: {train_path} 不存在（将使用dummy数据）")
        
        return all_ok
    
    def verify_q_only_setup(self) -> bool:
        """验证Q-only（量化）实验设置"""
        print("\n" + "="*80)
        print("验证 Q-only（量化）实验设置")
        print("="*80)
        
        all_ok = True
        
        # 1. 验证配置文件
        config_path = self.project_root / "expconfigs" / "quant.yaml"
        ok, config = self.verify_yaml_config(config_path, "量化配置文件")
        if not ok:
            all_ok = False
        else:
            # 验证关键配置项
            required_keys = ['run', 'model', 'quant']
            for key in required_keys:
                if key not in config:
                    self.errors.append(f"❌ 配置文件缺少必需项: {key}")
                    all_ok = False
                else:
                    self.info.append(f"   配置项 {key}: {json.dumps(config[key], indent=2, default=str)[:200]}")
            
            # 验证quant下的calibration（嵌套结构）
            if 'quant' in config and 'calibration' in config['quant']:
                self.info.append(f"   配置项 quant.calibration: {json.dumps(config['quant']['calibration'], indent=2, default=str)[:200]}")
            elif 'quant' in config:
                self.warnings.append(f"⚠️ quant配置缺少calibration项（将使用dummy数据）")
        
        # 2. 验证脚本
        script_path = self.project_root / "scripts" / "quantize.py"
        if not self.verify_script(script_path, "量化脚本"):
            all_ok = False
        
        # 3. 验证输出目录
        output_dirs = [
            ("checkpoints", "checkpoints/"),
            ("outputs", "outputs/"),
            ("logs", "logs/quant"),
        ]
        for desc, path in output_dirs:
            dir_path = self.project_root / path
            self.verify_directory(dir_path, f"{desc}目录", create_if_missing=True)
        
        # 4. 验证输入模型（如果指定了）
        if config and 'model' in config:
            model_path = config['model'].get('weights_fp32', '')
            if model_path:
                model_full_path = self.project_root / model_path
                if model_full_path.exists():
                    self.info.append(f"✅ 输入模型: {model_full_path} 存在")
                else:
                    self.warnings.append(f"⚠️ 输入模型: {model_full_path} 不存在（Q-only将使用baseline模型）")
        
        # 5. 验证校准数据集
        if config and 'quant' in config and 'calibration' in config['quant']:
            calib_list = config['quant']['calibration'].get('list', '')
            if calib_list:
                calib_path = self.project_root / calib_list
                if calib_path.exists():
                    self.info.append(f"✅ 校准数据集列表: {calib_path} 存在")
                else:
                    self.warnings.append(f"⚠️ 校准数据集列表: {calib_path} 不存在（将使用dummy数据）")
        
        return all_ok
    
    def verify_k_to_q_setup(self) -> bool:
        """验证K→Q组合实验设置"""
        print("\n" + "="*80)
        print("验证 K→Q（蒸馏+量化）组合实验设置")
        print("="*80)
        
        all_ok = True
        
        # 1. 验证K-only已完成（检查student模型）
        student_path = self.project_root / "outputs" / "checkpoints" / "student_fp32_best.pth"
        if student_path.exists():
            self.info.append(f"✅ Student模型: {student_path} 存在（K-only已完成）")
        else:
            self.warnings.append(f"⚠️ Student模型: {student_path} 不存在（需要先完成K-only实验）")
            all_ok = False
        
        # 2. 验证量化配置（复用Q-only配置）
        all_ok = self.verify_q_only_setup() and all_ok
        
        return all_ok
    
    def generate_report(self, output_file: str = "logs/experiment_verification_report.txt"):
        """生成验证报告"""
        report_path = self.project_root / output_file
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("实验设置验证报告\n")
            f.write(f"生成时间: {datetime.now().isoformat()}\n")
            f.write("="*80 + "\n\n")
            
            f.write("## 验证结果摘要\n\n")
            f.write(f"- 错误: {len(self.errors)} 个\n")
            f.write(f"- 警告: {len(self.warnings)} 个\n")
            f.write(f"- 信息: {len(self.info)} 条\n\n")
            
            if self.errors:
                f.write("## ❌ 错误\n\n")
                for error in self.errors:
                    f.write(f"{error}\n")
                f.write("\n")
            
            if self.warnings:
                f.write("## ⚠️ 警告\n\n")
                for warning in self.warnings:
                    f.write(f"{warning}\n")
                f.write("\n")
            
            f.write("## ✅ 详细信息\n\n")
            for info in self.info:
                f.write(f"{info}\n")
        
        print(f"\n验证报告已保存到: {report_path}")
        return report_path

def main():
    parser = argparse.ArgumentParser(description="验证实验设置")
    parser.add_argument("--exp", choices=["K-only", "Q-only", "K-to-Q"], help="验证特定实验")
    parser.add_argument("--all", action="store_true", help="验证所有实验")
    parser.add_argument("--project-root", type=str, default=None, help="项目根目录")
    
    args = parser.parse_args()
    
    # 确定项目根目录
    if args.project_root:
        project_root = Path(args.project_root)
    else:
        project_root = Path(__file__).resolve().parent.parent
    
    verifier = ExperimentVerifier(project_root)
    
    if args.all:
        print("验证所有实验设置...")
        verifier.verify_k_only_setup()
        verifier.verify_q_only_setup()
        verifier.verify_k_to_q_setup()
    elif args.exp == "K-only":
        verifier.verify_k_only_setup()
    elif args.exp == "Q-only":
        verifier.verify_q_only_setup()
    elif args.exp == "K-to-Q":
        verifier.verify_k_to_q_setup()
    else:
        print("请指定 --exp 或 --all")
        return 1
    
    # 生成报告
    report_path = verifier.generate_report()
    
    # 打印摘要
    print("\n" + "="*80)
    print("验证摘要")
    print("="*80)
    print(f"错误: {len(verifier.errors)} 个")
    print(f"警告: {len(verifier.warnings)} 个")
    print(f"信息: {len(verifier.info)} 条")
    
    if verifier.errors:
        print("\n❌ 发现错误，请修复后再开始实验！")
        return 1
    elif verifier.warnings:
        print("\n⚠️ 发现警告，请检查后继续")
        return 0
    else:
        print("\n✅ 所有验证通过，可以开始实验！")
        return 0

if __name__ == "__main__":
    sys.exit(main())

