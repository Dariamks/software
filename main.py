"""批量单笔划扣 GUI。合同号支持从文本中逐行粘贴。"""
from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from batch_single_payment import InputRow, process_one, resolve_review_user_id
from single_payment_processor_recovered import SinglePaymentProcessor, ReviewerListError
from reviewers import reviewer_options
from result_display import format_result
from parallel_batch import run_parallel
from access_control import AccessError, LicenseExpired, LocalLicense


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("单笔划扣工具（批量版）")
        self.geometry("820x620")
        self.minsize(700, 500)
        self.processor = SinglePaymentProcessor(base_url=os.getenv("FUJFU_BASE_URL"))
        self.stop_event = threading.Event()
        self.license = LocalLicense()
        self.access_valid = False
        self.running = False
        self._build_login()

    def _build_login(self):
        self.geometry("460x430")
        self.minsize(440, 420)
        self.configure(bg="#f4f7fb")
        self.login_panel = tk.Frame(self, bg="#f4f7fb", padx=36, pady=26)
        self.login_panel.pack(fill="both", expand=True)
        tk.Label(self.login_panel, text="登录单笔划扣工具", bg="#f4f7fb",
                 fg="#1f3a5f", font=("Arial", 18, "bold")).pack(anchor="w", pady=(0, 16))
        tk.Label(self.login_panel, text="账号", bg="#f4f7fb").pack(anchor="w")
        self.login_account = ttk.Entry(self.login_panel)
        self.login_account.pack(fill="x", pady=(4, 12))
        tk.Label(self.login_panel, text="密码", bg="#f4f7fb").pack(anchor="w")
        self.login_password = ttk.Entry(self.login_panel, show="*")
        self.login_password.pack(fill="x", pady=(4, 16))
        ttk.Button(self.login_panel, text="登录", command=self._login).pack(fill="x")
        ttk.Button(self.login_panel, text="激活码续期 / 永久解锁", command=self._activation_dialog).pack(fill="x", pady=(10, 0))
        tk.Label(self.login_panel, text="首次成功登录起可使用 24 小时，重启不会重置。",
                 bg="#f4f7fb", fg="#718096", wraplength=360).pack(pady=16)
        self.login_password.bind("<Return>", lambda event: self._login())
        self.login_account.focus_set()

    def _login(self):
        try:
            self.license.login(self.login_account.get(), self.login_password.get())
        except LicenseExpired as exc:
            self._activation_dialog(str(exc))
            return
        except AccessError as exc:
            messagebox.showerror("无法登录", str(exc))
            return
        self.login_password.delete(0, "end")
        self.login_panel.destroy()
        self.access_valid = True
        self.geometry("820x620")
        self.minsize(700, 500)
        self._build()
        self.log(self._license_label())
        self.after(1000, self._watch_access)

    def _check_access(self):
        try:
            self.license.check()
        except AccessError as exc:
            self.access_valid = False
            self.stop_event.set()
            self._set_running(self.running)
            self.log(str(exc) + "；不再启动新合同，已开始的交易处理完毕后停止。")
            if isinstance(exc, LicenseExpired):
                self._activation_dialog(str(exc))
            else:
                messagebox.showerror("使用期限", str(exc))
            return False
        return True

    def _watch_access(self):
        if self._check_access():
            self.after(1000, self._watch_access)

    def _license_label(self):
        if self.license.permanent:
            return "授权状态：永久解锁"
        return "使用期限至：" + datetime.fromtimestamp(self.license.expires_at).strftime("%Y-%m-%d %H:%M:%S")

    def _activation_dialog(self, notice=""):
        existing = getattr(self, 'activation_window', None)
        if existing is not None and existing.winfo_exists():
            if notice:
                self.activation_notice.set(notice)
            existing.lift()
            self.activation_input.focus_set()
            return
        dialog = tk.Toplevel(self)
        self.activation_window = dialog
        dialog.title("激活码续期")
        dialog.geometry("580x430")
        dialog.minsize(560, 410)
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        self.activation_notice = tk.StringVar(value=notice or "可续期一天或永久解锁，到期后也可以在这里激活。")
        ttk.Label(frame, textvariable=self.activation_notice, foreground="#b45309",
                  wraplength=500).pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="向管理员获取通用激活码，无需提供机器码。", wraplength=500).pack(anchor="w")
        ttk.Label(frame, text="同一码可用于多台电脑，在每台电脑上仅可激活一次。", wraplength=500).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, text="粘贴激活码").pack(anchor="w", pady=(16, 4))
        code = tk.Text(frame, height=4, wrap="char")
        self.activation_input = code
        code.pack(fill="both", expand=True)
        def redeem():
            try:
                self.license.redeem(code.get("1.0", "end").strip())
            except AccessError as exc:
                messagebox.showerror("激活失败", str(exc), parent=dialog)
                return
            if hasattr(self, 'execute_btn'):
                was_valid = self.access_valid
                self.access_valid = True
                self._set_running(self.running)
                self.log(self._license_label())
                if not was_valid:
                    self.after(1000, self._watch_access)
            messagebox.showinfo("激活成功", self._license_label(), parent=dialog)
            dialog.destroy()
        self.activation_submit = ttk.Button(frame, text="确认激活", command=redeem)
        self.activation_submit.pack(pady=(12, 0))
        dialog.update_idletasks()
        dialog.minsize(max(560, frame.winfo_reqwidth()), max(410, frame.winfo_reqheight()))
        code.focus_set()

    def _build(self):
        self.configure(bg="#f4f7fb")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Body.TLabel", background="#f4f7fb", foreground="#22324a", font=("Arial", 10))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#718096", font=("Arial", 9))
        style.configure("Card.TFrame", background="#ffffff")

        header = tk.Frame(self, bg="#1f3a5f", height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Button(header, text="激活码续期", command=self._activation_dialog).pack(side="right", padx=20)
        tk.Label(header, text="单笔划扣工具", bg="#1f3a5f", fg="white",
                 font=("Arial", 19, "bold")).pack(anchor="w", padx=24, pady=(13, 0))
        tk.Label(header, text="批量查询、划扣与复核", bg="#1f3a5f", fg="#c8d6e8",
                 font=("Arial", 10)).pack(anchor="w", padx=26)

        viewport = ttk.Frame(self)
        viewport.pack(fill="both", expand=True)
        self.page = tk.Canvas(viewport, bg="#f4f7fb", highlightthickness=0)
        page_scroll = ttk.Scrollbar(viewport, orient="vertical", command=self.page.yview)
        page_scroll.pack(side="right", fill="y")
        self.page.pack(side="left", fill="both", expand=True)
        self.page.configure(yscrollcommand=page_scroll.set)
        root = tk.Frame(self.page, bg="#f4f7fb", padx=22, pady=18)
        content = self.page.create_window((0, 0), window=root, anchor="nw")

        def resize_page(event=None):
            self.page.itemconfigure(content, width=self.page.winfo_width(),
                                    height=max(root.winfo_reqheight(), self.page.winfo_height()))
            self.page.configure(scrollregion=self.page.bbox("all"))

        root.bind("<Configure>", resize_page)
        self.page.bind("<Configure>", resize_page)
        root.columnconfigure(0, weight=1)
        # 操作栏必须保留最小高度，剩余空间交给日志区域。
        root.rowconfigure(2, weight=0, minsize=58)

        auth = tk.Frame(root, bg="#ffffff", highlightbackground="#e1e8f0", highlightthickness=1)
        auth.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        auth.columnconfigure(1, weight=1)
        tk.Label(auth, text="连接配置", bg="#ffffff", fg="#1f3a5f", font=("Arial", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(13, 8))
        tk.Label(auth, text="Token", bg="#ffffff", fg="#516176", font=("Arial", 10)).grid(
            row=1, column=0, sticky="w", padx=(16, 8), pady=(0, 14))
        self.token = ttk.Entry(auth, show="*")
        self.token.grid(row=1, column=1, sticky="ew", pady=(0, 14))
        tk.Button(auth, text="验证并加载人员", command=self.load_reviewers, bg="#e7f0fb", fg="#1f5d98",
                  activebackground="#d6e7f8", relief="flat", padx=14, pady=4).grid(
            row=1, column=2, padx=(10, 16), pady=(0, 14))
        tk.Label(auth, text="复核人", bg="#ffffff", fg="#516176", font=("Arial", 10)).grid(
            row=2, column=0, sticky="w", padx=(16, 8), pady=(0, 14))
        self.review_job_no = ttk.Combobox(auth, width=28, state="readonly")
        self.reviewer_loading = False
        self.review_job_no.grid(row=2, column=1, sticky="w", pady=(0, 14))
        self.refresh_reviewers = ttk.Button(auth, text="刷新复核人", command=self.load_reviewers)
        self.refresh_reviewers.grid(row=2, column=2, padx=(10, 16), pady=(0, 14))
        concurrency = tk.Frame(auth, bg="#ffffff")
        concurrency.grid(row=3, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 14))
        tk.Label(concurrency, text="并行合同数", bg="#ffffff", fg="#516176").pack(side="left", padx=(0, 12))
        self.workers = ttk.Combobox(concurrency, values=(2, 3, 4, 5, 6), state="readonly", width=5)
        self.workers.set("2")
        self.workers.pack(side="left")
        tk.Label(concurrency, text="个合同同时处理", bg="#ffffff", fg="#718096").pack(side="left", padx=10)

        work = tk.Frame(root, bg="#ffffff", highlightbackground="#e1e8f0", highlightthickness=1)
        work.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        work.columnconfigure(0, weight=1)
        tk.Label(work, text="合同编号", bg="#ffffff", fg="#1f3a5f", font=("Arial", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(13, 2))
        tk.Label(work, text="每行一个，可直接粘贴多条；系统会自动去重", bg="#ffffff", fg="#718096",
                 font=("Arial", 9)).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        self.contracts = tk.Text(work, height=7, undo=True, relief="flat", bd=0,
                                 bg="#f7f9fc", fg="#22324a", insertbackground="#1f5d98",
                                 font=("Consolas", 11), padx=10, pady=8)
        self.contracts.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        contracts_scroll = ttk.Scrollbar(work, orient="vertical", command=self.contracts.yview)
        contracts_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 14))
        self.contracts.configure(yscrollcommand=contracts_scroll.set)

        actions = tk.Frame(root, bg="#f4f7fb")
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.query_btn = tk.Button(actions, text="仅查询 / 预览", command=lambda: self.start(False),
                                   bg="#2f80c9", fg="white", activebackground="#246aa8",
                                   relief="flat", padx=18, pady=8, font=("Arial", 10, "bold"))
        self.query_btn.pack(side="left", padx=(0, 10))
        self.execute_btn = tk.Button(actions, text="执行划扣并复核", command=lambda: self.start(True),
                                     bg="#2da56a", fg="white", activebackground="#238451",
                                     relief="flat", padx=18, pady=8, font=("Arial", 10, "bold"))
        self.execute_btn.pack(side="left", padx=(0, 10))
        self.stop_btn = tk.Button(actions, text="停止", command=self.stop, state=tk.DISABLED,
                                  bg="#ffffff", fg="#c24b4b", activebackground="#fbecec",
                                  relief="flat", padx=18, pady=8, font=("Arial", 10))
        self.stop_btn.pack(side="left")
        self.count_label = tk.Label(actions, text="等待开始", bg="#f4f7fb", fg="#718096", font=("Arial", 10))
        self.count_label.pack(side="right", padx=8)

        log_card = tk.Frame(root, bg="#ffffff", highlightbackground="#e1e8f0", highlightthickness=1)
        log_card.grid(row=3, column=0, sticky="nsew")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)
        tk.Label(log_card, text="处理日志", bg="#ffffff", fg="#1f3a5f", font=("Arial", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(11, 7))
        self.clear_log_btn = tk.Button(
            log_card, text="清空日志", command=self.clear_log,
            bg="#e7f0fb", fg="#1f5d98", activebackground="#d6e7f8",
            relief="flat", padx=12, pady=4)
        self.clear_log_btn.grid(row=0, column=0, sticky="e", padx=16, pady=(11, 7))
        self.status = tk.Text(log_card, height=10, state=tk.DISABLED, relief="flat", bd=0,
                              bg="#fbfcfe", fg="#334155", font=("Consolas", 9), padx=10, pady=8)
        self.status.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        log_scroll = ttk.Scrollbar(log_card, orient="vertical", command=self.status.yview)
        log_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 14))
        self.status.configure(yscrollcommand=log_scroll.set, wrap="word")
        root.rowconfigure(3, weight=1)
        self._bind_scroll(self)

    def _bind_scroll(self, widget):
        # Widget bindings run before Text's class binding, preventing double scrolling.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self._scroll, add="+")
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _scroll(self, event):
        if event.num in (4, 5):
            units = -3 if event.num == 4 else 3
        elif event.delta:
            units = -max(1, abs(int(event.delta)) // 120) if event.delta > 0 else max(1, abs(int(event.delta)) // 120)
        else:
            return "break"
        target = event.widget
        if target in (self.contracts, self.status):
            first, last = target.yview()
            if (units < 0 and first > 0) or (units > 0 and last < 1):
                target.yview_scroll(units, "units")
                return "break"
        self.page.yview_scroll(units, "units")
        return "break"

    def log(self, text):
        self.after(0, self._append_log, text)

    def _append_log(self, text):
        self.status.configure(state=tk.NORMAL)
        self.status.insert("end", text + "\n")
        self.status.see("end")
        self.status.configure(state=tk.DISABLED)

    def clear_log(self):
        self.status.configure(state=tk.NORMAL)
        self.status.delete("1.0", "end")
        self.status.configure(state=tk.DISABLED)

    def load_reviewers(self):
        if self.running or self.reviewer_loading or not self.set_token():
            return
        token = self.token.get().strip()
        previous = self.review_job_no.get()
        self.review_job_no.set('')
        self.review_job_no.configure(values=())
        self.reviewer_loading = True
        self.refresh_reviewers.configure(state='disabled')
        self.log('正在加载复核人列表…')

        def load():
            processor = SinglePaymentProcessor(base_url=os.getenv('FUJFU_BASE_URL'))
            try:
                processor.set_token(token)
                users = processor.get_review_user_list()
                options = reviewer_options(users)
                if not options:
                    error = '复核人列表为空或字段尚未适配，请提供 getReviewUserList 的 Response 以核对'
                else:
                    error = ''
            except ReviewerListError as exc:
                options, error = [], str(exc)
            except Exception:
                options, error = [], '加载复核人失败，请检查接口返回'
            finally:
                processor.session.close()
            self.after(0, finish, options, error)

        def finish(options, error):
            self.reviewer_loading = False
            self.refresh_reviewers.configure(state='normal')
            if token != self.token.get().strip():
                self.log('Token 已更改，请重新加载复核人')
                return
            if error:
                self.log(error)
                return
            names = list(dict.fromkeys(label for label, _, _ in options))
            self.review_job_no.configure(values=names)
            if previous in names:
                self.review_job_no.set(previous)
            self.log(f'已加载 {len(names)} 位复核人，请按页面显示的工号和姓名选择')

        threading.Thread(target=load, daemon=True).start()

    def set_token(self):
        token = self.token.get().strip()
        if not token:
            messagebox.showwarning("提示", "请输入 Token")
            return False
        valid, text = self.processor.check_token_expiry(token)
        self.log(f"Token检查：{text}")
        if valid is False:
            messagebox.showerror("Token 无效", text)
            return False
        self.processor.set_token(token)
        return True

    def _items(self):
        raw = self.contracts.get("1.0", "end")
        values = re.split(r"[\s,，;；]+", raw.strip())
        result, seen = [], set()
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    def start(self, execute):
        if self.reviewer_loading:
            messagebox.showinfo('请稍候', '正在加载复核人列表')
            return
        if not self._check_access():
            return
        if not self.set_token():
            return
        contracts = self._items()
        if not contracts:
            messagebox.showwarning("提示", "请粘贴至少一个合同编号")
            return
        if execute and not self.review_job_no.get():
            messagebox.showwarning('请选择复核人', '点击“验证并加载人员”，然后从下拉框选择页面显示的复核人。')
            return
        if execute and not messagebox.askyesno(
            "确认执行", f"即将提交并复核 {len(contracts)} 个合同的划扣交易，确定继续吗？"
        ):
            return
        self.count_label.configure(text=f"已读取 {len(contracts)} 条合同")
        self.stop_event.clear()
        self._set_running(True)
        settings = (self.token.get().strip(), self.review_job_no.get().strip(), int(self.workers.get()))
        threading.Thread(target=self._run, args=(contracts, execute, settings), daemon=True).start()

    def _run(self, contracts, execute, settings):
        token, job_no, workers = settings

        def factory():
            self.license.check()
            processor = SinglePaymentProcessor(base_url=os.getenv("FUJFU_BASE_URL"))
            processor.set_token(token)
            return processor

        try:
            reviewer_id = ""
            if execute:
                processor = factory()
                try:
                    reviewer_id = resolve_review_user_id(processor.get_review_user_list(), job_no)
                finally:
                    processor.session.close()
                if not reviewer_id:
                    self.log(f"找不到复核人：{job_no}")
                    return
            self.log(f"开始处理 {len(contracts)} 个合同，并行数：{workers}")
            completed = 0

            def report(result):
                nonlocal completed
                completed += 1
                self.log(format_result(result))
                self.after(0, lambda n=completed: self.count_label.configure(text=f"已处理 {n}/{len(contracts)}"))

            run_parallel(contracts, workers, self.stop_event, factory, execute, reviewer_id, report)
            self.log("已停止，运行中的合同已处理完毕" if self.stop_event.is_set() else "本批次处理结束")
        except ReviewerListError as exc:
            self.log(str(exc))
        except Exception:
            self.log("批次异常中止，请核实已提交交易状态后再操作")
        finally:
            self.after(0, lambda: self._set_running(False))

    def stop(self):
        self.stop_event.set()
        self.log("正在停止：不再启动新合同，已开始的合同将完成当前划扣及复核流程")

    def _set_running(self, running):
        self.running = running
        state = tk.DISABLED if running or not self.access_valid else tk.NORMAL
        self.query_btn.configure(state=state)
        self.execute_btn.configure(state=state)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.workers.configure(state="disabled" if running else "readonly")
        self.review_job_no.configure(state="disabled" if running else "readonly")
        self.refresh_reviewers.configure(state="disabled" if running or self.reviewer_loading else "normal")


if __name__ == "__main__":
    App().mainloop()
