#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CodeAgent 打包工具
路径：./scripts/codeagent_packager.py
"""

import os
import sys
import json
import zipfile
import shutil
import ast
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

@dataclass
class ProjectFile:
    name: str
    path: str
    content: str
    size: int
    language: str
    description: str = ""


@dataclass
class ProjectInfo:
    name: str
    description: str
    language: str
    dependencies: List[str] = field(default_factory=list)
    dev_dependencies: List[str] = field(default_factory=list)
    files: List[ProjectFile] = field(default_factory=list)
    test_files: List[ProjectFile] = field(default_factory=list)
    main_file: str = ""
    author: str = "N/A"
    created_at: str = ""
    install_commands: List[str] = field(default_factory=list)
    usage_commands: List[str] = field(default_factory=list)
    python_version: str = ">=3.10"
    project_type: str = "python"


class ReadmeGenerator:
    
    @staticmethod
    def generate(project: ProjectInfo) -> str:
        lines = []
        
        lines.append(f"# {project.name}")
        lines.append("")
        
        lines.append(f"## 项目描述")
        lines.append("")
        lines.append(project.description)
        lines.append("")
        
        lines.append(f"## 技术栈")
        lines.append("")
        lines.append(f"- **语言**: {project.language}")
        if project.dependencies:
            lines.append("- **依赖**:")
            for dep in project.dependencies:
                lines.append(f"  - `{dep}`")
        if project.dev_dependencies:
            lines.append("- **开发依赖**:")
            for dep in project.dev_dependencies:
                lines.append(f"  - `{dep}`")
        lines.append("")
        
        lines.append(f"## 文件结构")
        lines.append("")
        lines.append("```")
        lines.append(project.name + "/")
        for file in project.files:
            prefix = "├── " if file != project.files[-1] else "└── "
            lines.append(f"{prefix}{file.name}  # {file.description}")
        if project.test_files:
            lines.append("├── tests/")
            for file in project.test_files:
                prefix = "│   ├── " if file != project.test_files[-1] else "│   └── "
                lines.append(f"{prefix}{file.name}  # {file.description}")
        lines.append("```")
        lines.append("")
        
        if project.install_commands:
            lines.append(f"## 安装依赖")
            lines.append("")
            for cmd in project.install_commands:
                lines.append(f"```bash")
                lines.append(cmd)
                lines.append("```")
                lines.append("")
        
        lines.append(f"## 使用方法")
        lines.append("")
        if project.usage_commands:
            for cmd in project.usage_commands:
                lines.append(f"```bash")
                lines.append(cmd)
                lines.append("```")
                lines.append("")
        else:
            lines.append(f"1. 确保已安装依赖")
            lines.append(f"2. 运行主文件:")
            lines.append(f"```bash")
            lines.append(f"python {project.main_file}" if project.language == 'python' else f"node {project.main_file}")
            lines.append(f"```")
            lines.append("")
        
        lines.append(f"## 运行测试")
        lines.append("")
        lines.append(f"```bash")
        lines.append(f"pytest tests/ -v")
        lines.append(f"```")
        lines.append("")
        
        lines.append(f"---")
        lines.append("")
        lines.append(f"*由 {project.author} 制作于 {project.created_at}*")
        lines.append("")
        
        return "\n".join(lines)


class DependencyGenerator:
    
    @staticmethod
    def extract_python_imports(code: str) -> Set[str]:
        modules = set()
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top_module = alias.name.split('.')[0]
                        modules.add(top_module)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top_module = node.module.split('.')[0]
                        modules.add(top_module)
        except SyntaxError:
            pass
        return modules
    
    @staticmethod
    def detect_python_dependencies(files: List[ProjectFile]) -> List[str]:
        all_modules = set()
        
        for file in files:
            if file.language == 'python':
                modules = DependencyGenerator.extract_python_imports(file.content)
                all_modules.update(modules)
        
        external_modules = []
        for module_name in all_modules:
            if DependencyGenerator._is_external_module(module_name):
                external_modules.append(module_name)
        
        return sorted(list(set(external_modules)))
    
    @staticmethod
    def _is_external_module(module_name: str) -> bool:
        try:
            import importlib
            module = importlib.import_module(module_name)
            if hasattr(module, '__file__') and module.__file__:
                if 'site-packages' in module.__file__:
                    return True
        except ImportError:
            pass
        return False
    
    @staticmethod
    def generate_requirements(dependencies: List[str]) -> str:
        return '\n'.join(dependencies) + '\n' if dependencies else ''
    
    @staticmethod
    def generate_pyproject_toml(project: ProjectInfo) -> str:
        deps_lines = '\n'.join([f'    "{dep}",' for dep in project.dependencies])
        dev_deps_lines = '\n'.join([f'    "{dep}",' for dep in project.dev_dependencies])
        
        return f'''[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{project.name.lower().replace(' ', '-').replace('_', '-')}"
version = "1.0.0"
description = "{project.description}"
authors = [{{name = "{project.author}"}}]
readme = "README.md"
requires-python = "{project.python_version}"
dependencies = [
{deps_lines}
]

[project.optional-dependencies]
dev = [
{dev_deps_lines}
]

[tool.ruff]
line-length = 120
target-version = "py310"

[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --cov=src --cov-report=term-missing"
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.coverage.run]
source = ["src"]
omit = ["tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if self.debug:",
    "if __name__ == .__main__.:",
]
'''
    
    @staticmethod
    def generate_package_json(project: ProjectInfo) -> str:
        pkg = {
            "name": project.name.lower().replace(" ", "-"),
            "version": "1.0.0",
            "description": project.description,
            "main": project.main_file,
            "scripts": {
                "start": f"node {project.main_file}",
                "test": "jest"
            },
            "dependencies": {}
        }
        
        for dep in project.dependencies:
            pkg["dependencies"][dep] = "latest"
        
        dev_deps = {}
        for dep in project.dev_dependencies:
            dev_deps[dep] = "latest"
        if dev_deps:
            pkg["devDependencies"] = dev_deps
        
        return json.dumps(pkg, ensure_ascii=False, indent=2)
    
    @staticmethod
    def detect_node_dependencies(code: str) -> List[str]:
        import re
        patterns = [
            r'(?:require|import)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            r'import\s+[\w{}\s*,\n]+\s+from\s+[\'"]([^\'"]+)[\'"]',
            r'import\s+[\'"]([^\'"]+)[\'"]',
            r'export\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]',
            r'import\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        ]
        
        cleaned = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'[\'"].*?[\'"]', '', cleaned)
        
        found = set()
        for pattern in patterns:
            matches = re.findall(pattern, cleaned, re.MULTILINE)
            for m in matches:
                module = m.strip()
                if (module and not module.startswith('.') 
                    and not module.startswith('node:') 
                    and not module.startswith('/')):
                    if module.startswith('@') and '/' in module:
                        found.add(module)
                    elif not module.startswith('@'):
                        found.add(module)
        
        return sorted(list(found))


class ProjectPackager:
    
    def __init__(self, output_dir: str = "./codeagent_workspace/archive"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def detect_language(self, files: List[ProjectFile]) -> str:
        extensions = {}
        for file in files:
            ext = Path(file.name).suffix.lower()
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
        
        if not extensions:
            return 'python'
        
        sorted_exts = sorted(extensions.items(), key=lambda x: x[1], reverse=True)
        main_ext = sorted_exts[0][0]
        
        lang_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.sh': 'shell', '.bash': 'shell', '.json': 'json',
            '.html': 'html', '.css': 'css', '.md': 'markdown',
            '.yaml': 'yaml', '.yml': 'yaml',
        }
        
        return lang_map.get(main_ext, 'python')
    
    def _install_node_dependencies(self, project_dir: Path) -> bool:
        try:
            proc = subprocess.run(
                ['npm', 'i'],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=300
            )
            return proc.returncode == 0
        except Exception:
            return False
    
    def _cleanup_temp_files(self, project_dir: Path):
        patterns = ['__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache']
        for pattern in patterns:
            for path in project_dir.rglob(pattern):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
        
        for path in project_dir.rglob('*.pyc'):
            path.unlink()
        
        for path in project_dir.rglob('coverage.json'):
            path.unlink()
    
    def build_project_info(
        self,
        files: List[ProjectFile],
        test_files: List[ProjectFile],
        name: str,
        description: str,
        main_file: str = None,
        project_type: str = 'python'
    ) -> ProjectInfo:
        language = self.detect_language(files)
        
        if not main_file:
            for file in files:
                if file.name in ['main.py', 'index.js', 'app.py', 'script.sh']:
                    main_file = file.name
                    break
            if not main_file and files:
                main_file = files[0].name
        
        dependencies = []
        dev_dependencies = ['pytest>=7.4.0', 'ruff>=0.1.0', 'mypy>=1.0.0', 'pytest-cov>=4.0.0']
        
        if language == 'python':
            dependencies = DependencyGenerator.detect_python_dependencies(files)
        elif language in ['javascript', 'typescript']:
            all_deps = set()
            for file in files:
                if file.language in ['javascript', 'typescript']:
                    deps = DependencyGenerator.detect_node_dependencies(file.content)
                    all_deps.update(deps)
            dependencies = sorted(list(all_deps))
            dev_dependencies = ['jest', 'eslint', 'typescript']
        
        install_commands = []
        if dependencies:
            if language == 'python':
                install_commands.append("pip install -r requirements.txt")
                install_commands.append("pip install -e .[dev]")
            elif language in ['javascript', 'typescript']:
                install_commands.append("npm install")
        
        usage_commands = []
        if main_file:
            if language == 'python':
                usage_commands.append(f"python {main_file}")
            elif language in ['javascript', 'typescript']:
                usage_commands.append(f"node {main_file}")
            elif language == 'shell':
                usage_commands.append(f"bash {main_file}")
                usage_commands.append(f"chmod +x {main_file}")
        
        return ProjectInfo(
            name=name,
            description=description,
            language=language,
            dependencies=dependencies,
            dev_dependencies=dev_dependencies,
            files=files,
            test_files=test_files,
            main_file=main_file or "",
            author="N/A",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            install_commands=install_commands,
            usage_commands=usage_commands,
            python_version=">=3.10",
            project_type=project_type
        )
    
    def pack(
        self,
        files: List[Dict],
        test_files: List[Dict] = None,
        name: str = "project",
        description: str = "",
        main_file: str = None,
        project_type: str = 'python',
        extra_files: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        result = {
            'success': False,
            'zip_path': '',
            'file_count': 0,
            'size': 0,
            'error': None
        }
        
        try:
            project_files = []
            for item in files:
                project_files.append(create_project_file(
                    item.get('name', 'file.txt'),
                    item.get('content', ''),
                    item.get('description', '')
                ))
            
            test_project_files = []
            if test_files:
                for item in test_files:
                    test_project_files.append(create_project_file(
                        item.get('name', 'test_file.py'),
                        item.get('content', ''),
                        item.get('description', '测试文件')
                    ))
            
            project = self.build_project_info(
                project_files, 
                test_project_files,
                name, 
                description, 
                main_file,
                project_type
            )
            
            temp_dir = Path(f"/tmp/codeagent_pack_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                project_dir = temp_dir / project.name
                project_dir.mkdir(parents=True, exist_ok=True)
                
                src_dir = project_dir / "src"
                src_dir.mkdir(parents=True, exist_ok=True)
                
                for file in project.files:
                    file_path = src_dir / file.name
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(file.content, encoding='utf-8')
                
                if project.test_files:
                    tests_dir = project_dir / "tests"
                    tests_dir.mkdir(parents=True, exist_ok=True)
                    for file in project.test_files:
                        file_path = tests_dir / file.name
                        file_path.write_text(file.content, encoding='utf-8')
                
                readme_content = ReadmeGenerator.generate(project)
                (project_dir / "README.md").write_text(readme_content, encoding='utf-8')
                
                if project.language == 'python':
                    pyproject_content = DependencyGenerator.generate_pyproject_toml(project)
                    (project_dir / "pyproject.toml").write_text(pyproject_content, encoding='utf-8')
                    
                    if project.dependencies:
                        req_content = DependencyGenerator.generate_requirements(project.dependencies)
                        (project_dir / "requirements.txt").write_text(req_content, encoding='utf-8')
                    
                    (project_dir / "src" / "__init__.py").write_text("", encoding='utf-8')
                    (project_dir / "tests" / "__init__.py").write_text("", encoding='utf-8')
                    
                elif project.language in ['javascript', 'typescript']:
                    pkg_content = DependencyGenerator.generate_package_json(project)
                    (project_dir / "package.json").write_text(pkg_content, encoding='utf-8')
                    self._install_node_dependencies(project_dir)
                
                if extra_files:
                    for extra in extra_files:
                        extra_name = extra.get('name', '')
                        content = extra.get('content', '')
                        if extra_name:
                            (project_dir / extra_name).write_text(content, encoding='utf-8')
                
                self._cleanup_temp_files(project_dir)
                
                zip_name = f"{project.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                zip_path = self.output_dir / zip_name
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, _, zip_files in os.walk(project_dir):
                        for file in zip_files:
                            file_path = Path(root) / file
                            arcname = file_path.relative_to(temp_dir)
                            zf.write(file_path, arcname)
                
                size = zip_path.stat().st_size
                
                result['success'] = True
                result['zip_path'] = str(zip_path)
                result['file_count'] = len(project.files) + len(project.test_files) + 2
                result['size'] = size
                
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            result['error'] = str(e)
        
        return result


def create_project_file(
    name: str,
    content: str,
    description: str = ""
) -> ProjectFile:
    language = Path(name).suffix.lower().lstrip('.')
    lang_map = {
        'py': 'python', 'js': 'javascript', 'ts': 'typescript',
        'sh': 'shell', 'bash': 'shell', 'json': 'json',
        'html': 'html', 'css': 'css', 'md': 'markdown',
        'yaml': 'yaml', 'yml': 'yaml',
    }
    
    return ProjectFile(
        name=name,
        path=name,
        content=content,
        size=len(content.encode('utf-8')),
        language=lang_map.get(language, 'text'),
        description=description
    )


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='CodeAgent 打包工具')
    parser.add_argument('--name', type=str, default='my-project', help='项目名称')
    parser.add_argument('--description', type=str, default='', help='项目描述')
    parser.add_argument('--main', type=str, help='主文件名')
    parser.add_argument('--files', type=str, help='文件列表 (JSON 格式)')
    parser.add_argument('--test-files', type=str, help='测试文件列表 (JSON 格式)')
    parser.add_argument('--file-dir', type=str, help='文件目录（自动扫描）')
    parser.add_argument('--type', type=str, default='python', help='项目类型')
    parser.add_argument('--output', type=str, help='输出路径')
    parser.add_argument('--test', action='store_true', help='运行测试')
    
    args = parser.parse_args()
    
    if args.test:
        print("运行打包测试...")
        
        files = [
            {'name': 'main.py', 'content': '''
import requests
import json
import pandas as pd

def main():
    print("Hello, World!")
    response = requests.get('https://api.github.com')
    print(f"Status: {response.status_code}")

if __name__ == '__main__':
    main()
''', 'description': '主程序入口'},
            {'name': 'utils.py', 'content': '''
import numpy as np
from datetime import datetime

def format_json(data):
    import json
    return json.dumps(data, indent=2)

def read_file(path):
    with open(path, 'r') as f:
        return f.read()
''', 'description': '工具函数'}
        ]
        
        test_files = [
            {'name': 'test_main.py', 'content': '''
import pytest
from src.main import main

def test_main():
    assert main() is None
''', 'description': '主程序测试'},
            {'name': 'test_utils.py', 'content': '''
import pytest
from src.utils import format_json, read_file

def test_format_json():
    data = {"key": "value"}
    result = format_json(data)
    assert "key" in result
''', 'description': '工具函数测试'}
        ]
        
        packager = ProjectPackager()
        result = packager.pack(
            files=files,
            test_files=test_files,
            name='test-project',
            description='这是一个测试项目',
            project_type='python'
        )
        
        print(f"成功: {result['success']}")
        print(f"文件: {result['zip_path']}")
        print(f"文件数: {result['file_count']}")
        print(f"大小: {result['size']} bytes")
        
        if result['error']:
            print(f"错误: {result['error']}")
        
        print("测试完成")
        return
    
    files = []
    if args.files:
        data = json.loads(args.files)
        for item in data:
            files.append({
                'name': item.get('name', 'file.txt'),
                'content': item.get('content', ''),
                'description': item.get('description', '')
            })
    elif args.file_dir:
        dir_path = Path(args.file_dir)
        if dir_path.exists():
            for file_path in dir_path.iterdir():
                if file_path.is_file():
                    content = file_path.read_text(encoding='utf-8')
                    files.append({
                        'name': file_path.name,
                        'content': content,
                        'description': ''
                    })
    
    test_files = []
    if args.test_files:
        test_data = json.loads(args.test_files)
        for item in test_data:
            test_files.append({
                'name': item.get('name', 'test_file.py'),
                'content': item.get('content', ''),
                'description': item.get('description', '测试文件')
            })
    
    if not files:
        print("错误: 请提供 --files 或 --file-dir", file=sys.stderr)
        sys.exit(1)
    
    packager = ProjectPackager()
    result = packager.pack(
        files=files,
        test_files=test_files,
        name=args.name,
        description=args.description or '由 CodeAgent 生成的项目',
        main_file=args.main,
        project_type=args.type
    )
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    
    if result['success']:
        print(f"打包成功: {result['zip_path']}", file=sys.stderr)
    else:
        print(f"打包失败: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

