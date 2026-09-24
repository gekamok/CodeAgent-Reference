#!/usr/bin/env node
/**
 * CodeAgent JavaScript/TypeScript 代码检查器
 * 路径：./scripts/codeagent_js_checker.js
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class JavaScriptChecker {
    constructor() {
        this.tempDir = path.join(os.tmpdir(), 'codeagent_js_check');
        this.eslintAvailable = this._checkCommand('eslint');
        this.tscAvailable = this._checkCommand('tsc');
        this.results = {
            issues: [],
            passed: true,
            quality_score: 0,
            summary: '',
            eslint: { issues: [], error: null },
            typescript: { issues: [], error: null },
            security: { issues: [], risk_level: 'safe' },
            quality: { score: 100, details: {}, issues: [] }
        };
    }

    _checkCommand(cmd) {
        try {
            execSync(`which ${cmd}`, { stdio: 'ignore' });
            return true;
        } catch {
            return false;
        }
    }

    _detectLanguage(code) {
        const tsPatterns = [
            /:\s*(string|number|boolean|void|any|unknown|never|object)/,
            /interface\s+\w+\s*\{/,
            /type\s+\w+\s*=\s*/,
            /as\s+(string|number|boolean|any|unknown)/,
            /<[A-Z]\w+>/,
            /export\s+(interface|type)\s+/
        ];
        
        for (const pattern of tsPatterns) {
            if (pattern.test(code)) {
                return 'typescript';
            }
        }
        return 'javascript';
    }

    _getFileExtension(language) {
        return language === 'typescript' ? '.ts' : '.js';
    }

    _setupTempDir(code, language) {
        if (!fs.existsSync(this.tempDir)) {
            fs.mkdirSync(this.tempDir, { recursive: true });
        }
        
        const ext = this._getFileExtension(language);
        const filePath = path.join(this.tempDir, `main${ext}`);
        fs.writeFileSync(filePath, code, 'utf-8');
        
        if (language === 'typescript') {
            const tsConfig = {
                compilerOptions: {
                    target: 'ES2020',
                    module: 'ESNext',
                    strict: true,
                    esModuleInterop: true,
                    skipLibCheck: true,
                    forceConsistentCasingInFileNames: true,
                    noImplicitAny: true,
                    strictNullChecks: true,
                    strictFunctionTypes: true,
                    strictBindCallApply: true,
                    strictPropertyInitialization: true,
                    noImplicitThis: true,
                    alwaysStrict: true,
                    noUnusedLocals: true,
                    noUnusedParameters: true,
                    noImplicitReturns: true,
                    noFallthroughCasesInSwitch: true,
                    moduleResolution: 'node'
                },
                include: ['*.ts']
            };
            fs.writeFileSync(
                path.join(this.tempDir, 'tsconfig.json'),
                JSON.stringify(tsConfig, null, 2),
                'utf-8'
            );
        }
        
        return filePath;
    }

    _cleanup() {
        if (fs.existsSync(this.tempDir)) {
            fs.rmSync(this.tempDir, { recursive: true, force: true });
        }
    }

    _runESLint(filePath) {
        const result = { available: this.eslintAvailable, issues: [], error: null };
        
        if (!this.eslintAvailable) {
            result.error = 'ESLint 未安装，请运行: npm install -g eslint';
            return result;
        }

        try {
            const output = execSync(
                `eslint ${filePath} --format json --env es2020,node`,
                { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
            );
            
            if (output.trim()) {
                const data = JSON.parse(output);
                for (const file of data) {
                    for (const msg of file.messages) {
                        result.issues.push({
                            line: msg.line || 0,
                            column: msg.column || 0,
                            severity: msg.severity === 2 ? 'error' : 'warning',
                            message: msg.message,
                            ruleId: msg.ruleId || 'unknown',
                            suggestion: this._getEslintSuggestion(msg.ruleId)
                        });
                    }
                }
            }
        } catch (error) {
            try {
                // ESLint 返回非0时，stdout 中仍有 JSON
                if (error.stdout && error.stdout.trim()) {
                    const data = JSON.parse(error.stdout);
                    for (const file of data) {
                        for (const msg of file.messages) {
                            result.issues.push({
                                line: msg.line || 0,
                                column: msg.column || 0,
                                severity: msg.severity === 2 ? 'error' : 'warning',
                                message: msg.message,
                                ruleId: msg.ruleId || 'unknown',
                                suggestion: this._getEslintSuggestion(msg.ruleId)
                            });
                        }
                    }
                } else {
                    result.error = error.stderr || 'ESLint 执行失败';
                }
            } catch (parseError) {
                result.error = 'ESLint 输出解析失败';
            }
        }
        
        return result;
    }

    _getEslintSuggestion(ruleId) {
        const suggestions = {
            'no-unused-vars': '删除未使用的变量或添加下划线前缀',
            'no-undef': '确保变量已定义或正确导入',
            'no-var': '使用 let 或 const 替代 var',
            'prefer-const': '变量未重新赋值时使用 const',
            'eqeqeq': '使用 === 替代 ==',
            'no-extra-semi': '删除多余的分号',
            'semi': '添加或删除分号',
            'quotes': '统一使用单引号或双引号',
            'indent': '检查缩进是否正确',
            'no-multiple-empty-lines': '删除多余的空行',
            'no-trailing-spaces': '删除行尾空格',
            'comma-dangle': '检查逗号放置规则',
            'arrow-parens': '箭头函数参数括号检查',
            'no-console': '移除 console.log 或替换为日志系统'
        };
        return suggestions[ruleId] || '请参考 ESLint 文档修复';
    }

    _runTypeScript(filePath, language) {
        const result = { available: true, issues: [], error: null };
        
        if (language !== 'typescript') {
            return result;
        }

        if (!this.tscAvailable) {
            result.available = false;
            result.error = 'TypeScript 未安装，请运行: npm install -g typescript';
            return result;
        }

        try {
            execSync(`tsc --noEmit --strict ${filePath}`, {
                encoding: 'utf-8',
                stdio: ['pipe', 'pipe', 'pipe']
            });
        } catch (error) {
            const output = (error.stdout || '') + (error.stderr || '');
            const lines = output.split('\n');
            
            for (const line of lines) {
                const match = line.match(/^(.+)\((\d+),(\d+)\):\s*error\s+TS(\d+):\s*(.+)$/);
                if (match) {
                    const code = `TS${match[4]}`;
                    result.issues.push({
                        line: parseInt(match[2]),
                        column: parseInt(match[3]),
                        code: code,
                        message: match[5],
                        suggestion: this._getTsSuggestion(code)
                    });
                }
            }
            
            if (result.issues.length === 0 && output.trim()) {
                result.error = output.trim();
            }
        }
        
        return result;
    }

    _getTsSuggestion(code) {
        const suggestions = {
            'TS2322': '检查赋值类型是否匹配声明的类型',
            'TS2345': '检查函数参数类型是否正确',
            'TS2339': '检查对象是否包含该属性',
            'TS2304': '检查变量或类型是否已定义/导入',
            'TS2352': '使用类型断言或检查类型转换',
            'TS2451': '检查模块导出是否已导入',
            'TS7006': '为函数参数添加类型注解',
            'TS7031': '为类成员添加类型注解',
            'TS7053': '检查索引签名是否正确',
            'TS2349': '检查函数调用参数是否正确',
            'TS2365': '检查运算符操作数类型是否正确',
            'TS2531': '检查对象是否可能为 null 或 undefined',
            'TS2532': '使用可选链操作符或检查 null/undefined',
            'TS2533': '检查对象属性是否可能为 undefined',
            'TS2564': '检查类属性是否已初始化'
        };
        return suggestions[code] || `请检查 TypeScript 错误: ${code}`;
    }

    _runSecurityScan(code) {
        const issues = [];
        const patterns = [
            { pattern: /eval\s*\(/g, level: 'critical', msg: '使用 eval 执行动态代码，存在代码注入风险' },
            { pattern: /Function\s*\(/g, level: 'critical', msg: '使用 Function 构造函数，存在代码注入风险' },
            { pattern: /child_process\.exec/g, level: 'high', msg: '使用 child_process.exec 执行系统命令' },
            { pattern: /child_process\.spawn/g, level: 'high', msg: '使用 child_process.spawn 执行系统命令' },
            { pattern: /fs\.writeFile.*['"]\/.*['"]/g, level: 'high', msg: '写入系统目录文件，可能存在权限风险' },
            { pattern: /fs\.unlink/g, level: 'high', msg: '删除文件操作' },
            { pattern: /fs\.rmdir/g, level: 'high', msg: '删除目录操作' },
            { pattern: /process\.exit/g, level: 'medium', msg: '进程退出操作' },
            { pattern: /http\.request/g, level: 'medium', msg: '发起 HTTP 请求' },
            { pattern: /https\.request/g, level: 'medium', msg: '发起 HTTPS 请求' },
            { pattern: /innerHTML\s*=/g, level: 'medium', msg: '直接操作 innerHTML，存在 XSS 风险' },
            { pattern: /document\.write/g, level: 'medium', msg: '使用 document.write，可能存在 XSS 风险' },
            { pattern: /setTimeout\s*\(\s*['"].*['"]\s*,\s*\d+\s*\)/g, level: 'low', msg: '使用 setTimeout 执行字符串代码' },
            { pattern: /setInterval\s*\(\s*['"].*['"]\s*,\s*\d+\s*\)/g, level: 'low', msg: '使用 setInterval 执行字符串代码' },
            { pattern: /import\s*\(\s*['"].*['"]\s*\)/g, level: 'low', msg: '动态 import，确保来源可信' }
        ];

        const lines = code.split('\n');
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            for (const p of patterns) {
                p.pattern.lastIndex = 0;
                if (p.pattern.test(line)) {
                    issues.push({
                        line: i + 1,
                        column: 0,
                        severity: p.level,
                        message: p.msg,
                        code: line.trim().substring(0, 100),
                        suggestion: '请使用安全替代方案'
                    });
                }
            }
        }

        const riskLevel = issues.some(i => i.severity === 'critical') ? 'critical' :
                         issues.some(i => i.severity === 'high') ? 'high' :
                         issues.some(i => i.severity === 'medium') ? 'medium' : 'safe';

        return { issues, risk_level: riskLevel };
    }

    _assessQuality(code) {
        let score = 100;
        const details = {};
        const issues = [];

        const lines = code.split('\n');
        const totalLines = lines.filter(l => l.trim()).length;

        if (totalLines === 0) {
            return { score: 0, details: { empty: true }, issues: ['代码为空'] };
        }

        // 注释比例
        const commentLines = lines.filter(l => l.trim().startsWith('//')).length;
        const ratio = commentLines / Math.max(1, totalLines);
        if (totalLines > 30 && ratio < 0.05) {
            score -= 10;
            issues.push('注释过少 (<5%)，建议增加注释说明');
        }
        details['comment_ratio'] = Math.round(ratio * 100);

        // 长函数检测
        let functionCount = 0;
        let longFunctions = 0;
        let inFunction = false;
        let currentFuncLines = 0;
        let braceCount = 0;

        for (const line of lines) {
            const trimmed = line.trim();
            // 检测函数开始
            if (trimmed.match(/^(function|const.*=>|async.*=>|class)/) && !trimmed.startsWith('//')) {
                functionCount++;
                inFunction = true;
                currentFuncLines = 1;
                braceCount = (trimmed.match(/{/g) || []).length - (trimmed.match(/}/g) || []).length;
            } else if (inFunction) {
                currentFuncLines++;
                braceCount += (trimmed.match(/{/g) || []).length - (trimmed.match(/}/g) || []).length;
                if (braceCount <= 0 && trimmed.includes('}')) {
                    inFunction = false;
                    if (currentFuncLines > 50) {
                        longFunctions++;
                    }
                }
            }
        }

        if (longFunctions > 0) {
            score -= Math.min(15, longFunctions * 5);
            issues.push(`有 ${longFunctions} 个函数超过50行，建议拆分`);
        }
        details['function_count'] = functionCount;
        details['long_functions'] = longFunctions;

        // 行长度
        const longLines = lines.filter(l => l.length > 120);
        if (longLines.length > 0) {
            score -= Math.min(10, longLines.length);
            issues.push(`有 ${longLines.length} 行超过120字符`);
        }
        details['long_lines'] = longLines.length;

        // 检测 var 使用
        if (/\bvar\s+/.test(code)) {
            score -= 10;
            issues.push('使用了 var，建议使用 let 或 const');
            details['used_var'] = true;
        }

        score = Math.max(0, Math.min(100, score));
        return { score, details, issues };
    }

    check(code, filePath = '', language = 'auto') {
        // 重置结果
        this.results = {
            issues: [],
            passed: true,
            quality_score: 0,
            summary: '',
            eslint: { issues: [], error: null },
            typescript: { issues: [], error: null },
            security: { issues: [], risk_level: 'safe' },
            quality: { score: 100, details: {}, issues: [] }
        };

        if (!code || !code.trim()) {
            this.results.summary = '代码为空';
            this.results.passed = false;
            return this.results;
        }

        if (language === 'auto') {
            language = this._detectLanguage(code);
        }

        let tempFilePath = null;
        try {
            tempFilePath = this._setupTempDir(code, language);

            // ESLint 检查
            const eslintResult = this._runESLint(tempFilePath);
            this.results.eslint = eslintResult;
            for (const issue of eslintResult.issues) {
                this.results.issues.push({
                    ...issue,
                    tool: 'eslint',
                    level: issue.severity === 'error' ? 'high' : 'medium'
                });
                if (issue.severity === 'error') {
                    this.results.passed = false;
                }
            }

            // TypeScript 检查
            const tsResult = this._runTypeScript(tempFilePath, language);
            this.results.typescript = tsResult;
            for (const issue of tsResult.issues) {
                this.results.issues.push({
                    ...issue,
                    tool: 'typescript',
                    level: 'high',
                    severity: 'error'
                });
                this.results.passed = false;
            }

            // 安全扫描
            const securityResult = this._runSecurityScan(code);
            this.results.security = securityResult;
            for (const issue of securityResult.issues) {
                this.results.issues.push({
                    ...issue,
                    tool: 'security',
                    level: issue.severity
                });
                if (issue.severity === 'critical' || issue.severity === 'high') {
                    this.results.passed = false;
                }
            }

            // 质量评估
            const qualityResult = this._assessQuality(code);
            this.results.quality = qualityResult;
            this.results.quality_score = qualityResult.score;
            if (qualityResult.score < 75) {
                this.results.passed = false;
            }

            // 生成摘要
            const critical = this.results.issues.filter(i => i.level === 'critical').length;
            const high = this.results.issues.filter(i => i.level === 'high').length;
            const medium = this.results.issues.filter(i => i.level === 'medium').length;
            const low = this.results.issues.filter(i => i.level === 'low').length;

            const parts = [];
            if (critical) parts.push(`${critical} 个严重问题`);
            if (high) parts.push(`${high} 个高危问题`);
            if (medium) parts.push(`${medium} 个中危问题`);
            if (low) parts.push(`${low} 个低危问题`);

            this.results.summary = parts.length ? `发现 ${parts.join(', ')}` : '代码检查通过';

        } finally {
            this._cleanup();
        }

        return this.results;
    }
}

function showHelp() {
    console.log(`
CodeAgent JavaScript/TypeScript 代码检查器

用法:
  node codeagent_javascript_checker.js [选项]

选项:
  --code <code>       直接传入代码字符串
  --code-file <path>  从文件读取代码
  --language <lang>   语言: javascript, typescript, auto (默认 auto)
  --output <path>     输出结果到 JSON 文件
  --test              运行测试
  --help              显示帮助信息

示例:
  node codeagent_javascript_checker.js --code-file ./main.js --output result.json
  node codeagent_javascript_checker.js --code "const x = 1;" --language javascript
  node codeagent_javascript_checker.js --test
`);
}

function main() {
    const args = process.argv.slice(2);
    
    if (args.includes('--help')) {
        showHelp();
        return;
    }

    const options = {
        code: '',
        codeFile: '',
        language: 'auto',
        output: '',
        test: false
    };

    for (let i = 0; i < args.length; i++) {
        switch (args[i]) {
            case '--code':
                if (i + 1 < args.length) options.code = args[++i];
                break;
            case '--code-file':
                if (i + 1 < args.length) options.codeFile = args[++i];
                break;
            case '--language':
                if (i + 1 < args.length) options.language = args[++i];
                break;
            case '--output':
                if (i + 1 < args.length) options.output = args[++i];
                break;
            case '--test':
                options.test = true;
                break;
        }
    }

    if (options.test) {
        console.log('运行 JavaScript/TypeScript 检查测试...');
        
        const testCode = `
function unsafeFunction(data) {
    eval(data);
    return eval(data);
}

function safeFunction(name) {
    return \`Hello, \${name}!\`;
}

const result = unsafeFunction('console.log("test")');
console.log(result);
`;
        const checker = new JavaScriptChecker();
        const result = checker.check(testCode, 'test.js', 'javascript');
        
        console.log(JSON.stringify(result, null, 2));
        console.log(`\n=== 摘要 ===`);
        console.log(`通过: ${result.passed}`);
        console.log(`质量评分: ${result.quality_score}/100`);
        console.log(`发现 ${result.issues.length} 个问题`);
        return;
    }

    let code = options.code;
    if (!code && options.codeFile) {
        try {
            code = fs.readFileSync(options.codeFile, 'utf-8');
        } catch (err) {
            console.error(`错误: 无法读取文件 ${options.codeFile}: ${err.message}`, process.stderr);
            process.exit(1);
        }
    }

    if (!code) {
        console.error('错误: 请提供 --code 或 --code-file', process.stderr);
        showHelp();
        process.exit(1);
    }

    const checker = new JavaScriptChecker();
    const result = checker.check(code, options.codeFile || '', options.language);

    const outputJson = JSON.stringify(result, null, 2);
    if (options.output) {
        fs.writeFileSync(options.output, outputJson, 'utf-8');
    } else {
        console.log(outputJson);
    }

    // 有严重/高危问题或质量不达标时退出码 1
    const hasCritical = result.issues.some(i => i.level === 'critical');
    const hasHigh = result.issues.some(i => i.level === 'high');
    if (!result.passed || hasCritical || hasHigh) {
        process.exit(1);
    }
}

main();
