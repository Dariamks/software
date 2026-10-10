"""从单笔划扣工具(3).exe 中恢复的核心网络类。

来源：PyInstaller 提取的 gui.pyc；这是按 Python 3.14 字节码重建的可读版本。
原始 gui.py 的 Tkinter 界面逻辑见同目录 gui_disassembly.txt。
"""
import base64
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ReviewerListError(Exception):
    pass


class SinglePaymentProcessor:
    def __init__(self, base_url=None, timeout=15):
        self.base_url = (base_url or (
            "https://rayleigh-inside-gateway.fujfu.com/"
            "urge-repayment-api/singlePayment/api/v2"
        )).rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://cuishou.fujfu.com",
            "Referer": "https://cuishou.fujfu.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36",
        }
        self.token = None
        self.current_user_id = None
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.1)
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def set_token(self, token):
        self.token = token
        try:
            parts = token.split(".")
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            self.current_user_id = json.loads(base64.urlsafe_b64decode(payload)).get("sub")
        except (IndexError, ValueError, json.JSONDecodeError):
            self.current_user_id = None
        self.headers["X-User-Token"] = token
        self.headers["Cookie"] = f"token={token}"
        self.session.headers.update(self.headers)

    def check_token_expiry(self, token):
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False, "Token格式错误"
            payload = parts[1]
            payload += "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            exp_timestamp = data.get("exp", 0)
            exp_time = datetime.fromtimestamp(exp_timestamp)
            now = datetime.now()
            hours_left = (exp_time - now).total_seconds() / 3600
            if hours_left < 0:
                return False, "Token已过期"
            return True, f"有效期至: {exp_time.strftime('%Y-%m-%d %H:%M')}"
        except Exception:
            return None, "无法验证Token"

    def search_wait_list(self, cert_id, contract_no, page_size):
        url = f"{self.base_url}/searchWaitSinglePaymentLoanList"
        params = {
            "certId": cert_id, "customerName": "", "contractNo": contract_no,
            "total": 1, "pageNumber": 0, "pageSize": page_size,
        }
        try:
            response = self.session.post(url, json=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def get_loan_detail(self, serial_no):
        url = f"{self.base_url}/getWaitSinglePaymentLoanDetail/{serial_no}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return result.get("data") if result.get("code") == 0 else None
        except (requests.RequestException, ValueError):
            return None

    def get_review_user_list(self):
        """Return reviewers available to the current logged-in user."""
        url = f"{self.base_url}/getReviewUserList"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("code") != 0:
                raise ReviewerListError("加载复核人失败：登录状态或权限校验未通过")
            return result.get("data")
        except requests.HTTPError as exc:
            raise ReviewerListError(f"加载复核人失败：HTTP {exc.response.status_code}，请检查登录状态或网络环境") from exc
        except requests.RequestException as exc:
            raise ReviewerListError("加载复核人失败：网络连接异常或超时") from exc
        except ValueError as exc:
            raise ReviewerListError("加载复核人失败：接口返回格式异常") from exc

    def submit_single_payment(self, payment_data):
        url = f"{self.base_url}/submitSinglePaymentData"
        try:
            response = self.session.post(url, json=payment_data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def search_review_list(self, cert_id, contract_no, page_size):
        url = f"{self.base_url}/searchReviewSinglePaymentTransactionList"
        params = {
            "certId": cert_id, "customerName": "", "contractNo": contract_no,
            "transStatus": "复核中", "reviewUserId": self.current_user_id,
            "submitUserId": None, "pageNumber": 0, "pageSize": page_size,
        }
        try:
            response = self.session.post(url, json=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def confirm_review(self, id_list):
        url = f"{self.base_url}/confirmReviewSinglePaymentTransaction"
        data = [{"id": str(item)} for item in id_list]
        try:
            response = self.session.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def query_repay_statistics(self, cert_id):
        url = (
            "https://rayleigh-inside-gateway.fujfu.com/"
            "urge-repayment-api/repayRecord/api/repayRecordDetailStatistics"
        )
        end_date = datetime.now().strftime("%Y/%m/%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y/%m/%d")
        params = {
            "credit": cert_id, "repayDateStart": start_date, "repayDateEnd": end_date,
            "overdueLevel": [], "commissionOverdueLevel": [], "pageNum": 1,
            "pageSize": 100,
        }
        try:
            response = self.session.post(url, json=params, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return result.get("data") if result.get("code") == 0 else None
        except (requests.RequestException, ValueError):
            return None
