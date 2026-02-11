#!/usr/bin/env python3
"""
SelimCam Performance Benchmark
===============================

Comprehensive performance testing and system recommendations.

Measures:
- Frame capture and rendering latency
- Filter performance (live vs post)
- Encoder response time
- Memory usage patterns
- CPU utilization
- I/O throughput

Outputs:
- Performance report
- System recommendations
- Bottleneck identification

Usage:
    python3 scripts/benchmark.py [--quick] [--full] [--report]

Author: SelimCam Team
License: MIT
"""

import time
import sys
import os
import argparse
import psutil
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import json

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ipc import SharedFrameBuffer
from filters.filters import FilterManager
from hardware.rotary_encoder import RotaryEncoder


class PerformanceBenchmark:
    """
    Comprehensive performance benchmark suite
    """
    
    def __init__(self):
        self.results = {}
        self.system_info = self._gather_system_info()
    
    def _gather_system_info(self) -> Dict:
        """Gather system information"""
        info = {
            'cpu_count': psutil.cpu_count(),
            'cpu_freq': psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            'memory_total_mb': psutil.virtual_memory().total / (1024**2),
            'platform': sys.platform,
            'python_version': sys.version,
        }
        
        # Try to get Raspberry Pi model
        try:
            with open('/proc/device-tree/model', 'r') as f:
                info['pi_model'] = f.read().strip('\x00')
        except:
            info['pi_model'] = 'Unknown'
        
        return info
    
    def benchmark_frame_buffer(self, iterations: int = 1000) -> Dict:
        """
        Benchmark frame buffer performance
        
        Measures:
        - Write latency
        - Read latency
        - Throughput
        """
        print("\n[1/6] Benchmarking Frame Buffer...")
        
        buffer = SharedFrameBuffer(640, 480, name="benchmark_buffer")
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Write benchmark
        write_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            buffer.write_frame(frame)
            write_times.append(time.perf_counter() - start)
        
        # Read benchmark
        read_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            _ = buffer.read_frame()
            read_times.append(time.perf_counter() - start)
        
        buffer.cleanup()
        
        results = {
            'write_avg_ms': np.mean(write_times) * 1000,
            'write_min_ms': np.min(write_times) * 1000,
            'write_max_ms': np.max(write_times) * 1000,
            'write_std_ms': np.std(write_times) * 1000,
            'read_avg_ms': np.mean(read_times) * 1000,
            'read_min_ms': np.min(read_times) * 1000,
            'read_max_ms': np.max(read_times) * 1000,
            'throughput_fps': 1.0 / np.mean(write_times),
        }
        
        print(f"  Write: {results['write_avg_ms']:.2f}ms (± {results['write_std_ms']:.2f}ms)")
        print(f"  Read:  {results['read_avg_ms']:.2f}ms")
        print(f"  Max throughput: {results['throughput_fps']:.1f} FPS")
        
        return results
    
    def benchmark_filters(self, iterations: int = 100) -> Dict:
        """
        Benchmark filter performance at preview and full resolution
        """
        print("\n[2/6] Benchmarking Filters...")
        
        manager = FilterManager()
        
        # Preview resolution (640x480)
        preview_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Full resolution (8MP - 3280x2464)
        full_image = np.random.randint(0, 255, (2464, 3280, 3), dtype=np.uint8)
        
        results = {}
        
        for filter_name in ['vintage', 'bw', 'vivid']:
            # Preview resolution
            preview_times = []
            for _ in range(iterations):
                start = time.perf_counter()
                _ = manager.apply_filter(preview_image, filter_name)
                preview_times.append(time.perf_counter() - start)
            
            # Full resolution (fewer iterations)
            full_times = []
            for _ in range(max(10, iterations // 10)):
                start = time.perf_counter()
                _ = manager.apply_filter(full_image, filter_name)
                full_times.append(time.perf_counter() - start)
            
            results[filter_name] = {
                'preview_avg_ms': np.mean(preview_times) * 1000,
                'preview_std_ms': np.std(preview_times) * 1000,
                'full_avg_ms': np.mean(full_times) * 1000,
                'full_std_ms': np.std(full_times) * 1000,
            }
            
            print(f"  {filter_name:12s}: "
                  f"Preview {results[filter_name]['preview_avg_ms']:.2f}ms, "
                  f"Full {results[filter_name]['full_avg_ms']:.0f}ms")
        
        return results
    
    def benchmark_encoder(self, iterations: int = 1000) -> Dict:
        """
        Benchmark encoder polling latency
        """
        print("\n[3/6] Benchmarking Encoder...")
        
        encoder = RotaryEncoder(pin_a=5, pin_b=6, pin_button=13)
        
        poll_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            encoder.poll()
            poll_times.append(time.perf_counter() - start)
        
        encoder.cleanup()
        
        results = {
            'poll_avg_us': np.mean(poll_times) * 1000000,
            'poll_max_us': np.max(poll_times) * 1000000,
            'poll_std_us': np.std(poll_times) * 1000000,
        }
        
        print(f"  Poll latency: {results['poll_avg_us']:.1f}µs "
              f"(max: {results['poll_max_us']:.1f}µs)")
        
        return results
    
    def benchmark_memory(self) -> Dict:
        """
        Measure memory usage patterns
        """
        print("\n[4/6] Analyzing Memory Usage...")
        
        import gc
        gc.collect()
        
        mem_start = psutil.Process().memory_info().rss / (1024**2)
        
        # Simulate typical workload
        buffer = SharedFrameBuffer(640, 480, name="mem_test")
        manager = FilterManager()
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Allocate some resources
        for _ in range(100):
            buffer.write_frame(frame)
            _ = manager.apply_filter(frame, 'vintage')
        
        mem_working = psutil.Process().memory_info().rss / (1024**2)
        
        buffer.cleanup()
        gc.collect()
        
        mem_end = psutil.Process().memory_info().rss / (1024**2)
        
        results = {
            'baseline_mb': mem_start,
            'working_set_mb': mem_working - mem_start,
            'peak_mb': mem_working,
            'leaked_mb': mem_end - mem_start,
        }
        
        print(f"  Baseline: {results['baseline_mb']:.1f} MB")
        print(f"  Working set: {results['working_set_mb']:.1f} MB")
        print(f"  Peak: {results['peak_mb']:.1f} MB")
        
        if results['leaked_mb'] > 1.0:
            print(f"  ⚠️  Possible leak: {results['leaked_mb']:.1f} MB")
        
        return results
    
    def benchmark_cpu(self, duration: int = 5) -> Dict:
        """
        Measure CPU utilization under load
        """
        print(f"\n[5/6] Measuring CPU Utilization ({duration}s)...")
        
        # Start workload
        import threading
        
        stop_event = threading.Event()
        
        def workload():
            buffer = SharedFrameBuffer(640, 480, name="cpu_test")
            manager = FilterManager()
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            
            while not stop_event.is_set():
                buffer.write_frame(frame)
                _ = manager.apply_filter(frame, 'vintage')
            
            buffer.cleanup()
        
        # Start worker threads
        threads = []
        for _ in range(2):  # Simulate camera + UI processes
            t = threading.Thread(target=workload, daemon=True)
            t.start()
            threads.append(t)
        
        # Measure CPU
        cpu_samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            cpu_samples.append(psutil.cpu_percent(interval=0.1))
        
        # Stop workers
        stop_event.set()
        for t in threads:
            t.join(timeout=1.0)
        
        results = {
            'avg_percent': np.mean(cpu_samples),
            'max_percent': np.max(cpu_samples),
            'std_percent': np.std(cpu_samples),
        }
        
        print(f"  Average: {results['avg_percent']:.1f}%")
        print(f"  Peak: {results['max_percent']:.1f}%")
        
        return results
    
    def benchmark_end_to_end(self, duration: int = 10) -> Dict:
        """
        End-to-end latency test
        
        Simulates: Encoder input → Haptic feedback → Frame update → Render
        """
        print(f"\n[6/6] End-to-End Latency Test ({duration}s)...")
        
        encoder = RotaryEncoder(pin_a=5, pin_b=6, pin_button=13)
        buffer = SharedFrameBuffer(640, 480, name="e2e_test")
        manager = FilterManager()
        
        latencies = []
        
        start_time = time.time()
        while time.time() - start_time < duration:
            # Simulate input event
            event_start = time.perf_counter()
            
            # 1. Poll encoder
            encoder.poll()
            
            # 2. Process event (simulate zoom change)
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            
            # 3. Apply filter
            filtered = manager.apply_filter(frame, 'vintage')
            
            # 4. Update buffer
            buffer.write_frame(filtered)
            
            # 5. Read for display
            _ = buffer.read_frame()
            
            event_end = time.perf_counter()
            
            latencies.append((event_end - event_start) * 1000)
            
            time.sleep(0.016)  # 60Hz polling
        
        encoder.cleanup()
        buffer.cleanup()
        
        results = {
            'avg_ms': np.mean(latencies),
            'p50_ms': np.percentile(latencies, 50),
            'p95_ms': np.percentile(latencies, 95),
            'p99_ms': np.percentile(latencies, 99),
            'max_ms': np.max(latencies),
        }
        
        print(f"  Average: {results['avg_ms']:.2f}ms")
        print(f"  P95: {results['p95_ms']:.2f}ms")
        print(f"  P99: {results['p99_ms']:.2f}ms")
        
        return results
    
    def generate_recommendations(self) -> List[str]:
        """
        Generate performance recommendations based on results
        """
        recommendations = []
        
        # Check frame buffer performance
        if self.results.get('frame_buffer', {}).get('write_avg_ms', 0) > 5.0:
            recommendations.append(
                "⚠️  Frame buffer writes are slow (>5ms). "
                "Consider reducing preview resolution or using faster storage."
            )
        
        # Check filter performance
        filters = self.results.get('filters', {})
        for filter_name, metrics in filters.items():
            if metrics.get('preview_avg_ms', 0) > 5.0:
                recommendations.append(
                    f"⚠️  Filter '{filter_name}' is too slow for live preview ({metrics['preview_avg_ms']:.1f}ms). "
                    f"Reduce preview resolution or optimize filter."
                )
        
        # Check encoder latency
        if self.results.get('encoder', {}).get('poll_avg_us', 0) > 100:
            recommendations.append(
                "⚠️  Encoder poll latency is high. Check for CPU contention."
            )
        
        # Check memory
        mem = self.results.get('memory', {})
        if mem.get('peak_mb', 0) > 400:
            recommendations.append(
                f"⚠️  High memory usage ({mem['peak_mb']:.0f} MB). "
                f"Consider enabling swap or reducing buffer count."
            )
        
        if mem.get('leaked_mb', 0) > 5.0:
            recommendations.append(
                f"⚠️  Potential memory leak detected ({mem['leaked_mb']:.1f} MB). "
                f"Run extended test to confirm."
            )
        
        # Check CPU
        cpu = self.results.get('cpu', {})
        if cpu.get('avg_percent', 0) > 80:
            recommendations.append(
                f"⚠️  High CPU usage ({cpu['avg_percent']:.0f}%). "
                f"Consider reducing preview FPS or disabling live filters."
            )
        
        # Check end-to-end latency
        e2e = self.results.get('end_to_end', {})
        if e2e.get('p95_ms', 0) > 25:
            recommendations.append(
                f"⚠️  High end-to-end latency (P95: {e2e['p95_ms']:.1f}ms). "
                f"Target is <25ms for responsive feel."
            )
        
        if not recommendations:
            recommendations.append("✅ All performance metrics within targets!")
        
        return recommendations
    
    def run_all(self, quick: bool = False):
        """Run all benchmarks"""
        print("="*60)
        print("SELIMCAM PERFORMANCE BENCHMARK")
        print("="*60)
        print(f"\nSystem: {self.system_info.get('pi_model', 'Unknown')}")
        print(f"CPU: {self.system_info['cpu_count']} cores @ {self.system_info.get('cpu_freq', 0):.0f} MHz")
        print(f"RAM: {self.system_info['memory_total_mb']:.0f} MB")
        
        iterations = 100 if quick else 1000
        duration = 3 if quick else 10
        
        self.results['frame_buffer'] = self.benchmark_frame_buffer(iterations)
        self.results['filters'] = self.benchmark_filters(iterations // 10 if quick else iterations)
        self.results['encoder'] = self.benchmark_encoder(iterations)
        self.results['memory'] = self.benchmark_memory()
        self.results['cpu'] = self.benchmark_cpu(duration)
        self.results['end_to_end'] = self.benchmark_end_to_end(duration)
        
        print("\n" + "="*60)
        print("RECOMMENDATIONS")
        print("="*60)
        
        for rec in self.generate_recommendations():
            print(f"\n{rec}")
        
        print("\n" + "="*60)
    
    def save_report(self, filepath: Path):
        """Save detailed report to JSON"""
        report = {
            'timestamp': time.time(),
            'system_info': self.system_info,
            'results': self.results,
            'recommendations': self.generate_recommendations(),
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nReport saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description='SelimCam Performance Benchmark')
    parser.add_argument('--quick', action='store_true', help='Run quick benchmark (fewer iterations)')
    parser.add_argument('--full', action='store_true', help='Run full benchmark (default)')
    parser.add_argument('--report', type=str, help='Save report to file (JSON)')
    
    args = parser.parse_args()
    
    benchmark = PerformanceBenchmark()
    benchmark.run_all(quick=args.quick)
    
    if args.report:
        benchmark.save_report(Path(args.report))


if __name__ == "__main__":
    main()
