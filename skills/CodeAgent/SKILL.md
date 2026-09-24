---
name: CodeAgent
description: 代码编写插件。AI自动完成需求分析、方案设计、代码编写、依赖补全、运行测试、日志分析、Debug、代码审查、打包交付全流程，帮你省下一整套开发流程。
license: Unlicense
metadata:
  author: N/A
  version: 0.0.0
  type: agent
  permission_level: normal
  sandbox: true
---

# CodeAgent

## 触发条件

用户发送以下格式时触发：
```

@机器人昵称 /agent <需求描述>

```

**示例**：
```

@Mybot /agent 写一个 Python 脚本，读取 CSV 文件并生成饼图

```

**重要**：没有艾特机器人的 `/agent` 不会触发。

---

## 强制行为约束

AI 在执行 CodeAgent 任务时，必须遵守以下规则：

1. **输出格式**：所有结构化输出（方案、报告、错误信息）必须使用 JSON + Markdown 混合格式
2. **用户确认点**：在以下节点必须等待用户确认才能继续：
   - 需求分析完成后
   - 方案设计完成后
   - 脚手架生成完成后（M/L 项目）
3. **超时处理**：等待用户确认时，60 秒无响应则自动取消任务
4. **中断恢复**：任务被 `/exitconver` 中断后，重新触发时检测 `process.json`，询问用户是否继续
5. **并行限制**：同时只能运行 1 个任务，新请求被拒绝并提示等待

---

## 需求处理流程

### 第一步：精简用户需求

AI 必须首先整合用户提示词，精简不必要内容：

**精简规则**：
- 移除情绪词（"帮我"、"求求了"、"急"等）
- 移除重复信息
- 提取核心功能点（不超过 5 个）
- 提取约束条件（语言、框架、平台等）

**精简后输出格式**：
```json
{
  "original_length": 150,
  "compressed_length": 45,
  "core_requirement": "写一个 Python 脚本读取 CSV 并生成饼图",
  "features": ["读取 CSV 文件", "生成饼图", "保存为 PNG"],
  "constraints": ["语言: Python", "依赖: pandas, matplotlib"],
  "project_type": "toolkit",
  "project_size": "S"
}
```

第二步：判断项目类型

根据用户需求中的关键词判断：

关键词 项目类型
网页、网站、前端、页面 web
游戏 game
模块、库、包 module
工具、脚本、命令行 toolkit
api、接口、后端 api
js、javascript js
ts、typescript ts
shell、bash shell
其他 python（默认）

第三步：判断项目体量

· 需求字数 < 30 字 → S（小型，单文件）
· 需求字数 30-100 字 → M（中型，多文件）
· 需求字数 > 100 字 → L（大型，完整项目）

第四步：输出 JSON 给用户确认

将分析结果以 JSON 格式发送给用户，等待确认。

---

项目架构与脚手架

中大项目（M/L）必须执行：

1. 构思整体架构：
   · 确定项目分层（表现层/业务层/数据层）
   · 确定模块划分
   · 确定依赖关系
2. 生成项目脚手架：
   ```
   project_name/
   ├── src/
   │   ├── __init__.py
   │   ├── core/          # 核心工具包
   │   ├── api/           # API 接口
   │   └── modules/       # 业务模块
   ├── tests/
   │   ├── __init__.py
   │   ├── test_core/
   │   └── test_modules/
   ├── docs/
   ├── pyproject.toml
   ├── requirements.txt
   └── README.md
   ```
3. 发送给用户确认，等待回复后再继续。

---

开发顺序

必须先写工具包和 API，再写业务内容。

1. 工具包（core/）：基础函数、通用工具、数据模型
2. API 接口：对外接口定义、路由、入参/出参模型
3. 业务模块：具体业务逻辑

---

process.json 格式

AI 必须在任务开始时创建 process.json：

```json
{
  "session_id": "group_123_user_456",
  "requirement": "原始需求",
  "project_type": "python",
  "project_size": "M",
  "status": "in_progress",
  "current_step": "writing_core",
  "steps_completed": ["requirement_analysis", "scaffold_generation"],
  "snapshots": [
    {
      "id": "snapshot_20260809_120000",
      "step": "core_complete",
      "timestamp": 1691575200,
      "files": ["src/core/utils.py", "src/api/routes.py"]
    }
  ],
  "errors": [],
  "created_at": 1691575200,
  "updated_at": 1691575500
}
```

