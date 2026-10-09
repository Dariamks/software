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
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(5, weight=1)
        ttk.Label(root, text="X-User-Token").grid(row=0, column=0, sticky="w", pady=4)
        self.token = ttk.Entry(root, show="*", width=70)
        self.token.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(root, text="设置 Token", command=self.set_token).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(root, text="复核人工号").grid(row=1, column=0, sticky="w", pady=4)
        self.review_job_no = ttk.Entry(root, width=18)
        self.review_job_no.insert(0, os.getenv("FUJFU_REVIEW_JOB_NO", "S80118"))
        self.review_job_no.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(root, text="合同编号（每行一个）").grid(row=2, column=0, sticky="nw", pady=4)
        self.contracts = tk.Text(root, height=9, width=60, undo=True)
        self.contracts.grid(row=2, column=1, columnspan=2, sticky="nsew", pady=4)
        ttk.Label(root, text="示例：A260712024444431037\nA260506123300591240", foreground="#666").grid(
            row=3, column=1, columnspan=2, sticky="nw")
        actions = ttk.Frame(root)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        self.query_btn = ttk.Button(actions, text="仅查询/预览", command=lambda: self.start(False))
        self.query_btn.pack(side="left", padx=(0, 8))
        self.execute_btn = ttk.Button(actions, text="执行划扣并复核", command=lambda: self.start(True))
        self.execute_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(actions, text="停止", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side="left")
        ttk.Label(root, text="处理日志").grid(row=5, column=0, sticky="nw", pady=4)
        self.status = tk.Text(root, height=14, width=90, state=tk.DISABLED)
        self.status.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=4)

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
