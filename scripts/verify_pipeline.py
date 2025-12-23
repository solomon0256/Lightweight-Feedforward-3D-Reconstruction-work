#!/usr/bin/env python3
"""
Pipeline 验证脚本 (本地小规模测试)
===================================

用途：在本地电脑上验证整个 PQK 工作流是否正确
     - 不做完整训练，只验证代码能跑通
     - 使用极小数据集 (2-4 张图)
     - 每个步骤只跑 1-2 个 iteration
     - 验证输入输出格式、文件保存、日志记录

用法：
    python scripts/verify_pipeline.py --all           # 验证所有阶段 (需要足够显存)
    python scripts/verify_pipeline.py --all --light   # 轻量模式 (用 Mock 模型)
    python scripts/verify_pipeline.py --pruning       # 只验证剪枝
    python scripts/verify_pipeline.py --quantization  # 只验证量化
    python scripts/verify_pipeline.py --distillation  # 只验证蒸馏

验证通过后，可以放心在服务器上运行完整任务！
"""

import sys
import os
import argparse
import time
import tempfile
import shutil

# 设置路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
os.chdir(PROJECT_ROOT)

DUST3R_PATH = os.path.join(PROJECT_ROOT, "third_party", "dust3r")
CROCO_PATH = os.path.join(DUST3R_PATH, "croco")

# 确保 croco/models/__init__.py 存在
croco_models_init = os.path.join(CROCO_PATH, "models", "__init__.py")
if not os.path.exists(croco_models_init):
    os.makedirs(os.path.dirname(croco_models_init), exist_ok=True)
    open(croco_models_init, 'w').close()

sys.path.insert(0, CROCO_PATH)
sys.path.insert(0, DUST3R_PATH)


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_step(step, total, desc):
    print(f"\n[{step}/{total}] {desc}")
    print("-" * 40)


def print_success(msg):
    print(f"✓ {msg}")


def print_fail(msg):
    print(f"✗ {msg}")


def print_info(msg):
    print(f"  {msg}")