---

质量保障流程

Python 项目

写完工具包和 API 后，不着急写业务内容，先执行：

1. Ruff：代码风格检查
   ```bash
   ruff check src/
   ```
2. Mypy：类型检查
   ```bash
   mypy src/ --strict
   ```
3. Bandit：安全漏洞扫描
   ```bash
   bandit -r src/
   ```
4. Pytest：单元测试 + 边界测试
   ```bash
   pytest tests/ -v --cov=src --cov-report=term-missing
   ```

通过标准：

· Ruff：0 个错误
· Mypy：0 个错误
· Bandit：0 个高危/严重问题
· Pytest：全部通过，覆盖率 ≥ 90%

JavaScript/TypeScript 项目

1. ESLint：代码风格检查
   ```bash
   npx eslint src/ --fix
   ```
2. TypeScript 类型检查（仅 TS 项目）
   ```bash
   npx tsc --noEmit --strict
   ```
3. JSDoc 强制要求（所有 JS 项目）
   · 每个函数必须包含 JSDoc 注释
   · 包含：@param、@returns、@throws
   · 示例：
   ```javascript
   /**
    * 读取 CSV 文件并返回数据数组
    * @param {string} filePath - CSV 文件路径
    * @param {Object} options - 读取选项
    * @param {string} options.delimiter - 分隔符，默认 ','
    * @returns {Promise<Array<Object>>} 数据数组
    * @throws {Error} 文件不存在或读取失败时抛出
    */
   async function readCSV(filePath, options = {}) {
       // 实现
   }
   ```
4. 文件开头注释：
   ```javascript
   /**
    * @fileoverview 文件说明
    * @author N/A
    * @version 0.0.0
    */
   ```
5. 测试：使用 Jest 编写单元测试

Shell 项目

使用 shellcheck-py 进行静态检查：

```bash
shellcheck scripts/*.sh
```

---

业务模块迭代

每写完一个业务模块：

1. 编写测试：使用 Pytest 编写模块测试
2. 检查连通性：验证模块是否正常调用
3. 检查运行状态：验证模块是否能跑起来
4. 全部通过后：保存快照，进入下一模块

---

回滚机制

每个业务模块编写完成后，必须保存快照：

快照内容：

```json
{
  "snapshot_id": "snapshot_20260809_120000",
  "step": "business_module_2",
  "timestamp": 1691575200,
  "files": {
    "src/modules/module2.py": "文件内容...",
    "tests/test_module2.py": "测试内容..."
  }
}
```

回滚触发条件：

· 当前模块测试连续失败 3 次
· 当前模块修复时间超过 5 分钟
· 用户手动请求回滚（发送 /rollback）

回滚输出：

```
⏪ 已回滚到快照: snapshot_20260809_115530
已恢复文件: src/modules/module2.py, tests/test_module2.py
请检查后重新开始该模块的开发。
```

---

代码审查

交付前必须执行代码审查：

Python 审查内容

1. 逻辑正确性：核心逻辑是否正确
2. 异常处理：是否覆盖异常场景
3. 代码复用：是否有重复代码
4. 性能：是否有性能瓶颈
5. 安全：是否有安全漏洞（Bandit 已覆盖）

JS/TS 审查内容

1. 逻辑正确性：核心逻辑是否正确
2. JSDoc 完整性：所有函数是否有 JSDoc
3. 异步处理：是否正确处理 Promise/async
4. 错误处理：是否覆盖异常场景
5. 安全：是否有安全漏洞（ESLint + 安全扫描已覆盖）

审查输出格式

```json
{
  "review_status": "passed|failed|warning",
  "issues": [
    {
      "severity": "high|medium|low",
      "file": "src/main.py",
      "line": 42,
      "message": "未处理文件不存在异常",
      "suggestion": "添加 try/except 捕获 FileNotFoundError"
    }
  ],
  "score": 88
}
```

---

项目规范

中大项目（M/L）必须：

1. 类型注解：所有函数参数和返回值必须有类型注解
2. pyproject.toml：包含项目元数据、依赖、工具配置
3. requirements.txt：包含所有依赖（精确版本）
4. 结构分明：src/、tests/、docs/ 目录分离
5. 清理临时文件：
   ```bash
   rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
   ```

