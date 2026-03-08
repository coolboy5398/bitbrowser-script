# BAT 启动脚本编写规则

## 适用场景

当需要为新的 Python 脚本创建一个可双击执行的 Windows 批处理启动器时，统一参考 [`runAug.bat`](runAug.bat) 的结构编写。

## 标准结构

批处理应包含以下固定流程：

1. `@echo off`
2. 输出标题分隔线
3. 提示正在通过 PowerShell 执行
4. 使用 `powershell -ExecutionPolicy Bypass -Command "..."` 包裹实际执行逻辑
5. 先进入脚本所在目录或目标子目录
6. 执行 `conda activate base`
7. 执行 `python --version`
8. 执行目标 Python 脚本
9. 输出完成提示
10. 使用 `Read-Host` 等待用户回车退出

参考入口见 [`runAug.bat`](runAug.bat) 与 [`runCleanCodex.bat`](runCleanCodex.bat)。

## 路径规则

### 1. 根目录脚本

如果目标脚本就在项目根目录，直接使用：

- `python augment_register.py`
- `python windsurf_register.py`

对应示例：[`runAug.bat`](runAug.bat)、[`runWindsurf.bat`](runWindsurf.bat)

### 2. 子目录脚本

如果目标脚本位于子目录，不要直接在 PowerShell 命令里使用类似：

- `python clean_codex/clean_codex_accounts.py`

优先改为：

- 先 `cd '%~dp0子目录名'`
- 再执行 `python 脚本名.py`

示例：[`runCleanCodex.bat`](runCleanCodex.bat)

这样做的好处：

1. 避免批处理、`cmd`、PowerShell 多层嵌套时的路径解析异常
2. 避免相对路径配置文件读取错误
3. 让脚本内部默认相对路径更稳定

例如 [`clean_codex/clean_codex_accounts.py`](clean_codex/clean_codex_accounts.py) 中的 [`DEFAULT_CONFIG_PATH`](clean_codex/clean_codex_accounts.py:19) 默认为 `config.json`，因此应在 [`clean_codex`](clean_codex) 目录下执行。

## 编码与换行规则

### 1. 换行必须使用 CRLF

Windows 批处理文件必须优先使用 `CRLF` 换行。

原因：

- [`runAug.bat`](runAug.bat) 可正常执行的一个关键点就是使用了 Windows 标准换行
- 如果写成仅 `LF`，可能在 `cmd` 下被错误解析，出现整行命令被拆坏、`Command 不是内部或外部命令` 等问题

### 2. 编码优先兼容 cmd

如果批处理包含中文提示，写入文件时必须考虑 `cmd` 的兼容性。

建议优先级：

1. 与现有项目保持一致，使用兼容 Windows `cmd` 的编码方式
2. 若无法确保编码一致，宁可使用英文提示，也不要让批处理无法执行

## 创建步骤

创建新的 BAT 启动脚本时，按以下顺序执行：

1. 先查看现有模板 [`runAug.bat`](runAug.bat)
2. 判断目标 Python 脚本在根目录还是子目录
3. 如果在子目录，确认是否存在相对路径配置依赖
4. 生成 BAT 文件
5. 确保文件为 Windows 可兼容编码
6. 确保换行为 `CRLF`
7. 实测执行 BAT 文件
8. 观察是否成功进入目标 Python 脚本，而不是只检查批处理是否被创建

## 测试标准

一个 BAT 启动脚本创建完成后，至少要验证以下几点：

1. `cmd /c` 可正常启动 BAT
2. 可以成功进入 PowerShell
3. `conda activate base` 可执行
4. `python --version` 能输出版本
5. 目标脚本确实开始运行
6. 如果目标脚本是交互式脚本，出现输入菜单或输入提示即可视为启动成功

例如 [`clean_codex/clean_codex_accounts.py`](clean_codex/clean_codex_accounts.py) 会进入 [`choose_mode()`](clean_codex/clean_codex_accounts.py:108) 菜单，因此测试中出现菜单并在无输入环境下报 `EOFError`，应判定为“启动成功但测试环境无交互输入”，而不是批处理失败。

## 推荐模板

```bat
@echo off
echo ========================================
echo 比特浏览器自动化脚本启动器
echo ========================================
echo.
echo 正在通过 PowerShell 运行脚本...
echo.
powershell -ExecutionPolicy Bypass -Command "cd '%~dp0目标目录'; Write-Host '激活 Conda 环境...' -ForegroundColor Cyan; conda activate base; Write-Host ''; Write-Host '检查 Python 版本...' -ForegroundColor Cyan; python --version; Write-Host ''; Write-Host '运行 Python 脚本...' -ForegroundColor Cyan; Write-Host ''; python 目标脚本.py; Write-Host ''; Write-Host '脚本执行完毕!' -ForegroundColor Green; Write-Host ''; Read-Host '按回车键退出'"
```

如果目标脚本位于根目录，则把 `cd '%~dp0目标目录'` 改为 `cd '%~dp0'`。

## 本项目已验证示例

- [`runAug.bat`](runAug.bat)
- [`runWindsurf.bat`](runWindsurf.bat)
- [`runCleanCodex.bat`](runCleanCodex.bat)
