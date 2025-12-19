import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
import requests

API_URL = "https://api.retail.xiaomiev.com/mtop/guidemarketing/product/car/inventory/list"

HEADERS_TEMPLATE = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/132.0.0.0 Safari/537.36 "
                  "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
                  "MiniProgramEnv/Mac MacWechat/WMPF MacWechat/3.8.7(0x13080712) "
                  "UnifiedPCMacWechat(0xf2641411) XWEB/16990",
    "Content-Type": "application/json; charset=UTF-8",
    "deviceappversion": "1.19.2",
    "configSelectorVersion": "2",
    "x-user-agent": "channel/car platform/car.wxlite",
    "xweb_xhr": "1",
    "Referer": "https://servicewechat.com/wx183d85f5e5e273c6/124/page-frame.html",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# PAYLOAD 测试与生产版本都保留
# PAYLOAD = [{
#     "source": "wx",
#     "inventoryChannel": "NORMAL",
#     "conditions": {
#         "stockType": "all",
#         "itemType": "500015457",
#         "sortType": "priceAsc"
#     },
#     "pageNo": 1,
#     "pageSize": 200
# }]
PAYLOAD = [{
    "source": "wx",
    "inventoryChannel": "NORMAL",
    "conditions": {
        "stockType": "all",
        "itemType": "500015457",
        "sortType": "priceAsc",
        # "carSsuId": "600019694",
        "carSsuId": "600019693",
        "saleConfigFilterList": []
    },
    "pageNo": 1,
    "pageSize": 200
}]


def setup_logger():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s"
    )
    return logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookie", required=True, help="serviceTokenCar Cookie")
    return parser.parse_args()


def request_inventory(cookie: str) -> dict:
    headers = HEADERS_TEMPLATE.copy()
    headers["Cookie"] = cookie

    resp = requests.post(
        API_URL,
        headers=headers,
        data=json.dumps(PAYLOAD),
        timeout=15
    )

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP 请求失败，状态码：{resp.status_code}")

    return resp.json()


def match_ssu_info(ssu_info: str) -> bool:
    if not ssu_info:
        return False

    color_ok = "深海蓝" in ssu_info
    wheel_ok = ("幻刃轮毂" in ssu_info) or ("锻造梅花轮毂" in ssu_info)
    audio_ok = "豪华音响" in ssu_info
    # interior_ok = ("松石灰" in ssu_info) or ("鸢尾紫" in ssu_info) or ("珊瑚橙" in ssu_info)
    interior_ok = ("松石灰" in ssu_info) or ("鸢尾紫" in ssu_info)

    return color_ok and wheel_ok and audio_ok and interior_ok


def query_inventory(cookie: str, logger):
    logger.warning("========== 库存接口查询开始 ==========")
    try:
        resp_json = request_inventory(cookie)
    except Exception as e:
        logger.error(f"接口请求失败：{e}")
        sys.exit(1)

    # 🔍 接口返回校验日志
    code = resp_json.get("code")
    message = resp_json.get("message")
    data = resp_json.get("data", {})
    total = data.get("total")

    logger.warning("========== 接口返回校验 ==========")
    logger.warning(f"code: {code}")
    logger.warning(f"message: {message}")
    logger.warning(f"total: {total}")
    logger.warning("=================================")

    if code != 0:
        logger.error("接口返回非成功状态，终止执行")
        sys.exit(1)

    items = data.get("items", [])
    if not items:
        logger.warning("接口返回 items 为空")
        return False  # 未命中

    matched = []
    for item in items:
        ssu_info = item.get("ssuInfo", "")
        if match_ssu_info(ssu_info):
            matched.append({
                "classify": item.get("classify"),
                "marketPrice": item.get("marketPrice"),
                "ssuInfo": ssu_info
            })

    if not matched:
        logger.warning("未发现满足条件的现车配置")
        return False

    logger.warning("========== 命中现车配置 ==========")
    for idx, car in enumerate(matched, 1):
        logger.warning(f"[{idx}] classify: {car['classify']}")
        logger.warning(f"    marketPrice: {car['marketPrice']}")
        logger.warning(f"    ssuInfo: {car['ssuInfo']}")
    logger.warning("==================================")
    return True


def main():
    logger = setup_logger()
    args = parse_args()

    # 循环 sleep 步长（秒）
    sleep_steps = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]

    # 精准触发窗口 ±5秒
    tolerance = timedelta(seconds=5)

    # 目标触发时间（今天 11:00 和 23:00）
    now = datetime.now()
    today = now.date()
    target_times = [
        datetime(today.year, today.month, today.day, 11, 0, 0),
        datetime(today.year, today.month, today.day, 23, 0, 0)
    ]

    for step in sleep_steps:
        time.sleep(step)
        now = datetime.now()

        # 判断是否在触发窗口
        hit_window = any(abs(now - t_target) <= tolerance for t_target in target_times)
        if hit_window:
            query_inventory(args.cookie, logger)
            logger.warning(f"精准触发时间：{now}, 退出循环")
            break  # 一旦命中立即退出循环
        else:
            logger.warning(f"当前时间 {now} 不在触发窗口，继续 sleep")


if __name__ == "__main__":
    main()
