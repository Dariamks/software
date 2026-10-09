# 单笔划扣工具：恢复结果

已从 `单笔划扣工具(3).exe` 静态提取出 PyInstaller 内容。入口字节码为 `gui.pyc`，其 Python 版本是 **3.14**。完整反汇编在 `gui_disassembly.txt`，核心网络类的可读重建版本在 `single_payment_processor_recovered.py`。

## 能恢复的内容

- PyInstaller 内嵌的 `gui.pyc` 已完整保留。
- 可确认原程序使用 Tkinter、requests、JSON、线程池，并包含登录窗口与主窗口。
- 已重建单笔划扣查询、详情、提交、复核、统计和 JWT 有效期检查逻辑。

## 不能保证完全一致的部分

Python 打包后通常不会保存原始 `.py`、注释、工程目录和部分变量命名。原入口的 Tkinter 控件布局和线程调度仍需依据 `gui_disassembly.txt` 逐段整理；这份文件是字节码级证据，不是原始源码。

程序中包含服务地址和固定的 `reviewUserId`。如果这些值仍有效，重建前应先确认服务端授权和账号权限。

## macOS 启动

不要使用系统自带的 Python 3.9 启动，因为它的 Tk 图形库和当前 macOS 版本不兼容。双击 `run_macos.command`，脚本会使用 Homebrew Python 3.13/Tk，并在项目目录创建 `.venv`。

首次需要：

```bash
brew install python@3.13 python-tk@3.13
```

## XLSX 批量流程

`batch_single_payment.py` 按门户中的顺序处理表格：查询待划扣记录、读取贷款详情、提交单笔划扣、查询“复核中”记录、确认复核。输入表格首行必须包含“借据号（合同编号）”和“身份证号码”。当前提供的表格实际包含 1,101 条非空数据行。

默认不调用接口。未提供 Token 时只生成 `plan_only` 结果，便于先检查表格；提供 Token 后会执行查询和详情读取，但仍不会提交划扣。只有显式加上 `--execute` 才会提交并确认复核：

```bash
./.venv/bin/python batch_single_payment.py \
  --xlsx "/path/to/新建 XLSX 工作表.xlsx" \
  --token "$FUJFU_TOKEN" \
  --limit 5 \
  --output single_payment_results.jsonl

# 经过授权、确认在远程电脑执行时才使用：
./.venv/bin/python batch_single_payment.py \
  --xlsx "/path/to/新建 XLSX 工作表.xlsx" \
  --token "$FUJFU_TOKEN" \
  --execute \
  --output single_payment_results.jsonl
```

脚本会调用 `getReviewUserList`，按 `--review-job-no`（默认 `S80118`）解析页面选择的复核人；也可用 `FUJFU_REVIEW_USER_ID` 直接指定复核人 ID。复核查询会从 JWT 的 `sub` 读取当前提交用户。脚本使用标准库读取 XLSX，不要求在本地安装 `openpyxl`。

如果银行卡未签约，接口会在确认复核后返回 `transStatus=处理失败` 和 `errorMsg=当前银行卡未签约，请更换银行卡后再试！`，这属于业务结果，脚本会原样写入 JSONL，不会把它误报成成功。