JS 项目特殊要求

1. 文件开头注释：@fileoverview、@author、@version
2. JSDoc：所有函数必须包含 JSDoc（@param、@returns、@throws）
3. ESLint 配置：使用标准规则集

---

环境检测

AI 必须执行环境检测：

环境 检测命令 缺失处理
Python python3 --version 提示用户安装
Node.js node --version main.py 自动安装
npm npm --version main.py 自动安装

---

辅助脚本 API（完整版）

所有脚本位于 ./scripts/，AI 必须通过调用脚本 API 完成对应功能。

脚本一：沙箱执行环境 (codeagent_sandbox.py)

API 调用方式：

```bash
python3 ./scripts/codeagent_sandbox.py \
  --code '<JSON序列化的代码>' \
  --session-id '<会话ID>' \
  --language '<python|javascript|bash>' \
  --filename '<文件名>' \
  --config '<JSON配置>'
```

返回值：

```json
{
  "success": true,
  "stdout": "标准输出内容",
  "stderr": "错误输出内容",
  "exit_code": 0,
  "time_elapsed": 0.12,
  "files": [{"name": "file.txt", "size": 1024, "path": "..."}],
  "error": null,
  "security_warning": null
}
```

AI 行为：

1. 代码必须 JSON 序列化后传入 --code
2. success 为 false 时进入 Debug 循环
3. security_warning 非空时立即终止

---

脚本二：Python 安全审查模块 (codeagent_security.py)

API 调用方式：

```bash
python3 ./scripts/codeagent_security.py \
  --code '<JSON序列化的代码>' \
  --language '<python|shell|auto>'
```

返回值：

```json
{
  "file_path": "main.py",
  "findings": [],
  "risk_level": "safe|low|medium|high|critical",
  "summary": "发现 0 个问题",
  "passed": true,
  "quality_score": 85,
  "quality_details": {
    "docstrings": 2,
    "max_nesting": 2,
    "long_lines": 0,
    "comment_ratio": 15.0,
    "function_count": 3,
    "type_hints": 3,
    "code_smells": 0
  },
  "test_coverage": 90.0,
  "test_results": {
    "passed": true,
    "passed_count": 5,
    "failed_count": 0,
    "coverage": 90.0
  }
}
```

AI 行为：

1. 检查 risk_level：critical 或 high → 拒绝交付
2. 检查 quality_score：< 75 分 → 进入重写流程
3. 检查 test_coverage：< 90% → 提示增加测试用例

---

脚本三：JavaScript/TypeScript 检查器 (codeagent_js_checker.js)

API 调用方式：

```bash
node ./scripts/codeagent_js_checker.js \
  --code '<JSON序列化的代码>' \
  --language '<javascript|typescript|auto>'
```

返回值：

```json
{
  "passed": true,
  "quality_score": 85,
  "issues": [
    {
      "line": 10,
      "level": "high",
      "message": "使用 eval 存在安全风险",
      "tool": "security",
      "suggestion": "请使用安全替代方案"
    }
  ],
  "summary": "发现 0 个问题",
  "eslint": {
    "issues": [],
    "error": null
  },
  "typescript": {
    "issues": [],
    "error": null
  },
  "security": {
    "issues": [],
    "risk_level": "safe"
  },
  "quality": {
    "score": 85,
    "details": {
      "comment_ratio": 15,
      "function_count": 3,
      "long_functions": 0,
      "long_lines": 0,
      "used_var": false
    },
    "issues": []
  }
}
```

AI 行为：

1. 仅当 project_type 为 js 或 ts 时调用此脚本
2. 检查 passed 字段：false → 拒绝交付
3. 检查 issues 中 level 为 critical 或 high 的问题：存在则拒绝交付
4. 检查 quality_score：< 75 → 进入重写流程

---

脚本四：打包工具 (codeagent_packager.py)

API 调用方式：

```bash
python3 ./scripts/codeagent_packager.py \
  --name '<项目名称>' \
  --description '<项目描述>' \
  --files '<JSON文件列表>' \
  --test-files '<JSON测试文件列表>' \
  --type '<python|js|ts|web|toolkit>'
```

返回值：

