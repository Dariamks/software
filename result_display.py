"""面向操作人员的单行结果，不显示接口字段或个人资料。"""


def format_result(result):
    messages = []
    status = result.get("status")
    if status == "no_wait_record":
        messages.append("未处理：没有待划扣记录")
    elif status == "search_failed":
        messages.append("查询失败：接口未返回有效结果，请检查网络和登录状态")
    reasons = {
        "detail_failed": "获取贷款详情失败",
        "amount_zero": "应还金额为零，已跳过",
        "missing_pay_account": "缺少还款银行卡，已跳过",
        "submit_failed": "提交失败",
    }
    for item in result.get("failed", []) + result.get("skipped", []):
        response = item.get("response") or {}
        reason = response.get("msg") or reasons.get(item.get("reason"), "处理异常")
        messages.append(str(reason))
    if result.get("would_submit"):
        messages.append("查询成功：可提交，尚未划扣、未复核")
    if result.get("submitted"):
        review = result.get("review") or {}
        response = review.get("response") or {}
        if not review:
            messages.append("已提交，未完成复核：未获取到待复核记录")
        elif response.get("code") != 0:
            messages.append("复核失败：" + str(response.get("msg") or "接口无有效响应，结果待核实"))
        else:
            rows = response.get("data")
            matched = {str(r.get("id")): r for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}
            for item_id in review.get("ids", []):
                item = matched.get(str(item_id), {})
                state = item.get("transStatus")
                error = item.get("errorMsg")
                if error or state == "处理失败":
                    messages.append("处理失败：" + str(error or "服务端未提供失败原因"))
                elif state in ("已复核", "处理成功"):
                    messages.append("复核成功" if state == "已复核" else "复核成功，处理成功")
                else:
                    messages.append("复核结果待确认：" + str(state or "接口未返回交易状态"))
    if not messages:
        messages.append("未处理：没有可执行记录")
    summary = "；".join(dict.fromkeys(messages))
    return " ".join(f"{result.get('contract_no', '')}｜{summary}".splitlines())
