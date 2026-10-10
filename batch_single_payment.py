#!/usr/bin/env python3
"""Batch single-payment workflow driven by an XLSX input file.

The workflow mirrors the portal's manual flow:
search wait list -> fetch loan detail -> submit single payment -> review -> confirm.
Dry-run is the default; use --execute only on the authorized remote machine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from single_payment_processor_recovered import SinglePaymentProcessor

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class InputRow:
    row_number: int
    contract_no: str
    cert_id: str


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in root.findall("m:si", NS)]


def _cell_value(cell: ET.Element, strings: list[str]) -> str:
    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return ""
    text = value.text
    if cell.get("t") == "s":
        try:
            return strings[int(text)]
        except (ValueError, IndexError):
            return ""
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", NS))
    return text


def _col_number(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    number = 0
    for ch in letters.upper():
        number = number * 26 + ord(ch) - 64
    return number


def read_input_rows(path: str | os.PathLike[str], sheet: str = "sheet1") -> list[InputRow]:
    """Read the two-column input workbook without requiring openpyxl/pandas."""
    with zipfile.ZipFile(path) as zf:
        strings = _shared_strings(zf)
        root = ET.fromstring(zf.read(f"xl/worksheets/{sheet}.xml"))
    rows: list[list[str]] = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            values[_col_number(cell.get("r", "A1"))] = _cell_value(cell, strings).strip()
        rows.append([values.get(1, ""), values.get(2, "")])
    if not rows:
        return []
    header = [x.replace(" ", "") for x in rows[0]]
    if header[0] not in {"借据号（合同编号）", "借据号(合同编号)", "合同编号", "借据号"} or header[1] not in {"身份证号码", "身份证号"}:
        raise ValueError(f"首行必须是借据号/合同编号和身份证号码，实际为：{rows[0]!r}")
    result: list[InputRow] = []
    for row_number, (contract_no, cert_id) in enumerate(rows[1:], start=2):
        if not contract_no and not cert_id:
            continue
        if not contract_no or not cert_id:
            raise ValueError(f"第 {row_number} 行缺少合同编号或身份证号码：{contract_no!r}, {cert_id!r}")
        result.append(InputRow(row_number, contract_no, cert_id))
    return result


def _content(result: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not result or result.get("code") != 0:
        return []
    data = result.get("data") or {}
    return list(data.get("content") or []) if isinstance(data, Mapping) else []


def resolve_review_user_id(users: Any, job_no: str) -> str | None:
    """Resolve the portal's reviewer ID from getReviewUserList by job number."""
    if isinstance(users, Mapping):
        for key in ("content", "records", "list", "data"):
            if key in users:
                found = resolve_review_user_id(users[key], job_no)
                if found:
                    return found
        if str(users.get("jobNo") or users.get("job_no") or "") == job_no:
            return str(users.get("id") or users.get("userId") or users.get("reviewUserId") or "") or None
    if isinstance(users, list):
        for item in users:
            found = resolve_review_user_id(item, job_no)
            if found:
                return found
    return None