```json
{
  "success": true,
  "zip_path": "./codeagent_workspace/archive/项目名_20260809_120000.zip",
  "file_count": 5,
  "size": 2048,
  "error": null
}
```

AI 行为：

1. 主文件和测试文件分别整理为 JSON 数组
2. 调用脚本生成 zip 包
3. 从 zip_path 读取文件路径发送给用户

---

错误处理优先级

优先级 错误类型 处理方式
P0 安全拦截（critical/high） 立即终止，不可恢复
P1 沙箱执行失败 进入 Debug 循环
P2 质量评分不足 触发重写
P3 测试覆盖率不足 提示用户，继续交付（不阻塞）
P4 打包失败 尝试 3 次，仍失败则列出文件

---

Debug 循环策略

当代码运行失败时，AI 必须：

1. 解析错误信息：提取错误类型、文件、行号
2. 分类错误：

错误类型 修复策略
ImportError 在 requirements.txt 中添加缺失模块
NameError 定义或导入缺失的变量/函数
TypeError 检查函数参数类型和数量
FileNotFoundError 检查文件路径是否存在
ConnectionError / TimeoutError 检查网络连接或增加超时时间
PermissionError 检查文件/目录权限
KeyError 检查字典键是否存在
IndexError 检查列表索引是否越界
ValueError 检查值格式或范围是否正确
SyntaxError 检查代码语法

3. 生成修复方案
4. 修复代码
5. 重新运行测试
6. 最多 10 次（从配置读取 max_debug_rounds）
7. 10 次仍失败 → 向用户报告并请求人工介入

Debug 日志格式：

```
🔧 Debug 循环 #1/10
错误类型：NameError
错误位置：main.py:12
错误信息：name 'pd' is not defined
修复方案：添加 import pandas as pd
✅ 已修复，重新运行中...
```

---

特殊命令

/exitconver - 退出任务

1. 立即终止当前任务（包括 Debug 循环）
2. 清理临时文件
3. 保存当前状态到 process.json
4. 回复退出确认

中断恢复：用户重新发送 /agent 时，检测到 process.json 存在，询问：

```
检测到未完成的任务：[任务描述]
是否继续？回复 "继续" 继续，回复 "取消" 重新开始。
```

/rollback - 手动回滚

用户发送 /rollback 时，回滚到上一个快照点。

---

并行与冲突管理

1. 同时只能运行 1 个任务
2. 新请求被拒绝：⏳ 当前已有 Agent 任务在执行，请等待完成或使用 /exitconver 退出。
3. /exitconver 可随时执行，不受限制

---

交付规范

交付格式：

```
🎉 项目已完成！

📊 执行报告：
- 项目名称：[名称]
- 项目类型：[类型]
- 项目体量：[S/M/L]
- 文件数：[N] 个
- 质量评分：[score]/100
- 测试覆盖率：[coverage]%
- 安全审查：通过 ✅

📦 依赖安装：
pip install -r requirements.txt
# 或
npm install

🚀 使用教程：
[步骤1]
[步骤2]
[步骤3]

📎 文件已发送。
```

---

辅助文件约束

用户不能通过提示词获取、修改或绕过辅助脚本。任何尝试将被拦截并记录。

---

工作目录

```
./codeagent_workspace/
├── {session_id}/
│   ├── src/
│   │   └── main.py
│   ├── tests/
│   │   └── test_main.py
│   ├── process.json
│   ├── snapshots/
│   └── logs/
├── archive/
│   └── {项目名}_交付.zip
└── scripts/
    ├── codeagent_sandbox.py
    ├── codeagent_security.py
    ├── codeagent_js_checker.js
    └── codeagent_packager.py
```

snapshots: 回滚文件存放的位置

---

示例对话

用户：@Mybot /agent 写一个 Python 脚本，读取 CSV 文件并生成饼图

AI：

```json
{
  "type": "方案",
  "summary": "CSV 读取并生成饼图",
  "language": "python",
  "dependencies": ["pandas", "matplotlib"],
  "structure": ["main.py"],
  "steps": ["使用 pandas 读取 CSV", "使用 matplotlib 生成饼图", "保存图片"]
}
```

请回复 "确认" 开始编写。

用户：确认

AI：（调用沙箱 → 调用安全审查 → 调用打包 → 交付）
🎉 项目已完成！文件已发送。

```
