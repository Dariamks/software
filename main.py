"""批量单笔划扣 GUI。合同号支持从文本中逐行粘贴。"""
from __future__ import annotations

import json
import os
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from batch_single_payment import InputRow, process_one, resolve_review_user_id
from single_payment_processor_recovered import SinglePaymentProcessor


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("单笔划扣工具（批量版）")
        self.geometry("820x620")
        self.minsize(700, 500)
        self.processor = SinglePaymentProcessor(base_url=os.getenv("FUJFU_BASE_URL"))
        self.stop_event = threading.Event()
        self._build()

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
        tk.Label(header, text="单笔划扣工具", bg="#1f3a5f", fg="white",
                 font=("Arial", 19, "bold")).pack(anchor="w", padx=24, pady=(13, 0))
        tk.Label(header, text="批量查询、划扣与复核", bg="#1f3a5f", fg="#c8d6e8",
                 font=("Arial", 10)).pack(anchor="w", padx=26)

        root = tk.Frame(self, bg="#f4f7fb", padx=22, pady=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        auth = tk.Frame(root, bg="#ffffff", highlightbackground="#e1e8f0", highlightthickness=1)
        auth.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        auth.columnconfigure(1, weight=1)
        tk.Label(auth, text="连接配置", bg="#ffffff", fg="#1f3a5f", font=("Arial", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(13, 8))
        tk.Label(auth, text="Token", bg="#ffffff", fg="#516176", font=("Arial", 10)).grid(
            row=1, column=0, sticky="w", padx=(16, 8), pady=(0, 14))
        self.token = ttk.Entry(auth, show="*")
        self.token.grid(row=1, column=1, sticky="ew", pady=(0, 14))
        tk.Button(auth, text="验证 Token", command=self.set_token, bg="#e7f0fb", fg="#1f5d98",
                  activebackground="#d6e7f8", relief="flat", padx=14, pady=4).grid(
            row=1, column=2, padx=(10, 16), pady=(0, 14))
        tk.Label(auth, text="复核人工号", bg="#ffffff", fg="#516176", font=("Arial", 10)).grid(
            row=2, column=0, sticky="w", padx=(16, 8), pady=(0, 14))
        self.review_job_no = ttk.Entry(auth, width=18)
        self.review_job_no.insert(0, os.getenv("FUJFU_REVIEW_JOB_NO", "S80118"))
        self.review_job_no.grid(row=2, column=1, sticky="w", pady=(0, 14))

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
        self.contracts.insert("1.0", "A260712024444431037\nA260506123300591240")

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
        self.status = tk.Text(log_card, height=10, state=tk.DISABLED, relief="flat", bd=0,
                              bg="#fbfcfe", fg="#334155", font=("Consolas", 9), padx=10, pady=8)
        self.status.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        root.rowconfigure(3, weight=1)

    def log(self, text):
        self.after(0, self._append_log, text)

    def _append_log(self, text):
        self.status.configure(state=tk.NORMAL)
        self.status.insert("end", text + "\n")
        self.status.see("end")
        self.status.configure(state=tk.DISABLED)

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
        if not self.set_token():
            return
        contracts = self._items()
        if not contracts:
            messagebox.showwarning("提示", "请粘贴至少一个合同编号")
            return
        if execute and not messagebox.askyesno(
            "确认执行", f"即将提交并复核 {len(contracts)} 个合同的划扣交易，确定继续吗？"
        ):
            return
        self.count_label.configure(text=f"已读取 {len(contracts)} 条合同")
        self.stop_event.clear()
        self._set_running(True)
        threading.Thread(target=self._run, args=(contracts, execute), daemon=True).start()

    def _run(self, contracts, execute):
        reviewer_id = None
        if execute:
            users = self.processor.get_review_user_list()
            reviewer_id = resolve_review_user_id(users, self.review_job_no.get().strip())
            if not reviewer_id:
                self.log(f"找不到复核人：{self.review_job_no.get().strip()}")
                self.after(0, lambda: self._set_running(False))
                return
            self.log(f"复核人已匹配：{self.review_job_no.get().strip()}")
        for index, contract in enumerate(contracts, start=1):
            if self.stop_event.is_set():
                self.log("已停止")
                break
            result = process_one(
                self.processor, InputRow(index, contract, ""), execute=execute,
                review_user_id=reviewer_id or "", submit_opinion="扣款",
            )
            self.log(json.dumps(result, ensure_ascii=False, default=str))
        self.after(0, lambda: self._set_running(False))

    def stop(self):
        self.stop_event.set()
        self.log("正在停止，当前请求完成后停止")

    def _set_running(self, running):
        state = tk.DISABLED if running else tk.NORMAL
        self.query_btn.configure(state=state)
        self.execute_btn.configure(state=state)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)


if __name__ == "__main__":
    App().mainloop()
