"""
时延统计器 - 计算 p50/p95 时延、吞吐量等效率指标
"""
import time
import numpy as np
from typing import List, Optional, Callable, Any
from dataclasses import dataclass
from contextlib import contextmanager
import torch


@dataclass
class TimingResult:
    """时延统计结果"""
    p50_ms: float      # 50 分位数（中位数）
    p95_ms: float      # 95 分位数
    mean_ms: float     # 平均值
    std_ms: float      # 标准差
    min_ms: float      # 最小值
    max_ms: float      # 最大值
    total_s: float     # 总时间（秒）
    count: int         # 样本数
    throughput: float  # 吞吐量（次/秒）
    
    def __str__(self) -> str:
        return (
            f"Timing: p50={self.p50_ms:.2f}ms, p95={self.p95_ms:.2f}ms, "
            f"mean={self.mean_ms:.2f}±{self.std_ms:.2f}ms, "
            f"throughput={self.throughput:.2f}/s"
        )


class Timer:
    """
    高精度计时器
    
    用法1 - 上下文管理器:
        timer = Timer()
        with timer.measure():
            # 执行操作
        print(timer.get_result())
    
    用法2 - 手动计时:
        timer = Timer()
        timer.start()
        # 执行操作
        timer.stop()
    
    用法3 - 装饰器:
        @Timer.timeit
        def my_function():
            pass
    """
    
    def __init__(self, warmup: int = 3, sync_cuda: bool = True):
        """
        Args:
            warmup: 预热次数（不计入统计）
            sync_cuda: 是否同步 CUDA（确保 GPU 计算完成）
        """
        self.warmup = warmup
        self.sync_cuda = sync_cuda
        self.times: List[float] = []
        self._start_time: Optional[float] = None
        self._warmup_count = 0
    
    def reset(self):
        """重置计时器"""
        self.times = []
        self._start_time = None
        self._warmup_count = 0
    
    def _sync(self):
        """同步 CUDA"""
        if self.sync_cuda and torch.cuda.is_available():
            torch.cuda.synchronize()
    
    def start(self):
        """开始计时"""
        self._sync()
        self._start_time = time.perf_counter()
    
    def stop(self) -> float:
        """
        停止计时
        
        Returns:
            本次计时时长（毫秒）
        """
        self._sync()
        if self._start_time is None:
            raise RuntimeError("Timer not started")
        
        elapsed = (time.perf_counter() - self._start_time) * 1000  # ms
        self._start_time = None
        
        # 预热阶段不记录
        if self._warmup_count < self.warmup:
            self._warmup_count += 1
        else:
            self.times.append(elapsed)
        
        return elapsed
    
    @contextmanager
    def measure(self):
        """上下文管理器方式计时"""
        self.start()
        try:
            yield
        finally:
            self.stop()
    
    def get_result(self) -> TimingResult:
        """获取统计结果"""
        if not self.times:
            return TimingResult(
                p50_ms=0, p95_ms=0, mean_ms=0, std_ms=0,
                min_ms=0, max_ms=0, total_s=0, count=0, throughput=0
            )
        
        times = np.array(self.times)
        total_s = times.sum() / 1000
        
        return TimingResult(
            p50_ms=float(np.percentile(times, 50)),
            p95_ms=float(np.percentile(times, 95)),
            mean_ms=float(np.mean(times)),
            std_ms=float(np.std(times)),
            min_ms=float(np.min(times)),
            max_ms=float(np.max(times)),
            total_s=total_s,
            count=len(times),
            throughput=len(times) / total_s if total_s > 0 else 0,
        )
    
    @staticmethod
    def timeit(func: Callable) -> Callable:
        """装饰器方式计时"""
        def wrapper(*args, **kwargs):
            timer = Timer(warmup=0, sync_cuda=True)
            timer.start()
            result = func(*args, **kwargs)
            elapsed = timer.stop()
            print(f"{func.__name__}: {elapsed:.2f}ms")
            return result
        return wrapper


class BatchTimer:
    """
    批量计时器 - 用于评测多个样本
    
    用法:
        timer = BatchTimer(warmup=3)
        for batch in dataloader:
            with timer.measure():
                model(batch)
        result = timer.get_result()
    """
    
    def __init__(self, warmup: int = 3, sync_cuda: bool = True):
        self.timer = Timer(warmup=warmup, sync_cuda=sync_cuda)
    
    def reset(self):
        self.timer.reset()
    
    @contextmanager
    def measure(self):
        with self.timer.measure():
            yield
    
    def get_result(self) -> TimingResult:
        return self.timer.get_result()
    
    def benchmark(
        self,
        func: Callable,
        inputs: List[Any],
        warmup: Optional[int] = None
    ) -> TimingResult:
        """
        对函数进行基准测试
        
        Args:
            func: 要测试的函数
            inputs: 输入列表
            warmup: 覆盖预热次数
        """
        if warmup is not None:
            self.timer.warmup = warmup
        
        self.reset()
        
        for inp in inputs:
            with self.measure():
                func(inp)
        
        return self.get_result()


def measure_inference_time(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    num_runs: int = 100,
    warmup: int = 10,
) -> TimingResult:
    """
    测量模型推理时间
    
    Args:
        model: PyTorch 模型
        input_tensor: 输入张量
        num_runs: 运行次数
        warmup: 预热次数
    
    Returns:
        TimingResult
    """
    model.eval()
    timer = Timer(warmup=warmup, sync_cuda=True)
    
    with torch.no_grad():
        # 预热 + 正式测量
        for _ in range(warmup + num_runs):
            with timer.measure():
                _ = model(input_tensor)
    
    return timer.get_result()


def estimate_scene_time(
    t_pair_ms: float,
    num_pairs: int,
    overhead_ratio: float = 1.1
) -> float:
    """
    估算场景总耗时
    
    Args:
        t_pair_ms: 单 pair 时延（毫秒）
        num_pairs: pair 数量
        overhead_ratio: 开销系数（数据加载、后处理等）
    
    Returns:
        场景耗时（秒）
    """
    return (t_pair_ms * num_pairs * overhead_ratio) / 1000


# ============ 测试 ============

if __name__ == '__main__':
    # 测试计时器
    timer = Timer(warmup=2, sync_cuda=False)
    
    for i in range(10):
        with timer.measure():
            time.sleep(0.01)  # 模拟 10ms 操作
    
    result = timer.get_result()
    print(result)
    
    # 测试场景时间估算
    scene_time = estimate_scene_time(t_pair_ms=50, num_pairs=200)
    print(f"Estimated scene time: {scene_time:.2f}s")
