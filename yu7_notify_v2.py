import requests
import json
import os
import sys
import re
import argparse
import logging
from datetime import datetime, timedelta
import toml

# =====================
# 基础配置
# =====================
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

BIN = os.path.dirname(os.path.realpath(__file__))
config_path = os.path.join(BIN, "config.toml")

badge_week = None

# =====================
# 配置加载
# =====================
def load_config():
    config = toml.load(config_path)
    try:
        return (
            config["account"]["orderId"],
            config["account"]["userId"],
            config["account"]["Cookie"],
            config["notice"].get("deliveryTimeLatest", ""),
            config["notice"].get("remarks", ""),
            config["notice"].get("errorTimes", 0),
        )
    except KeyError:
        logger.error("config.toml 参数缺失，请检查 account / notice 字段")
        sys.exit(1)

# =====================
# 交付时间解析
# =====================
def calculate_delivery_date(delivery_time, lock_time):
    weeks_pattern = r"(\d+)-(\d+)周"
    weeks_matches = re.findall(weeks_pattern, delivery_time)

    if not weeks_matches:
        return ""

    min_weeks, max_weeks = map(int, weeks_matches[-1])

    global badge_week
    badge_week = min_weeks

    current_date = datetime.now()
    if len(weeks_matches) == 1 and lock_time:
        current_date = datetime.strptime(lock_time, "%Y-%m-%d %H:%M:%S")

    start = current_date + timedelta(weeks=min_weeks)
    end = current_date + timedelta(weeks=max_weeks)

    return f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"

# =====================
# VID 状态
# =====================
def vid_status_mapping(vid: str):
    return "已下线" if vid.startswith("HXM") else "未下线"

# =====================
# 核心接口
# =====================
def get_order_detail(orderId, userId, Cookie):
    url = "https://api.retail.xiaomiev.com/mtop/car-order/order/detail"

    payload = [{"orderId": orderId, "userId": userId}]
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)",
        "Content-Type": "application/json",
        "Referer": "https://servicewechat.com/wx183d85f5e5e273c6/93/page-frame.html",
        "Cookie": Cookie,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=15)

    logger.warning("========== 接口请求调试信息 ==========")
    logger.warning(f"HTTP Status: {response.status_code}")

    try:
        resp_json = response.json()
    except Exception:
        logger.error("接口返回不是 JSON")
        logger.error(response.text)
        sys.exit(1)

    # 🔴 核心：完整打印返回结构
    logger.warning("接口返回 JSON：")
    logger.warning(json.dumps(resp_json, ensure_ascii=False, indent=2))

    data = resp_json.get("data")

    if not data:
        logger.error("接口返回 data 为空，可能 Cookie 失效或接口变更")
        sys.exit(1)

    # ===== 正常解析 =====
    statusInfo = data.get("statusInfo", {})
    orderTimeInfo = data.get("orderTimeInfo", {})
    buyCarInfo = data.get("buyCarInfo", {})

    order_status_name = statusInfo.get("orderStatusName")
    order_status = statusInfo.get("orderStatus")
    vid = buyCarInfo.get("vid", "")
    delivery_time = orderTimeInfo.get("deliveryTime")
    add_time = orderTimeInfo.get("addTime")
    pay_time = orderTimeInfo.get("payTime")
    lock_time = orderTimeInfo.get("lockTime")

    goods_names = " | ".join(
        item.get("goodsName", "") for item in data.get("orderItem", [])
    )

    return {
        "order_status_name": order_status_name,
        "order_status": order_status,
        "vid": vid,
        "delivery_time": delivery_time,
        "add_time": add_time,
        "pay_time": pay_time,
        "lock_time": lock_time,
        "goods_names": goods_names,
    }


# =====================
# 保存状态
# =====================
def save_config(delivery_time, order_status, error_times=0):
    config = toml.load(config_path)
    config["notice"]["deliveryTimeLatest"] = delivery_time
    config["notice"]["orderStatus"] = order_status
    config["notice"]["errorTimes"] = error_times

    with open(config_path, "w", encoding="utf-8") as f:
        toml.dump(config, f)

# =====================
# 日志输出（替代 Bark）
# =====================
def log_result(result: dict):
    logger.warning("========== 小米汽车订单状态 ==========")
    logger.warning(f"订单状态：{result['order_status_name']}")
    logger.warning(f"VID：{result['vid']}（{result['vid_status']}）")
    logger.warning(f"预计交付：{result['delivery_range']}")
    logger.warning(f"下定时间：{result['add_time']}")
    logger.warning(f"支付时间：{result['pay_time']}")
    logger.warning(f"锁单时间：{result['lock_time']}")
    logger.warning(f"配置：{result['goods']}")
    logger.warning("=====================================")

# =====================
# 主逻辑
# =====================
def main():
    if result["delivery_time"] != old_delivery_time:
        save_config(result["delivery_time"], result["order_status"])
        log_result(result)
    else:
        logger.warning("交付时间无变化，未输出新结果")

# =====================
# 启动入口
# =====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小米汽车订单状态查询")
    parser.add_argument("--orderId", type=str)
    parser.add_argument("--userId", type=str)
    parser.add_argument("--cookie", type=str)
    args = parser.parse_args()

    (
        orderId,
        userId,
        Cookie,
        old_delivery_time,
        remarks,
        error_times,
    ) = load_config()

    try:
        result = get_order_detail(orderId, userId, Cookie)
        main()
    except Exception as e:
        logger.error(f"请求失败：{e}")
        save_config(old_delivery_time, None, error_times + 1)
        sys.exit(1)
