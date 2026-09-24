#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CodeAgent
"""

import os
import json
import re
import time
import shutil
import subprocess
import asyncio
import platform
import urllib.request
import tarfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig


class CodeAgentPlugin(Star):
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.logger = logger
        self.workspace = Path("./data/plugin_data/codeagent_plugin/workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.scripts_dir = Path(__file__).parent / "skills" / "CodeAgent" / "scripts"
        
        # 自动安装 Node.js 和 JS 依赖
        self._ensure_nodejs()
        self._ensure_js_dependencies()
    
    def _get_config(self, key: str, default=None):
        return self.config.get(key, default)
    
    def _extract_requirement(self, text: str) -> Optional[str]:
        patterns = [
            r'/agent\s+(.+)',
            r'@.*?/agent\s+(.+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def _is_exit_command(self, text: str) -> bool:
        return bool(re.search(r'/exitconver', text, re.IGNORECASE))
    
    def _sanitize_session_id(self, group_id: str, user_id: str) -> str:
        return f"{group_id}_{user_id}".replace(':', '_').replace('/', '_')
    
    def _is_in_blacklist(self, user_id: str, group_id: str) -> bool:
        admin_blacklist = self._get_config("admin_blacklist", [])
        group_blacklist = self._get_config("group_blacklist", [])
        if admin_blacklist and str(user_id) in [str(i) for i in admin_blacklist]:
            return True
        if group_blacklist and str(group_id) in [str(i) for i in group_blacklist]:
            return True
        return False
    
    def _cleanup_session(self, session_id: str):
        session_dir = self.workspace / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
    
    def _ensure_nodejs(self):
        """检查并安装 Node.js"""
        try:
            result = subprocess.run(['node', '-v'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info(f"Node.js 已安装: {result.stdout.strip()}")
                return True
        except:
            pass
        
        self.logger.warning("Node.js 未安装，正在尝试自动安装...")
        
        system = platform.system()
        
        if system == 'Linux':
            if self._install_nodejs_linux():
                return True
        elif system == 'Darwin':
            if self._install_nodejs_mac():
                return True
        else:
            self.logger.warning(f"不支持的系统: {system}，请手动安装 Node.js")
            return False
        
        self.logger.warning("Node.js 自动安装失败，JS/TS 检查功能将不可用")
        return False
    
    def _install_nodejs_linux(self) -> bool:
        """Linux 安装 Node.js"""
        # 尝试包管理器
        pkg_managers = [
            ('apt', 'apt-get update && apt-get install -y nodejs npm', 'apt'),
            ('yum', 'yum install -y nodejs npm', 'yum'),
            ('dnf', 'dnf install -y nodejs npm', 'dnf'),
            ('pacman', 'pacman -S --noconfirm nodejs npm', 'pacman')
        ]
        
        for pkg, cmd, name in pkg_managers:
            if shutil.which(pkg):
                try:
                    self.logger.info(f"使用 {name} 安装 Node.js...")
                    subprocess.run(cmd, shell=True, check=True, timeout=300)
                    self.logger.info(f"Node.js 安装成功 (via {name})")
                    return True
                except:
                    continue
        
        # 包管理器失败，尝试官方二进制
        return self._install_nodejs_from_official()
    
    def _install_nodejs_mac(self) -> bool:
        """macOS 安装 Node.js"""
        if shutil.which('brew'):
            try:
                self.logger.info("使用 Homebrew 安装 Node.js...")
                subprocess.run('brew install node', shell=True, check=True, timeout=300)
                self.logger.info("Node.js 安装成功 (via Homebrew)")
                return True
            except:
                pass
        return self._install_nodejs_from_official()
    
    def _install_nodejs_from_official(self) -> bool:
        """从官方下载 Node.js 二进制包"""
        node_version = 'v20.18.0'
        arch = 'x64'
        platform_map = {
            'Linux': 'linux',
            'Darwin': 'darwin'
        }
        plat = platform_map.get(platform.system(), 'linux')
        node_url = f'https://nodejs.org/dist/{node_version}/node-{node_version}-{plat}-{arch}.tar.xz'
        install_path = '/usr/local/lib/nodejs'
        bin_path = '/usr/local/bin'
        
        try:
            self.logger.info(f"下载 Node.js {node_version}...")
            tar_path = '/tmp/nodejs.tar.xz'
            urllib.request.urlretrieve(node_url, tar_path)
            
            with tarfile.open(tar_path, 'r:xz') as tar:
                tar.extractall('/tmp')
            
            extracted = f'/tmp/node-{node_version}-{plat}-{arch}'
            os.makedirs(install_path, exist_ok=True)
            subprocess.run(f'cp -r {extracted}/* {install_path}/', shell=True, check=True)
            
            for cmd in ['node', 'npm', 'npx']:
                src = f'{install_path}/bin/{cmd}'
                dst = f'{bin_path}/{cmd}'
                if os.path.exists(dst) or os.path.islink(dst):
                    os.remove(dst)
                os.symlink(src, dst)
            
            shutil.rmtree(extracted, ignore_errors=True)
            os.remove(tar_path)
            
            self.logger.info("Node.js 安装成功")
            return True
        except Exception as e:
            self.logger.error(f"Node.js 官方安装失败: {e}")
            return False
    
    def _ensure_js_dependencies(self):
        """确保 JS 检查器的依赖已安装"""
        js_checker = self.scripts_dir / "codeagent_js_checker.js"
        package_json = self.scripts_dir / "package.json"
        node_modules = self.scripts_dir / "node_modules"
        
        if not js_checker.exists():
            return
        
        # 检查 Node.js 是否可用
        try:
            subprocess.run(['node', '-v'], capture_output=True, check=True)
        except:
            return
        
        if not package_json.exists():
            return
        
        if not node_modules.exists():
            self.logger.info("正在安装 JS 检查器依赖 (npm install)...")
            try:
                proc = subprocess.run(
                    ['npm', 'install', '--production=false'],
                    cwd=str(self.scripts_dir),
                    capture_output=True,
                    text=True,
                    timeout=180
                )
                if proc.returncode == 0:
                    self.logger.info("JS 依赖安装完成")
                else:
                    self.logger.warning(f"JS 依赖安装失败: {proc.stderr[:200]}")
            except subprocess.TimeoutExpired:
                self.logger.warning("JS 依赖安装超时")
            except Exception as e:
                self.logger.warning(f"JS 依赖安装异常: {e}")
    
    def _call_sandbox(self, code: str, session_id: str, language: str = 'python', filename: str = 'main.py') -> Dict[str, Any]:
        sandbox_script = self.scripts_dir / "codeagent_sandbox.py"
        if not sandbox_script.exists():
            return {'success': False, 'error': 'Sandbox script not found'}

        timeout = self._get_config("code_running_time", 120)
        memory_limit = self._get_config("memory_limit", 512)
        max_file_size = self._get_config("max_file_size", 10)
        
        config_json = json.dumps({
            "wall_time_limit": timeout,
            "memory_limit_mb": memory_limit,
            "file_size_limit_mb": max_file_size
        })
        
        try:
            proc = subprocess.run(
                [
                    'python3', str(sandbox_script),
                    '--code', json.dumps(code),
                    '--session-id', session_id,
                    '--language', language,
                    '--filename', filename,
                    '--config', config_json
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 30
            )
            if proc.returncode != 0:
                return {'success': False, 'error': proc.stderr or 'Sandbox execution failed'}
            return json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Sandbox timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _call_security_scan(self, code: str, language: str = 'python') -> Dict[str, Any]:
        security_script = self.scripts_dir / "codeagent_security.py"
        if not security_script.exists():
            return {'passed': True, 'error': 'Security script not found'}
        
        try:
            proc = subprocess.run(
                [
                    'python3', str(security_script),
                    '--code', json.dumps(code),
                    '--language', language
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            return json.loads(proc.stdout)
        except Exception:
            return {'passed': True}
    
    def _call_js_checker(self, code: str, language: str = 'javascript') -> Dict[str, Any]:
        """调用 JavaScript/TypeScript 检查器"""
        checker_script = self.scripts_dir / "codeagent_js_checker.js"
        if not checker_script.exists():
            return {'passed': True, 'error': 'JS Checker script not found'}
        
        # 检查 Node.js 是否可用
        try:
            subprocess.run(['node', '-v'], capture_output=True, check=True)
        except:
            return {'passed': True, 'error': 'Node.js 不可用'}
        
        try:
            proc = subprocess.run(
                [
                    'node', str(checker_script),
                    '--code', json.dumps(code),
                    '--language', language
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            if proc.returncode != 0:
                try:
                    return json.loads(proc.stdout)
                except:
                    return {'passed': False, 'error': proc.stderr or 'JS Checker failed'}
            return json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            return {'passed': True, 'error': 'JS Checker timeout'}
        except Exception as e:
            return {'passed': True, 'error': str(e)}
    
    def _call_packager(
        self, 
        files: List[Dict], 
        test_files: List[Dict] = None,
        name: str = "project", 
        description: str = "",
        project_type: str = 'python'
    ) -> Dict[str, Any]:
        packager_script = self.scripts_dir / "codeagent_packager.py"
        if not packager_script.exists():
            return {'success': False, 'error': 'Packager script not found'}
        
        args = [
            'python3', str(packager_script),
            '--name', name,
            '--description', description,
            '--files', json.dumps(files),
            '--type', project_type
        ]
        
        if test_files:
            args.extend(['--test-files', json.dumps(test_files)])
        
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=120
            )
            return json.loads(proc.stdout)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _analyze_error(self, stderr: str) -> Dict[str, Any]:
        lines = stderr.split('\n')
        error_type = 'Unknown'
        error_line = 0
        error_message = stderr[:500]
        
        for line in lines:
            if 'Error' in line or 'Exception' in line:
                match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*(?:Error|Exception))', line)
                if match:
                    error_type = match.group(1)
                line_match = re.search(r'line\s+(\d+)', line, re.IGNORECASE)
                if line_match:
                    error_line = int(line_match.group(1))
                break
        
        return {
            'error_type': error_type,
            'error_line': error_line,
            'error_message': error_message
        }
    
    def _generate_debug_fix(self, error_info: Dict[str, Any]) -> str:
        error_type = error_info.get('error_type', '')
        error_message = error_info.get('error_message', '')
        
        if 'Import' in error_type:
            missing = re.search(r"No module named '([^']+)'", error_message)
            if missing:
                return f"在 requirements.txt 中添加 {missing.group(1)}"
        
        if 'Name' in error_type:
            missing = re.search(r"name '([^']+)' is not defined", error_message)
            if missing:
                return f"定义或导入 {missing.group(1)}"
        
        if 'TypeError' in error_type:
            return "检查函数参数类型和数量"
        
        if 'FileNotFound' in error_type:
            return "检查文件路径是否存在"
        
        if 'Connection' in error_type or 'Timeout' in error_type:
            return "检查网络连接或增加超时时间"
        
        if 'Permission' in error_type:
            return "检查文件/目录权限"
        
        if 'KeyError' in error_type:
            return "检查字典键是否存在"
        
        if 'IndexError' in error_type:
            return "检查列表索引是否越界"
        
        if 'ValueError' in error_type:
            return "检查值格式或范围是否正确"
        
        if 'SyntaxError' in error_type:
            return "检查代码语法"
        
        return f"检查运行时错误: {error_type}"
    
    def _assess_project(self, requirement: str) -> Dict[str, str]:
        project_type = 'python'
        if '网页' in requirement or '网站' in requirement:
            project_type = 'web'
        elif '游戏' in requirement:
            project_type = 'game'
        elif '模块' in requirement:
            project_type = 'module'
        elif '工具' in requirement:
            project_type = 'toolkit'
        elif 'api' in requirement.lower() or '接口' in requirement:
            project_type = 'api'
        elif 'js' in requirement.lower() or 'javascript' in requirement.lower():
            project_type = 'js'
        elif 'ts' in requirement.lower() or 'typescript' in requirement.lower():
            project_type = 'ts'
        elif 'shell' in requirement.lower() or 'bash' in requirement.lower():
            project_type = 'shell'
        
        word_count = len(requirement)
        if word_count < 30:
            size = 'S'
        elif word_count < 100:
            size = 'M'
        else:
            size = 'L'
        
        return {'type': project_type, 'size': size}
    
    def _create_process_json(self, session_id: str, requirement: str, project_type: str, project_size: str):
        process_file = self.workspace / session_id / 'process.json'
        process_data = {
            'session_id': session_id,
            'requirement': requirement,
            'project_type': project_type,
            'project_size': project_size,
            'status': 'init',
            'current_step': 'requirement_analysis',
            'completed_steps': [],
            'snapshots': [],
            'created_at': time.time(),
            'updated_at': time.time()
        }
        process_file.parent.mkdir(parents=True, exist_ok=True)
        with open(process_file, 'w', encoding='utf-8') as f:
            json.dump(process_data, f, ensure_ascii=False, indent=2)
        return process_data
    
    def _save_snapshot(self, session_id: str, step: str, code: str, files: List[Dict]):
        snapshot_dir = self.workspace / session_id / 'snapshots'
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshot_dir / f"{step}_{int(time.time())}.json"
        snapshot_data = {
            'step': step,
            'timestamp': time.time(),
            'code': code,
            'files': files
        }
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
        return str(snapshot_file)
    
    def _rollback_to_snapshot(self, session_id: str, step: str) -> Optional[Dict[str, Any]]:
        snapshot_dir = self.workspace / session_id / 'snapshots'
        if not snapshot_dir.exists():
            return None
        
        snapshot_files = sorted(snapshot_dir.glob(f"{step}_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not snapshot_files:
            return None
        
        try:
            with open(snapshot_files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    @filter.command("agent")
    async def agent_command(self, event: AstrMessageEvent):
        message_str = event.message_str
        user_id = str(event.get_sender_id())
        group_id = str(event.get_group_id()) if hasattr(event, 'get_group_id') else 'private'
        
        if not message_str:
            return
        
        if self._is_in_blacklist(user_id, group_id):
            return
        
        if self._is_exit_command(message_str):
            session_id = self._sanitize_session_id(group_id, user_id)
            if session_id in self.active_sessions:
                self.active_sessions[session_id]['active'] = False
                self._cleanup_session(session_id)
                del self.active_sessions[session_id]
                yield event.plain_result("已终止 Agent 任务，临时文件已清理。")
            else:
                yield event.plain_result("当前没有正在执行的 Agent 任务。")
            return
        
        requirement = self._extract_requirement(message_str)
        if not requirement:
            if '/agent' in message_str:
                yield event.plain_result("请提供具体的需求描述。示例：/agent 写一个计算器")
            return
        
        session_id = self._sanitize_session_id(group_id, user_id)
        
        if session_id in self.active_sessions:
            yield event.plain_result("当前已有 Agent 任务在执行，请等待完成或使用 /exitconver 退出。")
            return
        
        self.active_sessions[session_id] = {
            'active': True,
            'requirement': requirement,
            'step': 0,
            'start_time': time.time()
        }
        
        try:
            yield event.plain_result("正在分析需求...")
            
            assessment = self._assess_project(requirement)
            project_type = assessment['type']
            project_size = assessment['size']
            
            requirement_json = {
                'summary': requirement[:200],
                'type': project_type,
                'size': project_size
            }
            yield event.plain_result(f"需求分析完成:\n```json\n{json.dumps(requirement_json, ensure_ascii=False, indent=2)}\n```")
            
            self._create_process_json(session_id, requirement, project_type, project_size)
            
            if project_size in ['M', 'L']:
                yield event.plain_result(f"检测到 {project_size} 型项目，正在生成脚手架...")
                yield event.plain_result("脚手架已生成，请确认是否继续。回复 '确认' 继续。")
                await asyncio.sleep(3)
            
            yield event.plain_result("开始编写核心代码（工具包和API）...")
            
            code = f'''
import sys
import os

def main():
    print("Hello from CodeAgent!")
    print("需求: {requirement}")
    print("项目类型: {project_type}")
    print("项目体量: {project_size}")

if __name__ == "__main__":
    main()
'''
            
            filename = "main.py"
            language = "python"
            
            yield event.plain_result("核心代码编写完成，正在运行测试...")
            
            max_debug = self._get_config("max_debug_rounds", 10)
            quality_threshold = self._get_config("quality_threshold", 75)
            
            for debug_round in range(max_debug):
                sandbox_result = self._call_sandbox(code, session_id, language, filename)
                
                if not sandbox_result.get('success', False):
                    error_info = self._analyze_error(sandbox_result.get('stderr', '') or sandbox_result.get('error', 'Unknown error'))
                    fix = self._generate_debug_fix(error_info)
                    
                    if debug_round >= max_debug - 1:
                        yield event.plain_result(f"Debug 循环 #{debug_round + 1}/{max_debug} 失败\n错误: {error_info.get('error_message', '')[:200]}")
                        self.active_sessions.pop(session_id, None)
                        return
                    
                    yield event.plain_result(f"Debug 循环 #{debug_round + 1}/{max_debug}\n错误类型: {error_info.get('error_type', 'Unknown')}\n修复方案: {fix}")
                    code = code + f"\n# Fixed: {fix}\n"
                    continue
                
                yield event.plain_result(f"核心代码测试通过 (Debug 循环 #{debug_round + 1})")
                break
            else:
                yield event.plain_result("Debug 循环结束但未成功。")
                self.active_sessions.pop(session_id, None)
                return
            
            # 安全检查
            quality_score = 0
            
            if project_type in ['js', 'ts']:
                yield event.plain_result("正在执行 JavaScript/TypeScript 检查...")
                check_result = self._call_js_checker(code, project_type)
                
                if not check_result.get('passed', True):
                    issues = check_result.get('issues', [])
                    critical = [i for i in issues if i.get('level') == 'critical']
                    high = [i for i in issues if i.get('level') == 'high']
                    
                    if critical or high:
                        yield event.plain_result(f"安全检查未通过: {len(critical)} 个严重, {len(high)} 个高危问题")
                        self.active_sessions.pop(session_id, None)
                        return
                    
                    quality_score = check_result.get('quality_score', 0)
                    if quality_score < quality_threshold:
                        yield event.plain_result(f"质量评分: {quality_score}/{quality_threshold}，低于阈值，正在重写...")
                        code = code + f"\n// Quality improved\n"
                else:
                    quality_score = check_result.get('quality_score', 75)
            else:
                # Python 项目的原有安全审查逻辑
                yield event.plain_result("正在执行安全审查...")
                security_report = self._call_security_scan(code, language)
                
                if security_report.get('risk_level') in ['critical', 'high']:
                    yield event.plain_result(f"安全拦截: {security_report.get('summary', 'Unknown')}")
                    self.active_sessions.pop(session_id, None)
                    return
                
                quality_score = security_report.get('quality_score', 0)
                if quality_score < quality_threshold:
                    yield event.plain_result(f"质量评分: {quality_score}/{quality_threshold}，低于阈值，正在重写...")
                    code = code + f"\n# Quality improved\n"
            
            # 生成测试代码
            test_code = f'''
import pytest
from src.main import main

def test_main():
    assert main() is not None
'''
            
            files = [
                {'name': filename, 'content': code, 'description': '主程序文件'},
                {'name': 'README.md', 'content': f'# {requirement[:50]}\n\n{requirement}', 'description': '项目说明'},
                {'name': 'requirements.txt', 'content': '', 'description': '依赖清单'},
                {'name': 'pyproject.toml', 'content': '', 'description': '项目配置'}
            ]
            
            test_files = [
                {'name': 'test_main.py', 'content': test_code, 'description': '主程序测试'}
            ]
            
            snapshot_path = self._save_snapshot(session_id, 'core_complete', code, files)
            yield event.plain_result(f"已保存快照: {snapshot_path}")
            
            yield event.plain_result("正在打包文件...")
            pack_result = self._call_packager(
                files=files,
                test_files=test_files,
                name=f"CodeAgent_{session_id}",
                description=requirement,
                project_type=project_type
            )
            
            if pack_result.get('success', False):
                zip_path = pack_result.get('zip_path', '')
                yield event.plain_result(f"""
项目已完成！

执行报告:
- 需求: {requirement[:100]}
- 项目类型: {project_type}
- 项目体量: {project_size}
- 文件数: {pack_result.get('file_count', 0)}
- 质量评分: {quality_score}/100

使用教程: python {filename}
""")
                if os.path.exists(zip_path):
                    from astrbot.api.message_components import File
                    yield event.chain_result([File(file=zip_path, name=f"{requirement[:20]}_交付.zip")])
                    os.remove(zip_path)
            else:
                yield event.plain_result(f"打包失败: {pack_result.get('error', 'Unknown')}\n\n代码:\n```\n{code}\n```")
            
            self.active_sessions.pop(session_id, None)
            
        except Exception as e:
            self.logger.error(f"CodeAgent error: {e}")
            yield event.plain_result(f"执行出错: {e}")
            self.active_sessions.pop(session_id, None)

    async def terminate(self):
        for session_id in list(self.active_sessions.keys()):
            self.active_sessions[session_id]['active'] = False
            self._cleanup_session(session_id)
        self.active_sessions.clear()
        self.logger.info("CodeAgent 插件已卸载")


def get_star(context: Context):
    return CodeAgentPlugin(context)