def process_one(processor: SinglePaymentProcessor, row: InputRow, *, execute: bool,
                review_user_id: str, submit_opinion: str, pause_seconds: float = 0.2) -> dict[str, Any]:
    out: dict[str, Any] = {"row": row.row_number, "contract_no": row.contract_no, "cert_id": row.cert_id,
                           "status": "dry_run" if not execute else "started", "logs": []}
    search = processor.search_wait_list(row.cert_id, row.contract_no, 100)
    loans = [loan for loan in _content(search) if loan.get("contractNo") == row.contract_no]
    if not loans:
        out["status"] = "no_wait_record" if search and search.get("code") == 0 else "search_failed"
        return out
    out["found"] = len(loans)
    for loan in loans:
        serial_no = loan.get("serialNo")
        contract_no = loan.get("contractNo") or row.contract_no
        detail = processor.get_loan_detail(serial_no) if serial_no else None
        if not detail:
            out.setdefault("failed", []).append({"contract_no": contract_no, "reason": "detail_failed"})
            continue
        actual_pay = detail.get("actualPayAmt")
        if not actual_pay or str(actual_pay) in {"0", "0.00"}:
            current_pay = detail.get("currentPeriodPaymentAmt")
            actual_pay = current_pay if current_pay and str(current_pay) not in {"0", "0.00"} else None
        if not actual_pay:
            out.setdefault("skipped", []).append({"contract_no": contract_no, "reason": "amount_zero"})
            continue
        if not detail.get("payAccountNo"):
            out.setdefault("skipped", []).append({"contract_no": contract_no, "reason": "missing_pay_account"})
            continue
        payment_data = {key: detail.get(key) for key in (
            "serialNo", "contractNo", "customerName", "productType", "businessSum", "certId",
            "channelSource", "currentPeriodPaymentAmt", "customerId", "overdueAmt",
            "overdueInterestAmt", "payAccountName", "payAccountNo", "payFailFee", "payInterestAmt",
            "payPrincipalAmt", "payPrincipalPenaltyAmt", "payServiceFee", "principalBalance", "putoutDate")}
        payment_data.update({"actualPayAmt": actual_pay, "reviewUserId": review_user_id,
                             "submitOpinion": submit_opinion})
        if not execute:
            out.setdefault("would_submit", []).append(payment_data)
            continue
        submitted = processor.submit_single_payment(payment_data)
        if not submitted or submitted.get("code") != 0:
            out.setdefault("failed", []).append({"contract_no": contract_no, "reason": "submit_failed", "response": submitted})
            continue
        out.setdefault("submitted", []).append({"contract_no": contract_no, "amount": actual_pay})
    if execute and out.get("submitted"):
        time.sleep(pause_seconds)
        review = processor.search_review_list(row.cert_id, row.contract_no, 100)
        review_ids = [item.get("id") for item in _content(review) if item.get("contractNo") == row.contract_no and item.get("transStatus") == "复核中" and item.get("id") is not None]
        if review_ids:
            confirmation = processor.confirm_review(review_ids)
            returned = (confirmation or {}).get("data")
            confirmed_ids = {str(item.get("id")) for item in returned
                             if isinstance(item, dict) and not item.get("errorMsg")
                             and item.get("transStatus") in {"已复核", "处理成功"}} if isinstance(returned, list) and confirmation.get("code") == 0 else set()
            out["review"] = {"ids": review_ids, "response": confirmation,
                             "confirmed": len(confirmed_ids.intersection(map(str, review_ids)))}
    if execute:
        out["status"] = "completed" if not out.get("failed") else "completed_with_errors"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量执行单笔划扣流程（默认只查询并生成预览）")
    parser.add_argument("--xlsx", required=True, help="包含借据号/合同编号和身份证号码的 XLSX")
    parser.add_argument("--token", default=os.getenv("FUJFU_TOKEN"), help="X-User-Token；也可用 FUJFU_TOKEN")
    parser.add_argument("--execute", action="store_true", help="执行真实提交和复核；仅在授权远程电脑上使用")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 行，0 表示全部")
    parser.add_argument("--output", default="single_payment_results.jsonl", help="结果 JSONL 路径")
    parser.add_argument("--review-user-id", default=os.getenv("FUJFU_REVIEW_USER_ID"), help="复核人 ID；不提供时按工号查询")
    parser.add_argument("--review-job-no", default=os.getenv("FUJFU_REVIEW_JOB_NO", "S80118"), help="页面选择的复核人工号")
    parser.add_argument("--submit-opinion", default="申请扣款")
    args = parser.parse_args(argv)
    if args.execute and not args.token:
        parser.error("--execute 必须同时提供 --token 或 FUJFU_TOKEN")
    rows = read_input_rows(args.xlsx)
    if args.limit:
        rows = rows[:args.limit]
    processor = SinglePaymentProcessor(base_url=os.getenv("FUJFU_BASE_URL"))
    if args.token:
        processor.set_token(args.token)
    if args.execute:
        valid, message = processor.check_token_expiry(args.token)
        if valid is False:
            parser.error(message)
        print(f"Token: {message}", file=sys.stderr)
        if not args.review_user_id:
            users = processor.get_review_user_list()
            args.review_user_id = resolve_review_user_id(users, args.review_job_no)
            if not args.review_user_id:
                parser.error(f"无法从 getReviewUserList 找到复核人 {args.review_job_no}，请显式提供 --review-user-id")
    with open(args.output, "w", encoding="utf-8") as fp:
        for row in rows:
            if not args.token:
                result = {"row": row.row_number, "contract_no": row.contract_no,
                          "cert_id": row.cert_id, "status": "plan_only",
                          "message": "未提供 Token，未调用远程接口"}
            else:
                result = process_one(processor, row, execute=args.execute, review_user_id=args.review_user_id,
                                     submit_opinion=args.submit_opinion)
            fp.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
