#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CodeAgent 沙箱执行环境
路径：./scripts/codeagent_sandbox.py
"""

import os
import sys
import json
import resource
import signal
import subprocess
import time
import shutil
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field

try:
    from RestrictedPython import safe_builtins
    from RestrictedPython import compile_restricted
    from RestrictedPython import limited_builtins
    RESTRICTED_PYTHON_AVAILABLE = True
except ImportError:
    RESTRICTED_PYTHON_AVAILABLE = False


@dataclass
class SandboxConfig:
    cpu_time_limit: int = 60
    wall_time_limit: int = 120
    memory_limit_mb: int = 512
    file_size_limit_mb: int = 10
    total_size_limit_mb: int = 50
    allow_network: bool = False
    network_whitelist: List[str] = field(default_factory=lambda: [
        'pypi.org', 'files.pythonhosted.org', 'cdn.jsdelivr.net',
        'github.com', 'raw.githubusercontent.com', 'registry.npmjs.org', 'unpkg.com'
    ])
    workspace_root: str = "./codeagent_workspace"
    allow_write: bool = True
    allow_read: bool = True
    allow_delete: bool = False
    timeout_signal: int = signal.SIGTERM
    encoding: str = 'utf-8'
    max_files: int = 50
    max_subprocesses: int = 5
    use_restricted_python: bool = True


class ResourceLimiter:
    def __init__(self, config: SandboxConfig):
        self.config = config
    
    def apply_limits(self):
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (self.config.cpu_time_limit, self.config.cpu_time_limit + 1))
            mem = self.config.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            resource.setrlimit(resource.RLIMIT_DATA, (mem, mem))
            resource.setrlimit(resource.RLIMIT_STACK, (mem // 4, mem // 4))
            file_limit = self.config.file_size_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
            resource.setrlimit(resource.RLIMIT_NPROC, (self.config.max_subprocesses, self.config.max_subprocesses))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        except Exception:
            pass


class TimeoutManager:
    def __init__(self, timeout_seconds: int):
        self.timeout = timeout_seconds
        self._timed_out = False
        self._old_handler = None
    
    def __enter__(self):
        def _handler(signum, frame):
            self._timed_out = True
            raise TimeoutError(f"执行超时（{self.timeout}秒）")
        self._old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(self.timeout)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.alarm(0)
        if self._old_handler:
            signal.signal(signal.SIGALRM, self._old_handler)
        return False


class RestrictedPythonExecutor:
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._setup_safe_env()
    
    def _setup_safe_env(self):
        self.safe_builtins = safe_builtins.copy() if RESTRICTED_PYTHON_AVAILABLE else {}
        
        safe_modules = {
            'sys': sys,
            'os': os,
            're': re,
            'json': json,
            'time': time,
            'datetime': __import__('datetime'),
            'math': __import__('math'),
            'random': __import__('random'),
            'collections': __import__('collections'),
            'itertools': __import__('itertools'),
            'functools': __import__('functools'),
            'typing': __import__('typing'),
            'pathlib': Path,
        }
        
        for name, module in safe_modules.items():
            self.safe_builtins[name] = module
        
        self.safe_builtins['__import__'] = self._safe_import
        self.safe_builtins['open'] = self._safe_open
        self.safe_builtins['print'] = self._safe_print
    
    def _safe_import(self, name: str, *args, **kwargs):
        safe_modules = {
            'sys': sys, 'os': os, 're': re, 'json': json, 'time': time,
            'datetime': __import__('datetime'), 'math': __import__('math'),
            'random': __import__('random'), 'collections': __import__('collections'),
            'itertools': __import__('itertools'), 'functools': __import__('functools'),
            'typing': __import__('typing'), 'pathlib': Path,
        }
        if name in safe_modules:
            return safe_modules[name]
        if name in ['pytest', 'unittest', 'doctest']:
            raise ImportError(f"测试模块 {name} 不允许在沙箱中导入")
        raise ImportError(f"模块 {name} 不允许在沙箱中导入")
    
    def _safe_open(self, path: str, mode: str = 'r', *args, **kwargs):
        if not self.config.allow_write and 'w' in mode:
            raise PermissionError(f"写入被禁止: {path}")
        if not self.config.allow_read and 'r' in mode:
            raise PermissionError(f"读取被禁止: {path}")
        if self.config.allow_delete and any(k in path for k in ['rm', 'del', 'remove']):
            raise PermissionError(f"删除被禁止: {path}")
        if path.startswith('/etc/') or path.startswith('/root/') or path.startswith('/sys/') or path.startswith('/proc/'):
            raise PermissionError(f"系统路径访问被禁止: {path}")
        return open(path, mode, *args, **kwargs)
    
    def _safe_print(self, *args, **kwargs):
        output = ' '.join(str(arg) for arg in args)
        sys.stdout.write(output + '\n')
        sys.stdout.flush()
    
    def execute_code(self, code: str, session_dir: Path, filename: str = 'main.py') -> Tuple[str, str, int]:
        if not RESTRICTED_PYTHON_AVAILABLE:
            return "", "RestrictedPython 未安装，请运行: pip install RestrictedPython", -1
        
        try:
            compiled_code = compile_restricted(code, filename, 'exec')
        except SyntaxError as e:
            return "", f"语法错误: {e}", -1
        except Exception as e:
            return "", f"编译错误: {e}", -1
        
        old_cwd = os.getcwd()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin
        
        stdout_capture = []
        stderr_capture = []
        
        class CaptureIO:
            def __init__(self, capture_list):
                self.capture_list = capture_list
            
            def write(self, text):
                self.capture_list.append(text)
            
            def flush(self):
                pass
        
        sys.stdout = CaptureIO(stdout_capture)
        sys.stderr = CaptureIO(stderr_capture)
        sys.stdin = open(os.devnull, 'r')
        
        try:
            os.chdir(str(session_dir))
            
            safe_globals = {
                '__builtins__': self.safe_builtins,
                '__name__': '__main__',
                '__file__': filename,
                'Path': Path,
                'sys': sys,
                'os': os,
                're': re,
                'json': json,
                'time': time,
                'math': __import__('math'),
                'random': __import__('random'),
            }
            
            exec(compiled_code, safe_globals)
            exit_code = 0
            
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 0
        except Exception as e:
            stderr_capture.append(f"{type(e).__name__}: {e}\n")
            exit_code = 1
        finally:
            os.chdir(old_cwd)
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
        
        return ''.join(stdout_capture), ''.join(stderr_capture), exit_code


class StandardExecutor:
    
    def __init__(self, config: SandboxConfig):
        self.config = config
    
    def execute_code(self, code: str, session_dir: Path, language: str, filename: str, args: list = None) -> Tuple[str, str, int, float]:
        file_path = session_dir / filename
        
        if language == 'python':
            cmd = ['python3', '-u', str(file_path)] + (args or [])
        elif language == 'javascript':
            cmd = ['node', str(file_path)] + (args or [])
        elif language == 'bash':
            os.chmod(file_path, 0o755)
            cmd = ['bash', str(file_path)] + (args or [])
        else:
            return "", f"不支持的语言: {language}", -1, 0
        
        start_time = time.time()
        
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(session_dir),
                env=self._build_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=self.config.encoding,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            try:
                stdout, stderr = proc.communicate(timeout=self.config.wall_time_limit)
                stdout = stdout[:100000] if len(stdout) > 100000 else stdout
                stderr = stderr[:50000] if len(stderr) > 50000 else stderr
                if len(stdout) > 100000:
                    stdout += f"\n... (输出截断，共 {len(stdout)} 字符)"
                return stdout, stderr, proc.returncode, time.time() - start_time
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except:
                    proc.kill()
                proc.wait(timeout=2)
                return "", f"执行超时（{self.config.wall_time_limit}秒）", -1, time.time() - start_time
                
        except Exception as e:
            return "", f"执行异常: {e}", -1, time.time() - start_time
    
    def _build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env['TMPDIR'] = str(self.config.workspace_root / 'tmp')
        env['TEMP'] = env['TMPDIR']
        env['TMP'] = env['TMPDIR']
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['PYTHONHASHSEED'] = 'random'
        env['PYTHONNOUSERSITE'] = '1'
        if not self.config.allow_network:
            env['http_proxy'] = ''
            env['https_proxy'] = ''
            env['no_proxy'] = '*'
        env['PATH'] = '/usr/local/bin:/usr/bin:/bin'
        return env


class SandboxExecutor:
    
    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self.workspace = Path(self.config.workspace_root).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        self.restricted_executor = RestrictedPythonExecutor(self.config) if self.config.use_restricted_python else None
        self.standard_executor = StandardExecutor(self.config)
    
    def _get_session_workspace(self, session_id: str) -> Path:
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)
        session_dir = self.workspace / safe_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def execute(self, code: str, session_id: str, language: str = 'python',
                filename: str = 'main.py', args: list = None) -> Dict[str, Any]:
        result = {
            'success': False, 'stdout': '', 'stderr': '', 'exit_code': -1,
            'time_elapsed': 0, 'files': [], 'error': None, 'security_warning': None,
            'execution_method': 'standard'
        }
        
        session_dir = self._get_session_workspace(session_id)
        file_path = session_dir / filename
        
        try:
            file_path.write_text(code, encoding=self.config.encoding)
        except Exception as e:
            result['error'] = f"写入文件失败: {e}"
            return result
        
        limiter = ResourceLimiter(self.config)
        limiter.apply_limits()
        
        stdout = ''
        stderr = ''
        exit_code = -1
        time_elapsed = 0
        
        try:
            with TimeoutManager(self.config.wall_time_limit):
                if language == 'python' and self.config.use_restricted_python and RESTRICTED_PYTHON_AVAILABLE:
                    stdout, stderr, exit_code = self.restricted_executor.execute_code(code, session_dir, filename)
                    result['execution_method'] = 'restricted_python'
                else:
                    if language != 'python' or not RESTRICTED_PYTHON_AVAILABLE:
                        stdout, stderr, exit_code, time_elapsed = self.standard_executor.execute_code(
                            code, session_dir, language, filename, args
                        )
                    else:
                        stdout, stderr, exit_code, time_elapsed = self.standard_executor.execute_code(
                            code, session_dir, 'python', filename, args
                        )
                
                result['stdout'] = stdout[:100000] if len(stdout) > 100000 else stdout
                result['stderr'] = stderr[:50000] if len(stderr) > 50000 else stderr
                if len(stdout) > 100000:
                    result['stdout'] += f"\n... (输出截断，共 {len(stdout)} 字符)"
                result['exit_code'] = exit_code
                result['time_elapsed'] = time_elapsed or 0
                
        except TimeoutError as e:
            result['error'] = str(e)
            return result
        except Exception as e:
            result['error'] = f"执行异常: {e}"
            return result
        
        try:
            result['files'] = []
            total_size = 0
            for item in session_dir.iterdir():
                if item.is_file() and item.name != filename and not item.name.startswith('.'):
                    size = item.stat().st_size
                    if size > self.config.file_size_limit_mb * 1024 * 1024:
                        continue
                    total_size += size
                    result['files'].append({
                        'name': item.name,
                        'size': size,
                        'path': str(item.relative_to(self.workspace))
                    })
                    if len(result['files']) > self.config.max_files:
                        break
            if total_size > self.config.total_size_limit_mb * 1024 * 1024:
                result['warning'] = f"项目总大小超出限制 ({total_size} bytes)"
        except Exception as e:
            result['warning'] = f"文件收集失败: {e}"
        
        result['success'] = (result['exit_code'] == 0 and result['error'] is None)
        
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='CodeAgent 沙箱执行环境')
    parser.add_argument('--code', type=str, help='代码内容')
    parser.add_argument('--code-file', type=str, help='代码文件路径')
    parser.add_argument('--session-id', type=str, default='test', help='会话ID')
    parser.add_argument('--language', type=str, default='python', help='编程语言')
    parser.add_argument('--filename', type=str, default='main.py', help='文件名')
    parser.add_argument('--args', type=str, nargs='*', help='命令行参数')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--test', action='store_true', help='运行测试')
    
    args = parser.parse_args()
    
    if args.test:
        print("运行沙箱测试...")
        config = SandboxConfig()
        executor = SandboxExecutor(config)
        
        test_code = '''
import os
import sys
print("Hello from sandbox!")
print(f"当前目录: {os.getcwd()}")
with open("test_output.txt", "w") as f:
    f.write("Test file created\\n")
print("测试完成")
print(f"Python版本: {sys.version}")
'''
        result = executor.execute(
            code=test_code,
            session_id='test_session',
            language='python',
            filename='test.py'
        )
        
        print(f"成功: {result['success']}")
        print(f"stdout:\n{result['stdout']}")
        if result['files']:
            print(f"生成的文件: {[f['name'] for f in result['files']]}")
        if result['error']:
            print(f"错误: {result['error']}")
        print("测试完成")
        return
    
    if args.code:
        code = args.code
    elif args.code_file:
        with open(args.code_file, 'r', encoding='utf-8') as f:
            code = f.read()
    else:
        print("错误: 请提供 --code 或 --code-file", file=sys.stderr)
        sys.exit(1)
    
    config = SandboxConfig()
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            for key, value in config_data.items():
                if hasattr(config, key):
                    setattr(config, key, value)
    
    executor = SandboxExecutor(config)
    result = executor.execute(
        code=code,
        session_id=args.session_id,
        language=args.language,
        filename=args.filename,
        args=args.args
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
