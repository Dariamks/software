"""可运行的恢复版入口。
核心接口实现位于 single_payment_processor_recovered.py。
"""
import tkinter as tk
from tkinter import ttk, messagebox
from single_payment_processor_recovered import SinglePaymentProcessor


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("单笔划扣工具（恢复版）")
        self.geometry("620x260")
        self.processor = SinglePaymentProcessor()
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="X-User-Token").grid(row=0, column=0, sticky="w", pady=5)
        self.token = ttk.Entry(frame, width=72, show="*")
        self.token.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Button(frame, text="设置 Token", command=self.set_token).grid(row=0, column=2, padx=8)
        ttk.Label(frame, text="身份证号").grid(row=1, column=0, sticky="w", pady=5)
        self.cert = ttk.Entry(frame, width=30)
        self.cert.grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(frame, text="合同号").grid(row=2, column=0, sticky="w", pady=5)
        self.contract = ttk.Entry(frame, width=30)
        self.contract.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Button(frame, text="查询待划扣列表", command=self.search).grid(row=3, column=1, sticky="w", pady=12)
        self.status = tk.Text(frame, height=6, width=72)
        self.status.grid(row=4, column=0, columnspan=3, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

    def set_token(self):
        token = self.token.get().strip()
        if not token:
            messagebox.showwarning("提示", "请输入 Token")
            return
        valid, text = self.processor.check_token_expiry(token)
        self.status.insert("end", f"Token检查：{text}\n")
        if valid is not False:
            self.processor.set_token(token)

    def search(self):
        cert, contract = self.cert.get().strip(), self.contract.get().strip()
        if not cert:
            messagebox.showwarning("提示", "请输入身份证号")
            return
        result = self.processor.search_wait_list(cert, contract, 100)
        self.status.insert("end", f"查询结果：{result!r}\n")


if __name__ == "__main__":
    App().mainloop()