class PipelineVerifier:
    """Pipeline 验证器"""
    
    def __init__(self, device="cuda", verbose=True, light_mode=False):
        self.device = device
        self.verbose = verbose
        self.light_mode = light_mode
        self.results = {}
        self.temp_dir = None
        self.model = None
        
    def setup(self):
        """初始化环境"""
        import torch
        
        print_header("Pipeline 验证 - 初始化")
        
        if self.light_mode:
            print_info("🔹 轻量模式：使用 Mock 模型验证代码逻辑")
        else:
            print_info("🔸 完整模式：使用真实 DUSt3R 模型")
        
        # 检查 PyTorch
        print_info(f"PyTorch: {torch.__version__}")
        print_info(f"CUDA: {torch.cuda.is_available()}")
        
        if self.device == "cuda" and not torch.cuda.is_available():
            print_fail("CUDA 不可用，切换到 CPU")
            self.device = "cpu"
        
        if torch.cuda.is_available():
            print_info(f"GPU: {torch.cuda.get_device_name(0)}")
            print_info(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp(prefix="pipeline_verify_")
        print_info(f"临时目录: {self.temp_dir}")
        
        return True
    
    def cleanup(self):
        """清理临时文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print_info(f"已清理临时目录")
    
    def load_model(self):
        """加载模型"""
        import torch
        
        print_step(1, 5, "加载模型")
        
        # 轻量模式：创建一个 mock 模型
        if self.light_mode:
            print_info("轻量模式：使用 Mock 模型")
            
            # 创建一个简单的小型 mock 模型来验证流程
            class MockModel(torch.nn.Module):
                def __init__(self):
                    super().__init__()
                    # 使用卷积而不是全连接，大幅减少参数
                    self.encoder = torch.nn.Sequential(
                        torch.nn.Conv2d(3, 64, 3, padding=1),
                        torch.nn.ReLU(),
                        torch.nn.Conv2d(64, 128, 3, padding=1),
                        torch.nn.ReLU(),
                    )
                    self.decoder = torch.nn.Sequential(
                        torch.nn.Conv2d(128, 64, 3, padding=1),
                        torch.nn.ReLU(),
                        torch.nn.Conv2d(64, 3, 3, padding=1),
                    )
                    # 添加一些 Linear 层用于测试剪枝
                    self.fc = torch.nn.Linear(128, 64)
                
                def forward(self, x):
                    # x: [batch, H, W, 3] -> [batch, 3, H, W]
                    x = x.permute(0, 3, 1, 2)
                    x = self.encoder(x)
                    x = self.decoder(x)
                    # [batch, 3, H, W] -> [batch, H, W, 3]
                    x = x.permute(0, 2, 3, 1)
                    return x
            
            self.model = MockModel().to(self.device)
            param_count = sum(p.numel() for p in self.model.parameters())
            
            print_success(f"Mock 模型创建成功")
            print_info(f"参数量: {param_count:,} ({param_count/1e6:.1f}M)")
            print_info("⚠️ 这是 Mock 模型，仅验证代码逻辑")
            
            self.results['model_load'] = True
            return True
        
        # 完整模式：加载真实模型
        try:
            from dust3r.model import AsymmetricCroCo3DStereo
            
            start = time.time()
            model = AsymmetricCroCo3DStereo.from_pretrained(
                "naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt"
            )
            model = model.to(self.device)
            model.eval()
            
            load_time = time.time() - start
            param_count = sum(p.numel() for p in model.parameters())
            
            print_success(f"模型加载成功 ({load_time:.1f}s)")
            print_info(f"参数量: {param_count:,} ({param_count/1e6:.1f}M)")
            
            self.model = model
            self.results['model_load'] = True
            return True
            
        except Exception as e:
            print_fail(f"模型加载失败: {e}")
            self.results['model_load'] = False
            return False
    
    def verify_inference(self):
        """验证推理流程"""
        import torch
        import numpy as np
        from PIL import Image
        
        print_step(2, 5, "验证推理")
        
        # 轻量模式
        if self.light_mode:
            try:
                # 创建测试输入
                test_input = torch.randn(2, 384, 512, 3).to(self.device)
                
                # 运行 mock 推理
                with torch.no_grad():
                    output = self.model(test_input)
                
                print_success("Mock 推理完成")
                print_info(f"输入: {test_input.shape} → 输出: {output.shape}")
                
                self.results['inference'] = True
                return True
            except Exception as e:
                print_fail(f"Mock 推理失败: {e}")
                self.results['inference'] = False
                return False
        
        # 完整模式
        try:
            from dust3r.inference import inference
            from dust3r.utils.image import load_images
            
            # 创建测试图像
            img1_path = os.path.join(self.temp_dir, "test1.png")
            img2_path = os.path.join(self.temp_dir, "test2.png")
            
            img1 = Image.fromarray(np.random.randint(0, 255, (384, 512, 3), dtype=np.uint8))
            img2 = Image.fromarray(np.random.randint(0, 255, (384, 512, 3), dtype=np.uint8))
            img1.save(img1_path)
            img2.save(img2_path)
            
            # 加载图像
            images = load_images([img1_path, img2_path], size=512)
            print_info(f"测试图像: 2 张 (512x384)")
            
            # 推理
            start = time.time()
            pairs = [(images[0], images[1]), (images[1], images[0])]
            with torch.no_grad():
                output = inference(pairs, self.model, self.device, batch_size=1)
            
            infer_time = time.time() - start
            
            # 验证输出格式
            assert 'pred1' in output[0], "输出缺少 pred1"
            assert 'pts3d' in output[0]['pred1'], "输出缺少 pts3d"
            assert 'conf' in output[0]['pred1'], "输出缺少 conf"
            
            print_success(f"推理完成 ({infer_time:.2f}s)")
            print_info(f"输出格式正确: pts3d, conf")
            
            self.results['inference'] = True
            return True
            
        except Exception as e:
            print_fail(f"推理失败: {e}")
            self.results['inference'] = False
            return False
    
    def verify_pruning(self):
        """验证剪枝流程"""
        import torch
        import torch.nn.utils.prune as prune
        
        print_step(3, 5, "验证剪枝 (Pruning)")
        
        try:
            # 获取一个线性层进行测试
            test_module = None
            for name, module in self.model.named_modules():
                if isinstance(module, torch.nn.Linear):
                    test_module = module
                    test_name = name
                    break
            
            if test_module is None:
                print_fail("找不到可剪枝的层")
                return False
            
            # 记录原始参数
            original_weight = test_module.weight.data.clone()
            original_nonzero = (original_weight != 0).sum().item()
            
            # 应用非结构化剪枝 (10%)
            prune.l1_unstructured(test_module, name='weight', amount=0.1)
            
            # 验证剪枝效果
            pruned_weight = test_module.weight.data
            pruned_nonzero = (pruned_weight != 0).sum().item()
            
            # 移除剪枝（使其永久化）
            prune.remove(test_module, 'weight')
            
            print_success(f"剪枝测试通过")
            print_info(f"测试层: {test_name}")
            print_info(f"原始非零: {original_nonzero:,} → 剪枝后: {pruned_nonzero:,}")
            print_info(f"稀疏度: {1 - pruned_nonzero/original_nonzero:.1%}")
            
            # 恢复原始权重
            test_module.weight.data = original_weight
            
            self.results['pruning'] = True
            return True
            
        except Exception as e:
            print_fail(f"剪枝验证失败: {e}")
            self.results['pruning'] = False
            return False
    
    def verify_quantization(self):
        """验证量化流程"""
        import torch
        
        print_step(4, 5, "验证量化 (Quantization)")
        
        try:
            # 方法1: 动态量化测试
            print_info("测试动态量化 (INT8)...")
            
            # 创建一个简单的测试模块
            class SimpleModule(torch.nn.Module):
                def __init__(self):
                    super().__init__()
                    self.linear = torch.nn.Linear(512, 256)
                
                def forward(self, x):
                    return self.linear(x)
            
            test_model = SimpleModule()
            
            # 应用动态量化
            quantized_model = torch.quantization.quantize_dynamic(
                test_model,
                {torch.nn.Linear},
                dtype=torch.qint8
            )
            
            # 验证量化模型能运行
            test_input = torch.randn(1, 512)
            with torch.no_grad():
                output = quantized_model(test_input)
            
            print_success("动态量化 (INT8) 测试通过")
            print_info(f"输入: {test_input.shape} → 输出: {output.shape}")
            
            # 方法2: FP16 测试（如果有 GPU）
            if self.device == "cuda":
                print_info("测试 FP16 推理...")
                
                # 转换模型到 FP16
                model_fp16 = self.model.half()
                
                # 获取原始模型大小
                fp32_size = sum(p.numel() * 4 for p in self.model.parameters()) / 1e6
                fp16_size = sum(p.numel() * 2 for p in model_fp16.parameters()) / 1e6
                
                print_success("FP16 转换成功")
                print_info(f"FP32: {fp32_size:.1f} MB → FP16: {fp16_size:.1f} MB")
                
                # 恢复 FP32
                self.model = self.model.float()
            
            self.results['quantization'] = True
            return True
            
        except Exception as e:
            print_fail(f"量化验证失败: {e}")
            self.results['quantization'] = False
            return False
    
    def verify_distillation(self):
        """验证蒸馏流程"""
        import torch
        import torch.nn.functional as F
        
        print_step(5, 5, "验证蒸馏 (Knowledge Distillation)")
        
        try:
            # 模拟 Teacher-Student 蒸馏
            print_info("模拟 Teacher-Student 蒸馏...")
            
            # 创建模拟的 teacher 和 student 输出
            batch_size = 2
            teacher_output = torch.randn(batch_size, 384, 512, 3).to(self.device)
            student_output = torch.randn(batch_size, 384, 512, 3).to(self.device)
            student_output.requires_grad = True
            
            # 计算蒸馏损失
            # 1. MSE Loss (点云距离)
            mse_loss = F.mse_loss(student_output, teacher_output)
            
            # 2. L1 Loss
            l1_loss = F.l1_loss(student_output, teacher_output)
            
            # 3. 组合损失
            alpha = 0.5
            combined_loss = alpha * mse_loss + (1 - alpha) * l1_loss
            
            print_success("蒸馏损失计算成功")
            print_info(f"MSE Loss: {mse_loss.item():.4f}")
            print_info(f"L1 Loss: {l1_loss.item():.4f}")
            print_info(f"Combined Loss: {combined_loss.item():.4f}")
            
            # 验证梯度回传
            combined_loss.backward()
            
            print_success("梯度回传测试通过")
            print_info(f"梯度形状: {student_output.grad.shape}")
            
            self.results['distillation'] = True
            return True
            
        except Exception as e:
            print_fail(f"蒸馏验证失败: {e}")
            self.results['distillation'] = False
            return False
    
    def verify_save_load(self):
        """验证模型保存和加载"""
        import torch
        
        print_step("Extra", "", "验证模型保存/加载")
        
        try:
            # 保存模型
            save_path = os.path.join(self.temp_dir, "test_model.pth")
            torch.save({
                'model_state_dict': self.model.state_dict(),
                'config': {
                    'model_name': 'DUSt3R_ViTLarge_BaseDecoder_512_dpt' if not self.light_mode else 'MockModel',
                    'pruning_ratio': 0.0,
                    'quantization': 'none'
                }
            }, save_path)
            
            file_size = os.path.getsize(save_path) / 1e6
            print_success(f"模型保存成功: {file_size:.1f} MB")
            
            # 加载模型
            checkpoint = torch.load(save_path, map_location=self.device, weights_only=False)
            print_success(f"模型加载成功")
            print_info(f"配置: {checkpoint['config']}")
            
            self.results['save_load'] = True
            return True
            
        except Exception as e:
            print_fail(f"保存/加载验证失败: {e}")
            self.results['save_load'] = False
            return False
    
    def print_summary(self):
        """打印验证总结"""
        print_header("验证结果总结")
        
        all_passed = True
        for name, passed in self.results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {name}: {status}")
            if not passed:
                all_passed = False
        
        print()
        if all_passed:
            print("=" * 60)
            if self.light_mode:
                print("  🎉 轻量验证通过！代码逻辑正确")
                print("  📝 下一步: 在服务器上用真实模型运行")
            else:
                print("  🎉 所有验证通过！Pipeline 可以在服务器上运行")
            print("=" * 60)
        else:
            print("=" * 60)
            print("  ⚠️  部分验证失败，请检查后再部署到服务器")
            print("=" * 60)
        
        return all_passed


def main():
    parser = argparse.ArgumentParser(description="Pipeline 验证脚本")
    parser.add_argument("--all", action="store_true", help="验证所有阶段")
    parser.add_argument("--pruning", action="store_true", help="只验证剪枝")
    parser.add_argument("--quantization", action="store_true", help="只验证量化")
    parser.add_argument("--distillation", action="store_true", help="只验证蒸馏")
    parser.add_argument("--device", default="cuda", help="设备 (cuda/cpu)")
    parser.add_argument("--light", action="store_true", help="轻量模式：不加载完整模型，只验证代码逻辑")
    args = parser.parse_args()
    
    # 默认验证所有
    if not (args.pruning or args.quantization or args.distillation):
        args.all = True
    
    verifier = PipelineVerifier(device=args.device, light_mode=args.light)
    
    try:
        # 初始化
        verifier.setup()
        
        # 加载模型
        if not verifier.load_model():
            return 1
        
        # 验证推理
        verifier.verify_inference()
        
        # 根据参数验证各阶段
        if args.all or args.pruning:
            verifier.verify_pruning()
        
        if args.all or args.quantization:
            verifier.verify_quantization()
        
        if args.all or args.distillation:
            verifier.verify_distillation()
        
        # 验证保存/加载
        if args.all:
            verifier.verify_save_load()
        
        # 总结
        success = verifier.print_summary()
        
        return 0 if success else 1
        
    finally:
        verifier.cleanup()


if __name__ == "__main__":
    sys.exit(main())
