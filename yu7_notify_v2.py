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
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.60(0x18003c31) NetType/4G Language/zh_CN",
        "Accept-Encoding": "gzip,compress,br,deflate",
        "Content-Type": "application/json",
        "configSelectorVersion": "2",
        "content-type": "application/json; charset=utf-8",
        "deviceappversion": "1.16.0",
        "x-user-agent": "channel/car platform/car.wxlite",
        "Referer": "https://servicewechat.com/wx183d85f5e5e273c6/93/page-frame.html",
        "Cookie": Cookie,
    }

    response = requests.post(url, data=json.dumps(payload), headers=headers)

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
    
    logo_link = data.get("backdropPictures", {}).get("backdropPicture", None)
    statusInfo = data.get("statusInfo", {})
    vid = data.get("buyCarInfo", {}).get("vid", "")
    orderTimeInfo = data.get("orderTimeInfo", {})

    order_status_name = statusInfo.get("orderStatusName", None)
    order_status = statusInfo.get("orderStatus")
    delivery_time = orderTimeInfo.get("deliveryTime")

    vid_text = f"🛠️ vid：{vid}【{vid_status_mapping(str(vid))}】"
    remarks_text = " " * 50 + remarks

    if not delivery_time:
        delivery_time = "请检查account参数是否正确！"
        error_times_update = error_times + 1

        message = f"{delivery_time}\n\n失败次数：{error_times_update}\norderId：{orderId}\nuserId：{userId}\nCookie：{Cookie}\n【失败次数超过3次后将停止发送】\n\n{remarks_text}\n\n{order_status}"

        save_config(
            delivery_time,
            order_status,
            # carshop_notice=carshop_notice,
            error_times=error_times_update,
        )
        # if error_times_update <= 3:
        #     send_bark_message(device_token, message, orderStatusName="account参数错误")

        logger.warning(delivery_time)
        sys.exit()
    add_time = orderTimeInfo.get("addTime")
    pay_time = orderTimeInfo.get("payTime")
    lock_time = orderTimeInfo.get("lockTime")
    goods_names = " | ".join(
        item.get("goodsName", "") for item in data.get("orderItem", [])
    )
    delivery_date_range = calculate_delivery_date(delivery_time, lock_time)
    text = f"{delivery_date_range}\n\n📅 下定时间：{add_time}\n💳 支付时间：{pay_time}\n🔒 锁单时间：{lock_time}\n\n🛍️ 配置：{goods_names}\n\n{vid_text}\n\n{remarks_text}"
    # print(text)

    return {
        "delivery_time": delivery_time,
        "order_status": order_status,
        "order_status_name": order_status_name,
        "message": text,
        "logo_link": logo_link,
        "vid": vid,
        "vid_status": vid_status_mapping(str(vid)),
        "delivery_range": calculate_delivery_date(delivery_time, lock_time),
        "add_time": add_time,
        "pay_time": pay_time,
        "lock_time": lock_time,
        "goods": goods_names,
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

    # ===== 命令行参数优先覆盖 =====
    if args.orderId:
        orderId = args.orderId
    if args.userId:
        userId = args.userId
    if args.cookie:
        Cookie = args.cookie

    try:
        logger.warning("========== 参数校验 ==========")
        logger.warning(f"orderId: {orderId[:5]}")
        logger.warning(f"userId: {userId[:5]}")
        logger.warning(f"Cookie 是否存在: {'是' if Cookie else '否'}")
        if Cookie:
            logger.warning(f"Cookie 前 20 字符: {Cookie[:20]}...")

        # delivery_time, order_status, message, order_status_name, logo_link, vid = get_order_detail(orderId, userId, Cookie)
        result = get_order_detail(orderId, userId, Cookie)
        main()
    except Exception as e:
        logger.error(f"请求失败：{e}")
        save_config(old_delivery_time, None, error_times + 1)
        sys.exit(1)
